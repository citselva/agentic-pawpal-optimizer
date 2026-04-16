"""agent/tools.py — PawPal+ LLM Tool Layer.

This module provides the complete inventory of callable tools used by the
agentic orchestration layer.

**Tools 1–9** are LLM-callable.  They are implemented as methods on
:class:`PawPalTools` and their Anthropic-format JSON schemas are collected in
:data:`TOOL_SCHEMAS`.  Pass ``TOOL_SCHEMAS`` directly to the ``tools``
parameter of ``anthropic.messages.create()``.

**Tool 10** (:func:`validate_required_tasks`) is a synchronous guardrail
utility.  It is intentionally absent from :data:`TOOL_SCHEMAS` and is called
exclusively by the Orchestrator after the Resolution Loop completes — never by
the LLM.  This design makes the safety check injection-proof: an adversarial
prompt cannot instruct the model to skip or disable it.

Import note
-----------
This module imports from ``pawpal_system``, which lives at the project root
(one level above this file).  When Streamlit or pytest launches from the
project root, that root is already on ``sys.path``, so the bare
``from pawpal_system import …`` resolves correctly.  There is no circular
import risk because ``pawpal_system.py`` does not import anything from
``agent/``.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Optional

from pawpal_system import Owner, Pet, Scheduler, Task

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# TOOL_SCHEMAS — Anthropic tool-use definitions for Tools 1–9
#
# Pass this list directly to anthropic.messages.create(tools=TOOL_SCHEMAS).
# Tool 10 (validate_required_tasks) is intentionally excluded.
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = [
    # ── Tool 1 ──────────────────────────────────────────────────────────────
    {
        "name": "get_all_tasks",
        "description": (
            "Return every care task that is due today or overdue and has not yet "
            "been permanently completed.  Use this tool to obtain a fresh, "
            "authoritative snapshot of the owner's actionable work before deciding "
            "how to schedule or prioritise.  Each task in the response includes a "
            "'pet_name' field so ownership is always traceable."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    # ── Tool 2 ──────────────────────────────────────────────────────────────
    {
        "name": "generate_schedule",
        "description": (
            "Run the two-phase deterministic scheduler against the owner's current "
            "time budget and return a full ScheduleResult.  "
            "Phase 1 places all required tasks unconditionally — even if their "
            "combined duration exceeds available_time_mins — and appends a "
            "'Time Deficit' note to reasoning when this occurs.  "
            "Phase 2 greedily fills remaining time with optional tasks ordered by "
            "priority descending; tasks that do not fit go to skipped_tasks.  "
            "A sweep-line conflict scan runs after both phases; any overlapping "
            "[start_time, end_time) windows produce a WARNING in reasoning.  "
            "Call this tool once at the start of each scheduling session.  "
            "If reasoning contains 'WARNING', proceed to call detect_conflicts "
            "and enter the Resolution Loop."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    # ── Tool 3 ──────────────────────────────────────────────────────────────
    {
        "name": "detect_conflicts",
        "description": (
            "Identify pairs of tasks whose time windows overlap.  "
            "Only tasks that carry a start_time value participate; tasks without "
            "one are silently ignored.  Two tasks conflict when the later task's "
            "start_time is strictly less than the earlier task's end_time "
            "(closed-open interval [start, end) semantics).  "
            "Use this tool: (a) after generate_schedule, to confirm whether "
            "conflicts exist before entering the Resolution Loop; and (b) after "
            "every reschedule_task call, to verify the shift resolved the conflict "
            "and did not introduce new overlaps."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "description": (
                        "List of task dicts to check for time-window overlaps.  "
                        "Each element must contain at minimum 'name', 'duration', "
                        "and 'start_time' fields.  Pass the 'scheduled_tasks' list "
                        "from a generate_schedule or reschedule_task response."
                    ),
                    "items": {"type": "object"},
                },
            },
            "required": ["tasks"],
        },
    },
    # ── Tool 4 ──────────────────────────────────────────────────────────────
    {
        "name": "add_task",
        "description": (
            "Create a new care task and assign it to a named pet.  "
            "Use this tool after extracting a fully-formed task from the owner's "
            "natural-language input.  Do NOT call it until every required field "
            "has been confirmed — if any field is ambiguous or missing, ask the "
            "owner a targeted clarification question first and wait for the answer.  "
            "The task becomes visible in the next generate_schedule call when its "
            "due_date is today or earlier.  "
            "Priority inference guide (apply when the owner does not state a number): "
            "5='critical/medication/vet/required', 4='important/don't forget', "
            "3='normal/regular' (default), 2='low/if possible', "
            "1='whenever/optional/nice to have'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pet_name": {
                    "type": "string",
                    "description": "Exact name of the pet this task belongs to.",
                },
                "name": {
                    "type": "string",
                    "description": "Short, descriptive task title (e.g. 'Morning Walk').",
                },
                "duration": {
                    "type": "integer",
                    "description": "How long the task takes, in whole minutes (minimum 1).",
                },
                "priority": {
                    "type": "integer",
                    "description": (
                        "Urgency level on a 1–5 integer scale: "
                        "1=lowest, 3=normal, 5=highest."
                    ),
                },
                "is_required": {
                    "type": "boolean",
                    "description": (
                        "True when the task MUST happen today regardless of the "
                        "time budget (e.g. medication, critical vet appointment).  "
                        "Defaults to false."
                    ),
                },
                "start_time": {
                    "type": "string",
                    "description": (
                        "Preferred wall-clock start in HH:MM 24-hour format "
                        "(e.g. '08:30'), or null if the owner did not specify one."
                    ),
                },
                "frequency": {
                    "type": "string",
                    "description": (
                        "Recurrence pattern: 'one-off' (default, task is retired "
                        "after completion), 'daily' (resurfaces tomorrow), "
                        "or 'weekly' (resurfaces in seven days)."
                    ),
                    "enum": ["one-off", "daily", "weekly"],
                },
                "due_date": {
                    "type": "string",
                    "description": (
                        "ISO-8601 date string (YYYY-MM-DD).  Defaults to today "
                        "if omitted."
                    ),
                },
            },
            "required": ["pet_name", "name", "duration", "priority"],
        },
    },
    # ── Tool 5 ──────────────────────────────────────────────────────────────
    {
        "name": "reschedule_task",
        "description": (
            "Update a task's start_time to resolve a scheduling conflict.  "
            "This is the primary — and only — mutation the agent may make during "
            "the Resolution Loop.  "
            "Hard constraints you MUST respect: "
            "(1) Do NOT change duration — it would invalidate the time-budget maths.  "
            "(2) Do NOT change priority — it would override the owner's stated urgency.  "
            "(3) Do NOT change is_required — it would bypass the safety guardrail.  "
            "Resolution strategy: prefer shifting the lower-priority task first; "
            "when both are required, shift the shorter one; setting "
            "task_b.start_time = task_a.end_time is always safe for the pair, "
            "but always re-check the full schedule for cascading conflicts by "
            "calling detect_conflicts immediately after."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pet_name": {
                    "type": "string",
                    "description": "Name of the pet that owns the task.",
                },
                "task_name": {
                    "type": "string",
                    "description": "Exact name of the task to reschedule.",
                },
                "new_start_time": {
                    "type": "string",
                    "description": (
                        "New start time in HH:MM 24-hour format (e.g. '09:30').  "
                        "Verify this does not create a new overlap with an adjacent "
                        "task before committing."
                    ),
                },
            },
            "required": ["pet_name", "task_name", "new_start_time"],
        },
    },
    # ── Tool 6 ──────────────────────────────────────────────────────────────
    {
        "name": "complete_task",
        "description": (
            "Mark a task as done with correct recurrence handling.  "
            "One-off tasks are permanently retired (is_completed=True) and will "
            "not appear in future schedules.  "
            "Daily tasks have their due_date advanced by one day so they resurface "
            "in tomorrow's get_all_tasks call; is_completed stays False.  "
            "Weekly tasks have due_date advanced by seven days on the same logic.  "
            "Only call this tool for tasks currently in the actionable list.  "
            "Calling it on an already-completed task returns a failure response."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pet_name": {
                    "type": "string",
                    "description": "Name of the pet that owns the task.",
                },
                "task_name": {
                    "type": "string",
                    "description": "Exact name of the task to mark complete.",
                },
            },
            "required": ["pet_name", "task_name"],
        },
    },
    # ── Tool 7 ──────────────────────────────────────────────────────────────
    {
        "name": "add_pet",
        "description": (
            "Register a new pet for the owner.  Call this tool when the owner "
            "mentions a pet that does not yet exist in the system and confirms "
            "they want it added.  After calling add_pet you can immediately call "
            "add_task to attach tasks to the new pet.  Pet names are used as the "
            "primary identifier when routing tasks, so duplicates are rejected."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The pet's name — must be unique across the owner's roster.",
                },
                "species": {
                    "type": "string",
                    "description": (
                        "Species of the pet (e.g. 'dog', 'cat', 'rabbit', "
                        "'hamster', 'fish', 'bird', 'other')."
                    ),
                },
                "age": {
                    "type": "integer",
                    "description": "Age of the pet in whole years (0 or greater).",
                },
            },
            "required": ["name", "species", "age"],
        },
    },
    # ── Tool 8 ──────────────────────────────────────────────────────────────
    {
        "name": "filter_tasks",
        "description": (
            "Query the owner's tasks with optional filters.  Returns tasks that "
            "satisfy all supplied criteria; omitting a parameter leaves that "
            "dimension unrestricted.  Every returned task dict includes 'pet_name' "
            "for ownership traceability.  "
            "Typical uses: filter_tasks() for all tasks; "
            "filter_tasks(pet_name='Buddy') for one pet; "
            "filter_tasks(is_completed=False) for all pending tasks; "
            "filter_tasks(pet_name='Mochi', is_completed=True) for completed "
            "tasks on a specific pet."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pet_name": {
                    "type": "string",
                    "description": (
                        "Restrict results to this pet only.  Omit to include "
                        "tasks from all pets."
                    ),
                },
                "is_completed": {
                    "type": "boolean",
                    "description": (
                        "True returns only retired tasks; false returns only active "
                        "tasks; omit to return tasks in any completion state."
                    ),
                },
            },
            "required": [],
        },
    },
    # ── Tool 9 ──────────────────────────────────────────────────────────────
    {
        "name": "save_state",
        "description": (
            "Persist the current owner, pet, and task graph to disk as JSON.  "
            "Call this tool at the end of every agent turn that modifies state "
            "(add_task, reschedule_task, complete_task, add_pet) to ensure "
            "changes survive a browser reload.  Parent directories are created "
            "automatically if they do not exist.  The file path defaults to "
            "'data/data.json'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Destination file path.  Defaults to 'data/data.json' "
                        "when omitted."
                    ),
                },
            },
            "required": [],
        },
    },
]


# ---------------------------------------------------------------------------
# PawPalTools — LLM-callable tool registry (Tools 1–9)
# ---------------------------------------------------------------------------


class PawPalTools:
    """Dispatches LLM tool-use calls against the live :class:`~pawpal_system.Owner`.

    Instantiate once per Streamlit session or orchestrator run by passing the
    current ``Owner`` object.  Each public method maps one-to-one to an entry
    in :data:`TOOL_SCHEMAS` and accepts the exact JSON keys defined there.

    The Orchestrator should dispatch ``tool_use`` blocks from the LLM like
    this::

        tools = PawPalTools(st.session_state.owner_data)
        result = tools.dispatch(tool_use_block["name"], tool_use_block["input"])

    Every method returns a plain ``dict`` with JSON-serialisable values, ready
    to be wrapped in an Anthropic ``tool_result`` content block.

    Parameters
    ----------
    owner:
        The live ``Owner`` object shared with Streamlit's session state.
        Tool methods mutate or read this object in place, so changes are
        immediately visible in the UI without an explicit reload.
    """

    def __init__(self, owner: Owner) -> None:
        self.owner = owner
        # Reuse a single Scheduler instance; detect_conflicts is stateless
        # with respect to self.owner so sharing is safe.
        self._scheduler = Scheduler(owner)

    # ------------------------------------------------------------------
    # Tool 1 — get_all_tasks
    # ------------------------------------------------------------------

    def get_all_tasks(self) -> dict[str, Any]:
        """Return all tasks that are actionable today.

        Iterates every pet in the owner's roster and collects tasks whose
        ``due_date`` is today or earlier and whose ``is_completed`` flag is
        ``False``.  The result augments each task dict with a ``"pet_name"``
        key so the caller can always trace which pet a task belongs to without
        a second query.

        This is the canonical source of truth for the scheduling session.
        Call it before ``generate_schedule`` when you need to reason about
        what tasks exist before deciding how to order or schedule them.

        Returns
        -------
        dict
            ``{"tasks": list[dict], "count": int}``

            * ``tasks`` — list of task dicts, each containing all
              :class:`~pawpal_system.Task` fields (name, duration, priority,
              is_required, is_completed, start_time, frequency, due_date)
              plus ``"pet_name"``.
            * ``count`` — number of actionable tasks (convenience field;
              equals ``len(tasks)``).
        """
        today = date.today()
        result: list[dict[str, Any]] = []
        for pet in self.owner.pets:
            for task in pet.tasks:
                if task.due_date <= today and not task.is_completed:
                    entry = task.to_dict()
                    entry["pet_name"] = pet.name
                    result.append(entry)
        return {"tasks": result, "count": len(result)}

    # ------------------------------------------------------------------
    # Tool 2 — generate_schedule
    # ------------------------------------------------------------------

    def generate_schedule(self) -> dict[str, Any]:
        """Run the two-phase deterministic scheduler and return the full result.

        Invokes :meth:`~pawpal_system.Scheduler.generate_schedule` against the
        current owner state and serialises the :class:`~pawpal_system.ScheduleResult`
        into a plain dict.

        **Phase 1 — Required tasks:** All ``is_required=True`` tasks are
        unconditionally scheduled, even when their combined duration exceeds
        ``available_time_mins``.  A *Time Deficit* note is appended to
        ``reasoning`` in that case.

        **Phase 2 — Optional tasks:** The remaining budget is filled greedily
        with optional tasks sorted by ``priority`` descending; ties are broken
        by ``duration`` ascending.  Tasks that cannot fit are placed in
        ``skipped_tasks``.

        **Conflict scan:** A sweep-line pass runs after both phases.  Any pair
        of tasks whose ``[start_time, end_time)`` windows overlap produces a
        ``WARNING`` entry in ``reasoning``.

        When ``reasoning`` contains ``"WARNING"``, the caller should invoke
        ``detect_conflicts`` on the returned ``scheduled_tasks`` and enter the
        Resolution Loop.

        Returns
        -------
        dict
            ``{"scheduled_tasks": list[dict], "skipped_tasks": list[dict],
            "total_time_used": int, "reasoning": str}``
        """
        scheduler = Scheduler(self.owner)
        sr = scheduler.generate_schedule()

        # Build an id → pet_name map before serialisation.  The Scheduler
        # returns direct object references from owner.pets, so id() is stable.
        id_to_pet: dict[int, str] = {
            id(task): pet.name
            for pet in self.owner.pets
            for task in pet.tasks
        }

        def _enrich(task_obj: Task) -> dict:
            d = task_obj.to_dict()
            d["pet_name"] = id_to_pet.get(id(task_obj), "")
            return d

        return {
            "scheduled_tasks": [_enrich(t) for t in sr.scheduled_tasks],
            "skipped_tasks":   [_enrich(t) for t in sr.skipped_tasks],
            "total_time_used": sr.total_time_used,
            "reasoning":       sr.reasoning,
        }

    # ------------------------------------------------------------------
    # Tool 3 — detect_conflicts
    # ------------------------------------------------------------------

    def detect_conflicts(self, tasks: list[dict]) -> dict[str, Any]:
        """Identify overlapping time windows in a list of tasks.

        Reconstructs :class:`~pawpal_system.Task` objects from the supplied
        dicts and runs the sweep-line conflict algorithm.  Tasks without a
        ``start_time`` value are silently excluded from the comparison.  Two
        tasks conflict when the later task's ``start_time`` is strictly less
        than the earlier task's ``end_time`` (closed-open interval semantics).

        Known limitation: the sort key is the ``HH:MM`` string, so overlaps
        that cross midnight (e.g. 23:50 → 00:20) are not detected.  See the
        ``test_midnight_rollover_known_failure`` test for details.

        Call this tool:

        * **After** ``generate_schedule`` to decide whether to enter the
          Resolution Loop.
        * **After every** ``reschedule_task`` call to verify the shift
          resolved the targeted conflict and did not create new ones.

        Parameters
        ----------
        tasks:
            List of task dicts, each containing at minimum ``"name"``,
            ``"duration"``, and ``"start_time"`` fields.  Pass the
            ``"scheduled_tasks"`` list from a ``generate_schedule`` or
            ``reschedule_task`` response.

        Returns
        -------
        dict
            ``{"conflicts": list[dict], "conflict_count": int}``

            Each entry in ``conflicts`` is
            ``{"task_a": dict, "task_b": dict}`` where ``task_a`` ends after
            ``task_b`` begins.  An empty ``conflicts`` list means the schedule
            is clean.
        """
        try:
            task_objects = [Task.from_dict(t) for t in tasks]
        except (KeyError, ValueError) as exc:
            logger.error(
                "detect_conflicts: failed to reconstruct Task from dict: %s", exc
            )
            return {"conflicts": [], "conflict_count": 0}
        pairs = self._scheduler.detect_conflicts(task_objects)
        return {
            "conflicts": [
                {"task_a": a.to_dict(), "task_b": b.to_dict()}
                for a, b in pairs
            ],
            "conflict_count": len(pairs),
        }

    # ------------------------------------------------------------------
    # Tool 4 — add_task
    # ------------------------------------------------------------------

    def add_task(
        self,
        pet_name: str,
        name: str,
        duration: int,
        priority: int,
        is_required: bool = False,
        start_time: Optional[str] = None,
        frequency: str = "one-off",
        due_date: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create a new care task and assign it to a pet.

        Constructs a :class:`~pawpal_system.Task` from the supplied fields and
        appends it to the named pet's ``tasks`` list.  The task enters the
        scheduler's view the next time ``generate_schedule`` or
        ``get_all_tasks`` is called, provided ``due_date`` is today or earlier.

        **Important — call discipline:**

        Do **not** invoke this tool until every required field has been
        confirmed with the owner.  If any field is ambiguous (e.g. the owner
        said "feed Buddy" without specifying duration), emit a clarification
        question and wait for the response before calling this tool.

        Priority inference guide (use when the owner does not state a number):

        ====  ===================================================
        5     "critical", "must", "medication", "vet", "required"
        4     "important", "don't forget", "high priority"
        3     "normal", "usual", "regular" *(default when unclear)*
        2     "low", "when you get a chance", "if possible"
        1     "whenever", "optional", "nice to have"
        ====  ===================================================

        Parameters
        ----------
        pet_name:
            Exact name of the pet as registered in the system.  The lookup is
            case-sensitive.
        name:
            Short descriptive task title (e.g. ``"Morning Walk"``).
        duration:
            Time required in whole minutes.  Must be ≥ 1.
        priority:
            Urgency level as an integer from 1 to 5 inclusive.
        is_required:
            ``True`` when the task must run today regardless of budget
            (e.g. daily medication).  Defaults to ``False``.
        start_time:
            Preferred wall-clock start in ``HH:MM`` 24-hour format, or
            ``None`` if the owner did not specify a time.
        frequency:
            Recurrence pattern — ``"one-off"`` (default), ``"daily"``, or
            ``"weekly"``.
        due_date:
            ISO-8601 date string (``YYYY-MM-DD``).  Defaults to today when
            omitted.

        Returns
        -------
        dict
            On success: ``{"success": True, "task": dict, "assigned_to": str}``

            On failure: ``{"success": False, "error": str}``
        """
        pet = next((p for p in self.owner.pets if p.name == pet_name), None)
        if pet is None:
            return {
                "success": False,
                "error": (
                    f"No pet named '{pet_name}' found.  "
                    f"Known pets: {[p.name for p in self.owner.pets]}"
                ),
            }

        if duration < 1:
            return {"success": False, "error": "duration must be at least 1 minute."}

        if not (1 <= priority <= 5):
            return {"success": False, "error": "priority must be an integer from 1 to 5."}

        if start_time is not None:
            try:
                datetime.strptime(start_time, "%H:%M")
            except ValueError:
                return {
                    "success": False,
                    "error": (
                        f"Invalid start_time '{start_time}'.  "
                        "Use HH:MM 24-hour format (e.g. '08:30')."
                    ),
                }

        task_due = date.fromisoformat(due_date) if due_date else date.today()
        task = Task(
            name=name,
            duration=duration,
            priority=priority,
            is_required=is_required,
            start_time=start_time,
            frequency=frequency,
            due_date=task_due,
        )
        pet.tasks.append(task)
        logger.info("add_task: '%s' → pet '%s' (priority=%d).", name, pet_name, priority)
        return {"success": True, "task": task.to_dict(), "assigned_to": pet_name}

    # ------------------------------------------------------------------
    # Tool 5 — reschedule_task
    # ------------------------------------------------------------------

    def reschedule_task(
        self,
        pet_name: str,
        task_name: str,
        new_start_time: str,
    ) -> dict[str, Any]:
        """Update a task's start_time to resolve a scheduling conflict.

        This is the **primary — and only — mutation** available to the agent
        during the Resolution Loop.  It sets a new ``start_time`` on the
        matched task and returns the updated task dict.  The caller must then
        pass the full updated schedule to ``detect_conflicts`` to verify the
        shift did not introduce new overlaps.

        Hard constraints the agent MUST respect
        ----------------------------------------
        * **Do not change** ``duration`` — altering it would corrupt the
          time-budget accounting.
        * **Do not change** ``priority`` — doing so would override the
          owner's stated urgency ordering.
        * **Do not change** ``is_required`` — removing the required flag
          would bypass the safety guardrail.

        Resolution heuristics
        ---------------------
        1. Prefer shifting the lower-priority task rather than the
           higher-priority one.
        2. When both conflicting tasks are required, prefer shifting the
           shorter one (smaller budget impact).
        3. Setting ``new_start_time = task_a.end_time`` is always safe for
           the immediate pair — but always call ``detect_conflicts`` on the
           whole schedule afterwards to catch cascading overlaps.

        Parameters
        ----------
        pet_name:
            Name of the pet that owns the task.
        task_name:
            Exact name of the task to reschedule.  Case-sensitive.
        new_start_time:
            New start time in ``HH:MM`` 24-hour format (e.g. ``"09:30"``).

        Returns
        -------
        dict
            On success:
            ``{"success": True, "updated_task": dict, "previous_start_time": str | None}``

            On failure: ``{"success": False, "error": str}``
        """
        try:
            datetime.strptime(new_start_time, "%H:%M")
        except ValueError:
            return {
                "success": False,
                "error": (
                    f"Invalid new_start_time '{new_start_time}'.  "
                    "Use HH:MM 24-hour format (e.g. '09:30')."
                ),
            }

        for pet in self.owner.pets:
            if pet.name != pet_name:
                continue
            for task in pet.tasks:
                if task.name == task_name:
                    previous = task.start_time
                    task.start_time = new_start_time
                    logger.info(
                        "reschedule_task: '%s' on '%s'  %s → %s.",
                        task_name, pet_name, previous, new_start_time,
                    )
                    return {
                        "success": True,
                        "updated_task": task.to_dict(),
                        "previous_start_time": previous,
                    }

        return {
            "success": False,
            "error": f"Task '{task_name}' not found on pet '{pet_name}'.",
        }

    # ------------------------------------------------------------------
    # Tool 6 — complete_task
    # ------------------------------------------------------------------

    def complete_task(self, pet_name: str, task_name: str) -> dict[str, Any]:
        """Mark a task done with correct recurrence-advance logic.

        Delegates to :meth:`~pawpal_system.Pet.complete_task`, which
        implements the three-way recurrence contract:

        ``"one-off"``
            ``is_completed`` is set to ``True``.  The task is permanently
            retired and will not appear in future ``get_all_tasks`` calls.

        ``"daily"``
            ``due_date`` advances by one day so the task resurfaces in
            tomorrow's schedule.  ``is_completed`` stays ``False``.

        ``"weekly"``
            ``due_date`` advances by seven days.  Same logic as daily, but
            on a weekly cycle.

        Only call this tool for tasks currently returned by ``get_all_tasks``.
        Calling it on a task that is already retired (``is_completed=True``)
        returns a failure response.

        Parameters
        ----------
        pet_name:
            Name of the pet that owns the task.
        task_name:
            Exact name of the task to complete.

        Returns
        -------
        dict
            On success:
            ``{"success": True, "frequency": str, "next_due_date": str | None,
            "retired": bool}``

            * ``next_due_date`` — ISO-8601 date of the next occurrence for
              recurring tasks, or ``None`` for one-off tasks.
            * ``retired`` — ``True`` only for one-off tasks after completion.

            On failure: ``{"success": False, "error": str}``
        """
        for pet in self.owner.pets:
            if pet.name != pet_name:
                continue
            for task in pet.tasks:
                if task.name == task_name and not task.is_completed:
                    pet.complete_task(task)
                    logger.info(
                        "complete_task: '%s' on '%s' (frequency=%s).",
                        task_name, pet_name, task.frequency,
                    )
                    return {
                        "success": True,
                        "frequency": task.frequency,
                        "next_due_date": (
                            task.due_date.isoformat()
                            if task.frequency != "one-off"
                            else None
                        ),
                        "retired": task.is_completed,
                    }

        return {
            "success": False,
            "error": (
                f"Task '{task_name}' not found or already completed "
                f"on pet '{pet_name}'."
            ),
        }

    # ------------------------------------------------------------------
    # Tool 7 — add_pet
    # ------------------------------------------------------------------

    def add_pet(self, name: str, species: str, age: int) -> dict[str, Any]:
        """Register a new pet for the owner.

        Creates a :class:`~pawpal_system.Pet` with an empty task list and
        appends it to the owner's roster.  After this call you can immediately
        invoke ``add_task`` to attach tasks to the new pet.

        Pet names act as the primary identifier when routing tasks.  Before
        calling this tool, confirm with the owner that the named pet does not
        already exist — duplicate names are rejected.

        Parameters
        ----------
        name:
            The pet's name.  Must be unique across the owner's roster
            (case-sensitive match).
        species:
            Species of the pet (e.g. ``"dog"``, ``"cat"``, ``"rabbit"``,
            ``"hamster"``, ``"fish"``, ``"bird"``, ``"other"``).
        age:
            Age of the pet in whole years.  Must be 0 or greater.

        Returns
        -------
        dict
            On success: ``{"success": True, "pet_summary": str}``

            On failure: ``{"success": False, "error": str}``
        """
        if any(p.name == name for p in self.owner.pets):
            return {"success": False, "error": f"A pet named '{name}' already exists."}

        if age < 0:
            return {"success": False, "error": "age must be 0 or greater."}

        pet = Pet(name=name, species=species, age=age)
        self.owner.pets.append(pet)
        logger.info("add_pet: '%s' (%s, age %d) registered.", name, species, age)
        return {"success": True, "pet_summary": pet.get_summary()}

    # ------------------------------------------------------------------
    # Tool 8 — filter_tasks
    # ------------------------------------------------------------------

    def filter_tasks(
        self,
        pet_name: Optional[str] = None,
        is_completed: Optional[bool] = None,
    ) -> dict[str, Any]:
        """Query the owner's tasks with optional filters.

        Returns every task that satisfies **all** supplied filter criteria.
        Omitting a parameter leaves that dimension unrestricted (all values
        pass).  Every returned task dict includes ``"pet_name"`` for
        ownership traceability, allowing the caller to route follow-up
        ``complete_task`` or ``reschedule_task`` calls without a second
        lookup.

        Common query patterns
        ---------------------
        * ``filter_tasks()`` — every task across all pets in any state.
        * ``filter_tasks(pet_name="Buddy")`` — all tasks for Buddy.
        * ``filter_tasks(is_completed=False)`` — all outstanding tasks.
        * ``filter_tasks(pet_name="Mochi", is_completed=True)`` — retired
          tasks for Mochi only.

        Parameters
        ----------
        pet_name:
            Restrict results to this pet only.  ``None`` (default) includes
            tasks from all pets.
        is_completed:
            ``True`` returns only retired tasks; ``False`` returns only active
            tasks; ``None`` (default) returns tasks in any completion state.

        Returns
        -------
        dict
            ``{"tasks": list[dict], "count": int}``

            Each task dict contains all :class:`~pawpal_system.Task` fields
            plus ``"pet_name"``.
        """
        result: list[dict[str, Any]] = []
        for pet in self.owner.pets:
            if pet_name is not None and pet.name != pet_name:
                continue
            for task in pet.tasks:
                if is_completed is not None and task.is_completed != is_completed:
                    continue
                entry = task.to_dict()
                entry["pet_name"] = pet.name
                result.append(entry)
        return {"tasks": result, "count": len(result)}

    # ------------------------------------------------------------------
    # Tool 9 — save_state
    # ------------------------------------------------------------------

    def save_state(self, path: str = "data/data.json") -> dict[str, Any]:
        """Persist the current owner graph to disk as JSON.

        Serialises the full :class:`~pawpal_system.Owner` — including every
        pet and all of their tasks — via
        :meth:`~pawpal_system.Owner.save_to_json`.  Parent directories are
        created automatically if they do not exist.  The Streamlit UI
        rehydrates from this file on the next page load, making this call
        the programmatic equivalent of clicking *Save Data* in the UI.

        **Call discipline:** invoke this tool at the end of every agent turn
        that mutates state (``add_task``, ``reschedule_task``,
        ``complete_task``, ``add_pet``) to ensure no changes are silently
        lost on a browser reload.

        Parameters
        ----------
        path:
            Destination file path.  Defaults to ``"data/data.json"``.

        Returns
        -------
        dict
            On success: ``{"success": True, "path": str}``

            On failure: ``{"success": False, "error": str}``
        """
        try:
            self.owner.save_to_json(path)
            logger.info("save_state: owner graph persisted to '%s'.", path)
            return {"success": True, "path": path}
        except Exception as exc:  # noqa: BLE001
            logger.error("save_state failed: %s", exc)
            return {"success": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Orchestrator dispatcher
    # ------------------------------------------------------------------

    def dispatch(self, tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        """Route an LLM ``tool_use`` block to the correct method.

        Looks up ``tool_name`` on this instance, validates it is an
        LLM-callable tool (i.e. present in :data:`TOOL_SCHEMAS`), and calls
        it with the unpacked ``tool_input`` dict.  Returns the method's result
        dict ready to be wrapped in an Anthropic ``tool_result`` content block.

        ``validate_required_tasks`` is intentionally not reachable through
        this dispatcher — it lives outside the class and must be called by the
        Orchestrator directly.

        Parameters
        ----------
        tool_name:
            The ``"name"`` field from the LLM ``tool_use`` block.
        tool_input:
            The ``"input"`` field from the LLM ``tool_use`` block.

        Returns
        -------
        dict
            The tool's JSON-serialisable response dict.

        Raises
        ------
        ValueError
            When ``tool_name`` does not correspond to any LLM-callable method.
        """
        _callable_names = {s["name"] for s in TOOL_SCHEMAS}
        if tool_name not in _callable_names:
            raise ValueError(
                f"Unknown or non-LLM-callable tool '{tool_name}'.  "
                f"Available tools: {sorted(_callable_names)}"
            )
        method = getattr(self, tool_name)
        try:
            return method(**tool_input)
        except TypeError as exc:
            logger.error(
                "dispatch: TypeError calling '%s' with input %s: %s",
                tool_name, tool_input, exc,
            )
            return {
                "success": False,
                "error": (
                    f"Tool '{tool_name}' received invalid or missing parameters: {exc}"
                ),
            }


# ---------------------------------------------------------------------------
# Tool 10 — validate_required_tasks  (NOT LLM-callable — guardrail utility)
# ---------------------------------------------------------------------------


def validate_required_tasks(
    proposed_schedule: dict[str, Any],
    owner: Owner,
) -> dict[str, Any]:
    """Verify that all required tasks survived the LLM's schedule mutation.

    .. danger::
        **This function is NOT part of the LLM's toolset.**

        It is absent from :data:`TOOL_SCHEMAS` by design and must be called
        **exclusively** by the Orchestrator, never by the LLM.  This makes
        the safety check injection-proof: a compromised or adversarial prompt
        cannot instruct the model to skip or weaken this guardrail.

    The function derives the authoritative set of required tasks directly from
    the ``owner`` object — not from ``proposed_schedule`` — and checks that
    every ``is_required=True`` task that is due today appears in
    ``proposed_schedule["scheduled_tasks"]``.

    When any required task is missing it is:

    1. Named in the ``violations`` list.
    2. Prepended to ``corrected_schedule["scheduled_tasks"]`` (required tasks
       always lead the schedule).
    3. Logged at ``WARNING`` level as a ``GUARDRAIL_VIOLATION`` event.

    The ``corrected_schedule`` dict is returned unconditionally — callers
    should always use ``corrected_schedule`` rather than the raw
    ``proposed_schedule`` as the source of truth for the UI.

    Parameters
    ----------
    proposed_schedule:
        A dict in the shape returned by :meth:`PawPalTools.generate_schedule`
        — must contain a ``"scheduled_tasks"`` key holding a list of task
        dicts.  This is the LLM's final output before it reaches the UI.
    owner:
        The live :class:`~pawpal_system.Owner` object.  Required tasks are
        re-derived from this object to guarantee the check cannot be spoofed
        via the ``proposed_schedule`` payload.

    Returns
    -------
    dict
        ``{"violations": list[str], "corrected_schedule": dict,
        "guardrail_triggered": bool}``

        * ``violations`` — names of required tasks that were absent from
          ``proposed_schedule``.  Empty list when the guardrail passes
          cleanly.
        * ``corrected_schedule`` — a copy of ``proposed_schedule`` with any
          missing required tasks prepended to ``"scheduled_tasks"``.
        * ``guardrail_triggered`` — ``True`` if at least one violation was
          found and corrected.

    Examples
    --------
    Typical Orchestrator usage::

        result = validate_required_tasks(proposed_schedule, owner)
        if result["guardrail_triggered"]:
            st.warning(
                f"Guardrail corrected {len(result['violations'])} "
                f"dropped required task(s): {result['violations']}"
            )
        final_schedule = result["corrected_schedule"]
    """
    today = date.today()

    # Build the authoritative (pet_name, task_name) set from the owner object —
    # NOT from proposed_schedule.  This makes the check injection-proof.
    authoritative_required: list[tuple[str, Task]] = [
        (pet.name, task)
        for pet in owner.pets
        for task in pet.tasks
        if task.is_required and task.due_date <= today and not task.is_completed
    ]

    scheduled_tasks = proposed_schedule.get("scheduled_tasks", [])

    # Prefer tuple matching when pet_name is present in the schedule dicts
    # (set by PawPalTools.generate_schedule).  Fall back to name-only matching
    # for legacy schedules that pre-date the pet_name addition so that the
    # guardrail never silently degrades.
    has_pet_names = any(t.get("pet_name") for t in scheduled_tasks)
    if has_pet_names:
        scheduled_keys: set[tuple[str, str]] = {
            (t.get("pet_name", ""), t.get("name", ""))
            for t in scheduled_tasks
        }
    else:
        scheduled_name_set: set[str] = {t.get("name", "") for t in scheduled_tasks}

    violations: list[str] = []
    restored: list[dict[str, Any]] = []

    for pet_name, task in authoritative_required:
        if has_pet_names:
            missing = (pet_name, task.name) not in scheduled_keys
        else:
            missing = task.name not in scheduled_name_set

        if missing:
            violations.append(task.name)
            task_dict = task.to_dict()
            task_dict["pet_name"] = pet_name  # keep pet_name in restored entry
            restored.append(task_dict)
            logger.warning(
                "GUARDRAIL_VIOLATION: required task '%s' on pet '%s' was absent "
                "from the LLM-proposed schedule and has been auto-restored.",
                task.name, pet_name,
            )

    # Prepend restored tasks so required items always lead the schedule.
    corrected_scheduled = restored + list(scheduled_tasks)
    corrected_schedule = {
        **proposed_schedule,
        "scheduled_tasks": corrected_scheduled,
    }

    return {
        "violations": violations,
        "corrected_schedule": corrected_schedule,
        "guardrail_triggered": bool(violations),
    }
