"""agent/orchestrator.py — Agentic Orchestration Layer.

This module coordinates the two agentic workflows defined in
REQUIREMENTS_EXTENSION.md:

1. **NL Parsing** (:meth:`PawPalOrchestrator.parse_nl_task`) — a single
   ``claude-haiku-4-5`` call that extracts a structured task from free-form
   text and dispatches ``add_task`` (or ``add_pet``).

2. **ReAct Resolution Loop** (:meth:`PawPalOrchestrator.resolve_schedule_conflicts`)
   — a bounded multi-turn conversation with ``claude-sonnet-4-6`` that calls
   ``reschedule_task`` and ``detect_conflicts`` in alternation until no
   conflicts remain or the step budget is exhausted.

3. **Guardrail** (:meth:`PawPalOrchestrator.run_final_guardrail`) — a
   synchronous post-loop check that restores any required tasks the LLM may
   have dropped, via :func:`agent.guardrail.run_guardrail`.

All three methods accumulate :class:`TraceStep` records in
``self.agent_trace`` so the Streamlit UI can render the full Thought /
Action / Observation audit trail.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Optional

import anthropic

from pawpal_system import Owner
from agent.guardrail import CorrectionResult, run_guardrail
from agent.prompts import (
    _BOUNDARY,
    SYSTEM_PROMPT,
    NL_PARSE_USER_TMPL,
    RESOLUTION_LOOP_TMPL,
)
from agent.tools import PawPalTools, TOOL_SCHEMAS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model constants — change here to switch providers / versions.
# ---------------------------------------------------------------------------

#: Model for natural-language task extraction (fast, cheap single-shot call).
NL_MODEL: str = "claude-haiku-4-5-20251001"

#: Model for the multi-turn ReAct resolution loop.
#: The user-facing requirement specifies "Claude Sonnet 3.5"; set this to
#: ``"claude-3-5-sonnet-20241022"`` to match that exactly.  The default
#: below uses the newer ``claude-sonnet-4-6`` which offers improved reasoning
#: at the same latency tier.
RESOLUTION_MODEL: str = "claude-sonnet-4-6"

#: Maximum number of LLM API calls during one Resolution Loop session.
#: Each call is one Thought + one Action (tool call).  Per NFR-01.
MAX_RESOLUTION_STEPS: int = 5


# ---------------------------------------------------------------------------
# Result / trace data classes
# ---------------------------------------------------------------------------


@dataclass
class TraceStep:
    """One completed Thought → Action → Observation cycle.

    Stored in :attr:`PawPalOrchestrator.agent_trace` and rendered by the
    Streamlit UI's "Agent Reasoning" expander.

    Attributes
    ----------
    step:
        1-based iteration index within the current loop.
    thought:
        The model's reasoning text (extracted from ``TextBlock`` content).
    action_tool:
        Name of the tool that was called, or ``"(end_turn)"`` when the model
        finished without a tool call.
    action_input:
        The ``input`` dict passed to the tool.
    observation:
        The JSON-serialisable result returned by the tool.
    """

    step: int
    thought: str
    action_tool: str
    action_input: dict[str, Any]
    observation: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        """Serialisable representation for session state storage."""
        return {
            "step": self.step,
            "thought": self.thought,
            "action_tool": self.action_tool,
            "action_input": self.action_input,
            "observation": self.observation,
        }


@dataclass
class ParseResult:
    """Result of a single :meth:`PawPalOrchestrator.parse_nl_task` call.

    Attributes
    ----------
    success:
        ``True`` when a task was successfully extracted and added to a pet.
    task_dict:
        The serialised :class:`~pawpal_system.Task` dict on success, else
        ``None``.
    clarification_question:
        The question to surface to the owner when the model could not
        confidently extract one or more required fields.  Set when
        ``success`` is ``False`` and the model returned a
        ``clarification_request`` response.
    error:
        Human-readable error string for unexpected failures (tool rejected
        the input, unknown pet name, etc.).
    """

    success: bool
    task_dict: Optional[dict[str, Any]] = None
    clarification_question: Optional[str] = None
    error: Optional[str] = None

    @property
    def needs_clarification(self) -> bool:
        """``True`` when the owner must answer a follow-up question."""
        return not self.success and self.clarification_question is not None


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class PawPalOrchestrator:
    """Co-ordinates NL parsing, the ReAct resolution loop, and the guardrail.

    Parameters
    ----------
    owner:
        The live :class:`~pawpal_system.Owner` shared with Streamlit session
        state.  Every tool call mutates or reads from this object in place.
    client:
        An initialised :class:`anthropic.Anthropic` client.  The caller is
        responsible for passing a client with a valid API key.
    max_resolution_steps:
        Override for :data:`MAX_RESOLUTION_STEPS`.  Useful for testing.

    Attributes
    ----------
    agent_trace:
        Accumulated :class:`TraceStep` records from the current session.
        Reset by :meth:`clear_trace`.  Rendered in the Streamlit UI's
        "Agent Reasoning" expander.
    """

    def __init__(
        self,
        owner: Owner,
        client: anthropic.Anthropic,
        max_resolution_steps: int = MAX_RESOLUTION_STEPS,
    ) -> None:
        self.owner = owner
        self.client = client
        self.tools = PawPalTools(owner)
        self.max_steps = max_resolution_steps
        self.agent_trace: list[TraceStep] = []

    def clear_trace(self) -> None:
        """Reset the trace list between scheduling sessions."""
        self.agent_trace = []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _format_schedule_context(self) -> str:
        """Render a compact owner/pet/task snapshot for the system prompt tail.

        Returns a multi-line string showing the owner's time budget and every
        pet with its tasks that are due today.  Called on every API call so
        the context always reflects the latest in-memory state.
        """
        today = date.today()
        lines: list[str] = [
            f"Owner: {self.owner.name}  |  "
            f"Available time: {self.owner.available_time_mins} min  |  "
            f"Date: {today.isoformat()}",
            "",
        ]
        for pet in self.owner.pets:
            due = [
                t for t in pet.tasks
                if t.due_date <= today and not t.is_completed
            ]
            lines.append(
                f"  {pet.get_summary()} — {len(due)} task(s) due today"
            )
            for t in due:
                req_tag = "  [REQUIRED]" if t.is_required else ""
                start_tag = f"  start={t.start_time}" if t.start_time else ""
                end_tag = (
                    f"  end={_compute_end_time(t.start_time, t.duration)}"
                    if t.start_time else ""
                )
                lines.append(
                    f"    • {t.name}  {t.duration} min  "
                    f"priority={t.priority}{start_tag}{end_tag}{req_tag}"
                )
        return "\n".join(lines)

    def _build_system_messages(self) -> list[dict[str, Any]]:
        """Return a two-block system message list with prompt caching.

        The static head (~97 % of the prompt) is marked ``cache_control:
        ephemeral`` so it is only tokenised once per 5-minute cache window.
        The dynamic tail (the schedule context snapshot) is not cached because
        it changes as tasks are rescheduled across turns.
        """
        context = self._format_schedule_context()
        # Format the whole prompt first so that {{ }} escape pairs are resolved.
        rendered = SYSTEM_PROMPT.format(schedule_context=context)
        boundary_idx = rendered.index(_BOUNDARY)
        return [
            {
                "type": "text",
                "text": rendered[:boundary_idx],
                "cache_control": {"type": "ephemeral"},
            },
            {
                "type": "text",
                "text": rendered[boundary_idx:],
            },
        ]

    @staticmethod
    def _serialize_content(content: list) -> list[dict[str, Any]]:
        """Convert SDK content block objects to plain dicts for message history.

        The Anthropic Python SDK returns Pydantic model objects in
        ``response.content``.  When we append an assistant turn to the
        ``messages`` list for the next API call we need plain dicts.

        Parameters
        ----------
        content:
            ``response.content`` from an ``anthropic.types.Message``.

        Returns
        -------
        list[dict]
            Each block serialised to a dict that the Anthropic API accepts.
        """
        result: list[dict[str, Any]] = []
        for block in content:
            btype = getattr(block, "type", None)
            if btype == "text":
                result.append({"type": "text", "text": block.text})
            elif btype == "tool_use":
                result.append(
                    {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    }
                )
        return result

    @staticmethod
    def _extract_thought(content: list) -> str:
        """Concatenate all text blocks from a response into a single Thought string.

        Returns a non-empty placeholder when the model emits no text blocks so
        that ``TraceStep.thought`` is always meaningful in the UI.
        """
        parts = [
            block.text.strip()
            for block in content
            if getattr(block, "type", None) == "text" and block.text.strip()
        ]
        return "\n".join(parts) or "(no text reasoning provided)"

    @staticmethod
    def _extract_json(text: str) -> Optional[dict[str, Any]]:
        """Attempt to parse a JSON object from a string, tolerating prose wrappers."""
        stripped = text.strip()
        # Strip markdown code fences if present
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass
        # Fall back to finding the first {...} block in mixed text
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return None

    def _format_conflict_pairs(self, conflicts: list[dict[str, Any]]) -> str:
        """Render conflict pairs as readable bullet points for the loop template."""
        if not conflicts:
            return "  (none)"
        lines: list[str] = []
        for i, pair in enumerate(conflicts, start=1):
            a = pair["task_a"]
            b = pair["task_b"]
            a_end = _compute_end_time(a.get("start_time"), a.get("duration", 0))
            b_end = _compute_end_time(b.get("start_time"), b.get("duration", 0))
            lines.append(
                f"  {i}. '{a['name']}' "
                f"({a.get('start_time', 'unset')}→{a_end}, "
                f"priority={a['priority']}, required={a['is_required']})\n"
                f"     overlaps with\n"
                f"     '{b['name']}' "
                f"({b.get('start_time', 'unset')}→{b_end}, "
                f"priority={b['priority']}, required={b['is_required']})"
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Method 1 — parse_nl_task
    # ------------------------------------------------------------------

    def parse_nl_task(self, user_input: str) -> ParseResult:
        """Extract a structured task from a natural-language description.

        Sends ``user_input`` to ``claude-haiku-4-5`` using
        :data:`~agent.prompts.NL_PARSE_USER_TMPL`.  The model responds with
        either an ``add_task`` tool call (confident extraction) or a
        ``clarification_request`` JSON object (one or more required fields
        could not be inferred).

        On a successful ``add_task`` tool call the task is appended to the
        named pet's task list **in place** and a :class:`ParseResult` with
        ``success=True`` is returned.

        On a ``clarification_request`` response a :class:`ParseResult` with
        ``success=False`` and ``clarification_question`` set is returned.  The
        caller should surface the question to the owner and retry with the
        enriched input.

        Parameters
        ----------
        user_input:
            Raw natural-language text from the owner.

        Returns
        -------
        ParseResult
            See :class:`ParseResult` for field semantics.
        """
        known_pets = (
            ", ".join(p.name for p in self.owner.pets) or "(no pets yet)"
        )
        user_message = NL_PARSE_USER_TMPL.format(
            raw_text=user_input,
            known_pets=known_pets,
        )

        logger.info("parse_nl_task: sending to %s.", NL_MODEL)
        response = self.client.messages.create(
            model=NL_MODEL,
            max_tokens=1024,
            system=self._build_system_messages(),
            tools=TOOL_SCHEMAS,
            messages=[{"role": "user", "content": user_message}],
        )

        thought = self._extract_thought(response.content)

        # ── Successful tool extraction ────────────────────────────────────
        if response.stop_reason == "tool_use":
            for block in response.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                try:
                    result = self.tools.dispatch(block.name, dict(block.input))
                except ValueError as exc:
                    return ParseResult(success=False, error=str(exc))

                step = TraceStep(
                    step=len(self.agent_trace) + 1,
                    thought=thought or f"Extracted task via {block.name}.",
                    action_tool=block.name,
                    action_input=dict(block.input),
                    observation=result,
                )
                self.agent_trace.append(step)
                logger.info("parse_nl_task: %s → %s", block.name, result)

                if result.get("success"):
                    return ParseResult(
                        success=True, task_dict=result.get("task")
                    )
                return ParseResult(success=False, error=result.get("error"))

        # ── Clarification request or unexpected end_turn ──────────────────
        for block in response.content:
            if getattr(block, "type", None) != "text":
                continue
            parsed = self._extract_json(block.text)
            if parsed and parsed.get("type") == "clarification_request":
                question = parsed.get(
                    "question",
                    "Could you provide more details about the task?",
                )
                step = TraceStep(
                    step=len(self.agent_trace) + 1,
                    thought=thought,
                    action_tool="clarification_request",
                    action_input={"missing_fields": parsed.get("missing_fields", [])},
                    observation={"question": question},
                )
                self.agent_trace.append(step)
                logger.info("parse_nl_task: clarification needed — %s", question)
                return ParseResult(
                    success=False, clarification_question=question
                )

        # Unexpected response shape
        error_msg = (
            f"NL parser returned an unexpected response "
            f"(stop_reason={response.stop_reason!r}).  "
            "Please rephrase your input."
        )
        logger.warning("parse_nl_task: %s", error_msg)
        return ParseResult(success=False, error=error_msg)

    # ------------------------------------------------------------------
    # Method 2 — resolve_schedule_conflicts (ReAct Loop)
    # ------------------------------------------------------------------

    def resolve_schedule_conflicts(self) -> dict[str, Any]:
        """Run the bounded ReAct loop to produce a conflict-free schedule.

        Algorithm
        ---------
        1. Call ``generate_schedule`` to get the deterministic baseline.
        2. Call ``detect_conflicts`` to check for overlapping time windows.
        3. If no conflicts, save state and return immediately.
        4. Otherwise enter the ReAct loop for up to
           :attr:`max_steps` LLM API calls:

           a. Build or extend the conversation with the current system prompt
              and (on the first turn) the formatted conflict list.
           b. Call ``claude-sonnet-4-6``.
           c. Extract the Thought (text blocks) and Action (``tool_use``
              blocks).
           d. Execute the tool via :meth:`~agent.tools.PawPalTools.dispatch`.
           e. Append the Observation (``tool_result``) to the message history
              so the next turn has full context.
           f. Record a :class:`TraceStep`.
           g. If the action was ``detect_conflicts`` and ``conflict_count``
              is 0, mark ``resolved=True`` and allow the model one final turn
              to call ``save_state`` and issue ``end_turn``.
           h. Stop early if ``stop_reason == "end_turn"`` or budget is gone.

        5. After the loop, if ``resolved`` is ``True`` but the model did not
           call ``save_state`` itself, the orchestrator calls it directly so
           no mutations are lost.
        6. Fetch the final schedule via a fresh ``generate_schedule`` call and
           return the full result dict.

        Returns
        -------
        dict
            ``{"schedule": dict, "conflicts_resolved": bool,
            "remaining_conflicts": list, "steps_taken": int,
            "escalated": bool, "agent_trace": list[dict]}``
        """
        # ── Baseline schedule ─────────────────────────────────────────────
        initial_schedule = self.tools.generate_schedule()
        initial_conflicts = self.tools.detect_conflicts(
            initial_schedule["scheduled_tasks"]
        )

        if initial_conflicts["conflict_count"] == 0:
            self.tools.save_state()
            logger.info("resolve_schedule_conflicts: no conflicts — done immediately.")
            return {
                "schedule": initial_schedule,
                "conflicts_resolved": True,
                "remaining_conflicts": [],
                "steps_taken": 0,
                "escalated": False,
                "agent_trace": [],
            }

        # ── Prepare opening user message ──────────────────────────────────
        opening_user_msg = RESOLUTION_LOOP_TMPL.format(
            conflict_count=initial_conflicts["conflict_count"],
            remaining_steps=self.max_steps,
            conflict_pairs=self._format_conflict_pairs(
                initial_conflicts["conflicts"]
            ),
            scheduled_tasks=json.dumps(
                initial_schedule["scheduled_tasks"], indent=2
            ),
        )

        messages: list[dict[str, Any]] = [
            {"role": "user", "content": opening_user_msg}
        ]

        # ── ReAct Loop ────────────────────────────────────────────────────
        resolved = False
        state_saved = False
        escalated = False
        steps_taken = 0
        last_detect_result: dict[str, Any] = initial_conflicts

        for step_n in range(1, self.max_steps + 1):
            steps_taken = step_n
            remaining = self.max_steps - step_n

            logger.info(
                "ReAct step %d/%d (remaining after this: %d).",
                step_n, self.max_steps, remaining,
            )

            response = self.client.messages.create(
                model=RESOLUTION_MODEL,
                max_tokens=2048,
                system=self._build_system_messages(),
                tools=TOOL_SCHEMAS,
                messages=messages,
            )

            thought = self._extract_thought(response.content)

            # ── Model ended turn without a tool call ──────────────────────
            if response.stop_reason == "end_turn":
                # Either the model confirmed success after save_state,
                # or it is escalating.
                action = "(end_turn — no tool call)"
                observation: dict[str, Any] = {
                    "model_text": thought,
                    "resolved": resolved,
                }
                self.agent_trace.append(
                    TraceStep(
                        step=step_n,
                        thought=thought,
                        action_tool="(end_turn)",
                        action_input={},
                        observation=observation,
                    )
                )
                if not resolved:
                    escalated = True
                    logger.warning(
                        "ReAct loop: model issued end_turn with unresolved conflicts."
                    )
                break

            if response.stop_reason == "max_tokens":
                logger.warning("ReAct loop: max_tokens hit at step %d.", step_n)
                escalated = True
                break

            # ── Process tool_use blocks ───────────────────────────────────
            tool_blocks = [
                b for b in response.content
                if getattr(b, "type", None) == "tool_use"
            ]
            if not tool_blocks:
                # Unexpected: stop_reason is tool_use but no blocks found.
                logger.error("ReAct loop: stop_reason=tool_use but no tool blocks.")
                escalated = True
                break

            # Append the assistant turn (Thought + Action) to history.
            messages.append(
                {
                    "role": "assistant",
                    "content": self._serialize_content(response.content),
                }
            )

            # Execute each tool and collect results.
            tool_results: list[dict[str, Any]] = []
            primary_tool = tool_blocks[0]

            for tu in tool_blocks:
                try:
                    obs = self.tools.dispatch(tu.name, dict(tu.input))
                except ValueError as exc:
                    obs = {"success": False, "error": str(exc)}

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": json.dumps(obs),
                    }
                )

                # Track detect_conflicts result for termination logic.
                if tu.name == "detect_conflicts":
                    last_detect_result = obs
                    if obs.get("conflict_count", 1) == 0:
                        resolved = True
                        logger.info(
                            "ReAct step %d: all conflicts resolved.", step_n
                        )

                if tu.name == "save_state" and obs.get("success"):
                    state_saved = True

            # Record primary trace step.
            primary_obs = json.loads(tool_results[0]["content"])
            self.agent_trace.append(
                TraceStep(
                    step=step_n,
                    thought=thought,
                    action_tool=primary_tool.name,
                    action_input=dict(primary_tool.input),
                    observation=primary_obs,
                )
            )

            # Feed observations back as the next user turn.
            messages.append({"role": "user", "content": tool_results})

            # If resolved and model just saved, allow one more turn for
            # end_turn, then break to avoid burning extra steps.
            if resolved and state_saved:
                break

            # Step budget exhausted.
            if step_n == self.max_steps and not resolved:
                escalated = True
                logger.warning(
                    "ReAct loop: step budget (%d) exhausted without full "
                    "conflict resolution.",
                    self.max_steps,
                )

        # ── Post-loop bookkeeping ─────────────────────────────────────────
        # If state was not saved yet — either the model resolved conflicts without
        # calling save_state, OR the loop escalated with partial reschedules —
        # persist the mutations now so nothing is lost on a reload.
        if not state_saved and (resolved or escalated):
            save_result = self.tools.save_state()
            logger.info("Orchestrator saved state after loop: %s", save_result)

        # Canonical final schedule (reflects all reschedule_task mutations).
        final_schedule = self.tools.generate_schedule()
        final_conflicts = self.tools.detect_conflicts(
            final_schedule["scheduled_tasks"]
        )
        conflicts_resolved = final_conflicts["conflict_count"] == 0

        return {
            "schedule": final_schedule,
            "conflicts_resolved": conflicts_resolved,
            "remaining_conflicts": final_conflicts["conflicts"],
            "steps_taken": steps_taken,
            "escalated": escalated,
            "agent_trace": [t.as_dict() for t in self.agent_trace],
        }

    # ------------------------------------------------------------------
    # Method 3 — run_final_guardrail
    # ------------------------------------------------------------------

    def run_final_guardrail(
        self, proposed_schedule: dict[str, Any]
    ) -> CorrectionResult:
        """Run the post-loop safety check and return a typed result.

        Delegates to :func:`agent.guardrail.run_guardrail`, which in turn
        calls :func:`agent.tools.validate_required_tasks` — the injection-proof
        guardrail that derives required tasks from the ``Owner`` object, never
        from ``proposed_schedule``.

        Any missing required tasks are auto-restored in the returned
        ``corrected_schedule``.  A :data:`~agent.guardrail.VIOLATION_LOG_PATH`
        entry is appended when ``guardrail_triggered`` is ``True``.

        This method MUST be called by the Streamlit UI immediately after
        :meth:`resolve_schedule_conflicts` and before any schedule results
        are displayed to the owner.

        Parameters
        ----------
        proposed_schedule:
            The ``"schedule"`` value from the dict returned by
            :meth:`resolve_schedule_conflicts`.

        Returns
        -------
        CorrectionResult
            Always use ``result.corrected_schedule`` as the source of truth
            for the UI, regardless of whether ``guardrail_triggered`` is set.
        """
        result = run_guardrail(proposed_schedule, self.owner)

        if result.guardrail_triggered:
            logger.warning(
                "run_final_guardrail: %d violation(s) — %s",
                result.violation_count,
                result.violations,
            )
            # Append a trace step so the guardrail action is visible in the UI.
            self.agent_trace.append(
                TraceStep(
                    step=len(self.agent_trace) + 1,
                    thought=(
                        "GUARDRAIL CHECK: One or more required tasks were absent "
                        "from the LLM-proposed schedule.  Auto-restoring now."
                    ),
                    action_tool="validate_required_tasks",
                    action_input={"owner": self.owner.name},
                    observation={
                        "guardrail_triggered": True,
                        "violations": result.violations,
                        "violation_count": result.violation_count,
                    },
                )
            )
        else:
            logger.info("run_final_guardrail: clean — no violations.")

        return result


# ---------------------------------------------------------------------------
# Module-level utility
# ---------------------------------------------------------------------------


def _compute_end_time(start_time: Optional[str], duration: int) -> str:
    """Compute HH:MM end time from a start time string and duration in minutes.

    Parameters
    ----------
    start_time:
        HH:MM string, or ``None`` / empty string.
    duration:
        Task duration in minutes.

    Returns
    -------
    str
        Computed end time as ``HH:MM``, or ``"unset"`` when start_time is
        not provided.
    """
    if not start_time:
        return "unset"
    try:
        t = datetime.strptime(start_time, "%H:%M") + timedelta(minutes=duration)
        return t.strftime("%H:%M")
    except ValueError:
        return "invalid"
