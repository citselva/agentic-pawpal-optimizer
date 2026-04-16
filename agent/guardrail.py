"""agent/guardrail.py — Guardrail Layer.

This module owns the CorrectionResult contract and the audit trail.

The core algorithm lives in :func:`agent.tools.validate_required_tasks` — it
is intentionally kept there so Tool 10 stays co-located with the rest of the
tool layer and remains absent from TOOL_SCHEMAS.  This module wraps that
function in a typed result object and persists every violation to a
newline-delimited JSON audit log, giving every LLM correction a permanent,
time-stamped record.

This module MUST NOT import ``anthropic`` or call any LLM.  It is synchronous
and runs in the critical path between the Resolution Loop and the UI update.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pawpal_system import Owner
from agent.tools import validate_required_tasks as _core_validate

logger = logging.getLogger(__name__)

# Append-only JSONL file — one record per triggered guardrail event.
VIOLATION_LOG_PATH: Path = Path("data/guardrail_violations.jsonl")


# ---------------------------------------------------------------------------
# CorrectionResult
# ---------------------------------------------------------------------------


@dataclass
class CorrectionResult:
    """Typed result returned by :func:`run_guardrail`.

    Attributes
    ----------
    violations:
        Names of required tasks that were absent from the LLM's proposed
        schedule and have been restored.  Empty when the guardrail passes
        cleanly.
    corrected_schedule:
        The final, safe schedule dict — identical to ``proposed_schedule``
        when ``guardrail_triggered`` is ``False``, otherwise a copy with the
        missing required tasks prepended to ``"scheduled_tasks"``.
    guardrail_triggered:
        ``True`` if at least one required task was missing and had to be
        restored.  Shorthand for ``bool(violations)``.
    timestamp:
        ISO-8601 UTC timestamp of the check, set at object creation time.
        Included in the audit log so violations are traceable across sessions.
    """

    violations: list[str]
    corrected_schedule: dict[str, Any]
    guardrail_triggered: bool
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # ------------------------------------------------------------------
    # Convenience helpers used by the Streamlit UI and tests
    # ------------------------------------------------------------------

    @property
    def is_clean(self) -> bool:
        """``True`` when no required tasks were dropped (guardrail did not fire)."""
        return not self.guardrail_triggered

    @property
    def violation_count(self) -> int:
        """Number of required tasks that were missing from the proposed schedule."""
        return len(self.violations)

    def as_ui_message(self) -> str:
        """Return a single human-readable line suitable for a Streamlit alert.

        Returns an empty string when no violation occurred so the caller can
        gate on truthiness::

            msg = result.as_ui_message()
            if msg:
                st.error(msg)
        """
        if not self.guardrail_triggered:
            return ""
        names = ", ".join(f"'{v}'" for v in self.violations)
        return (
            f"Guardrail correction applied: {self.violation_count} required task(s) "
            f"were absent from the AI-proposed schedule and have been automatically "
            f"restored — {names}."
        )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_guardrail(
    proposed_schedule: dict[str, Any],
    owner: Owner,
) -> CorrectionResult:
    """Verify proposed_schedule against owner's required tasks and fix violations.

    This is the single entry point the Orchestrator calls after the Resolution
    Loop completes.  It delegates the algorithm to
    :func:`agent.tools.validate_required_tasks` (which is injection-proof
    because it derives the required-task set from ``owner``, never from
    ``proposed_schedule``), wraps the result in a :class:`CorrectionResult`,
    and persists any violation event to :data:`VIOLATION_LOG_PATH`.

    Parameters
    ----------
    proposed_schedule:
        The schedule dict produced by the LLM Resolution Loop.  Must contain
        ``"scheduled_tasks": list[dict]``.
    owner:
        The live :class:`~pawpal_system.Owner` object.  Used as the
        authoritative source for which tasks are required today.

    Returns
    -------
    CorrectionResult
        Always returns a ``CorrectionResult``.  Callers should use
        ``result.corrected_schedule`` rather than ``proposed_schedule`` as
        the source of truth for the UI.

    Side effects
    ------------
    When ``guardrail_triggered`` is ``True``, appends one JSON record to
    :data:`VIOLATION_LOG_PATH` (``data/guardrail_violations.jsonl``).
    The record is written with ``mode="a"`` so multiple sessions accumulate
    in the same file.  Parent directories are created if absent.
    """
    raw = _core_validate(proposed_schedule, owner)

    result = CorrectionResult(
        violations=raw["violations"],
        corrected_schedule=raw["corrected_schedule"],
        guardrail_triggered=raw["guardrail_triggered"],
    )

    if result.guardrail_triggered:
        _append_violation_log(result, proposed_schedule, owner)

    return result


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------


def _append_violation_log(
    result: CorrectionResult,
    proposed_schedule: dict[str, Any],
    owner: Owner,
) -> None:
    """Append one GUARDRAIL_VIOLATION record to the JSONL audit log.

    Each record is a single JSON object on its own line so the file can be
    read incrementally without loading the entire history.  The record
    includes both the proposed and corrected task-name lists so a human
    auditor can see exactly what the LLM dropped and what was restored.

    Failures are logged at ERROR level but not re-raised — a logging failure
    must never block the schedule from reaching the UI.

    Parameters
    ----------
    result:
        The :class:`CorrectionResult` describing the violation.
    proposed_schedule:
        The LLM's original (uncorrected) schedule dict.
    owner:
        Used to record the owner's name in the audit record.
    """
    record = {
        "event": "GUARDRAIL_VIOLATION",
        "timestamp": result.timestamp,
        "owner_name": owner.name,
        "violation_count": result.violation_count,
        "missing_required_tasks": result.violations,
        "proposed_scheduled_task_names": [
            t.get("name", "<unknown>")
            for t in proposed_schedule.get("scheduled_tasks", [])
        ],
        "corrected_scheduled_task_names": [
            t.get("name", "<unknown>")
            for t in result.corrected_schedule.get("scheduled_tasks", [])
        ],
    }

    try:
        VIOLATION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with VIOLATION_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        logger.info(
            "GUARDRAIL_VIOLATION logged: %d task(s) restored for owner '%s'.",
            result.violation_count,
            owner.name,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Failed to write guardrail violation log to '%s': %s",
            VIOLATION_LOG_PATH,
            exc,
        )
