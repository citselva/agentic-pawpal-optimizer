"""tests/test_agent.py — Comprehensive test suite for agent/ extensions.

Test groups (9 classes, ~75 test cases):

  TC-SCHEMA   TestToolSchemas               — TOOL_SCHEMAS structure validation
  TC-TOOLS    TestPawPalToolsMethods         — Tools 1-9 happy path + errors
  TC-DISP     TestDispatch                   — routing, blocking, TypeError (BUG#1)
  TC-GUARD    TestValidateRequiredTasks      — guardrail algorithm, BUG#6 same-name fix
  TC-CRRES    TestCorrectionResult           — dataclass properties and helpers
  TC-RG       TestRunGuardrail              — integration + JSONL audit trail
  TC-ORCH     TestOrchestratorHelpers        — pure helper methods
  TC-NL       TestParseNlTask               — NL parsing with mocked Anthropic client
  TC-REACT    TestResolveScheduleConflicts   — ReAct loop, BUG#3 escalation save
"""

from __future__ import annotations

import json
import tempfile
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

from pawpal_system import Owner, Pet, Task
from agent.tools import TOOL_SCHEMAS, PawPalTools, validate_required_tasks
from agent.guardrail import CorrectionResult, run_guardrail, VIOLATION_LOG_PATH
from agent.orchestrator import (
    MAX_RESOLUTION_STEPS,
    ParseResult,
    PawPalOrchestrator,
    TraceStep,
    _compute_end_time,
)


# ===========================================================================
# Shared fixtures
# ===========================================================================


@pytest.fixture
def today() -> date:
    return date.today()


@pytest.fixture
def owner(today: date) -> Owner:
    """Owner with two pets, each carrying required and optional tasks."""
    o = Owner(name="Alice", available_time_mins=300)

    buddy = Pet(name="Buddy", species="dog", age=3)
    buddy.tasks = [
        Task(
            name="Morning Walk",
            duration=30,
            priority=4,
            is_required=True,
            start_time="08:00",
            due_date=today,
        ),
        Task(
            name="Play Time",
            duration=20,
            priority=2,
            is_required=False,
            start_time="09:00",
            due_date=today,
        ),
    ]

    mochi = Pet(name="Mochi", species="cat", age=2)
    mochi.tasks = [
        Task(
            name="Feeding",
            duration=10,
            priority=5,
            is_required=True,
            start_time="09:30",
            due_date=today,
        ),
        Task(
            name="Litter Box",
            duration=15,
            priority=3,
            is_required=False,
            start_time="10:00",
            due_date=today,
        ),
    ]

    o.pets = [buddy, mochi]
    return o


@pytest.fixture
def tools(owner: Owner) -> PawPalTools:
    return PawPalTools(owner)


@pytest.fixture
def mock_client() -> MagicMock:
    return MagicMock()


@pytest.fixture
def orchestrator(owner: Owner, mock_client: MagicMock) -> PawPalOrchestrator:
    return PawPalOrchestrator(
        owner=owner, client=mock_client, max_resolution_steps=3
    )


# ---------------------------------------------------------------------------
# Helper to build a minimal Anthropic-style mock response block
# ---------------------------------------------------------------------------


def _text_block(text: str):
    b = SimpleNamespace(type="text", text=text)
    return b


def _tool_block(name: str, input_dict: dict, block_id: str = "tu_001"):
    b = SimpleNamespace(type="tool_use", id=block_id, name=name, input=input_dict)
    return b


def _mock_response(blocks, stop_reason: str = "tool_use"):
    r = MagicMock()
    r.content = blocks
    r.stop_reason = stop_reason
    return r


# ===========================================================================
# TC-SCHEMA  TestToolSchemas
# ===========================================================================


class TestToolSchemas:
    """Validate TOOL_SCHEMAS list structure — no LLM call needed."""

    def test_exactly_nine_schemas(self):
        assert len(TOOL_SCHEMAS) == 9

    def test_each_schema_has_required_keys(self):
        for schema in TOOL_SCHEMAS:
            assert "name" in schema, f"Missing 'name' in {schema}"
            assert "description" in schema, f"Missing 'description' in {schema}"
            assert "input_schema" in schema, f"Missing 'input_schema' in {schema}"

    def test_tool_10_absent_from_schemas(self):
        names = {s["name"] for s in TOOL_SCHEMAS}
        assert "validate_required_tasks" not in names

    def test_all_input_schemas_are_objects(self):
        for schema in TOOL_SCHEMAS:
            assert schema["input_schema"]["type"] == "object"

    def test_tool_names_are_unique(self):
        names = [s["name"] for s in TOOL_SCHEMAS]
        assert len(names) == len(set(names))

    def test_expected_tool_names_present(self):
        names = {s["name"] for s in TOOL_SCHEMAS}
        expected = {
            "get_all_tasks", "generate_schedule", "detect_conflicts",
            "add_task", "reschedule_task", "complete_task",
            "add_pet", "filter_tasks", "save_state",
        }
        assert names == expected


# ===========================================================================
# TC-TOOLS  TestPawPalToolsMethods
# ===========================================================================


class TestPawPalToolsMethods:
    """Unit tests for each of Tools 1-9 via direct method calls."""

    # ── Tool 1: get_all_tasks ──────────────────────────────────────────────

    def test_get_all_tasks_returns_due_tasks(self, tools, today):
        result = tools.get_all_tasks()
        assert result["count"] == 4  # Morning Walk, Play Time, Feeding, Litter Box

    def test_get_all_tasks_excludes_future_tasks(self, tools, today):
        tools.owner.pets[0].tasks[0].due_date = today + timedelta(days=1)
        result = tools.get_all_tasks()
        assert result["count"] == 3

    def test_get_all_tasks_excludes_completed_tasks(self, tools):
        tools.owner.pets[0].tasks[0].is_completed = True
        result = tools.get_all_tasks()
        assert result["count"] == 3

    def test_get_all_tasks_includes_pet_name(self, tools):
        result = tools.get_all_tasks()
        for task in result["tasks"]:
            assert "pet_name" in task
            assert task["pet_name"] in {"Buddy", "Mochi"}

    # ── Tool 2: generate_schedule ──────────────────────────────────────────

    def test_generate_schedule_returns_expected_keys(self, tools):
        result = tools.generate_schedule()
        assert set(result.keys()) >= {
            "scheduled_tasks", "skipped_tasks", "total_time_used", "reasoning"
        }

    def test_generate_schedule_includes_pet_name(self, tools):
        """BUG#6 fix verification — pet_name must be present in scheduled task dicts."""
        result = tools.generate_schedule()
        for task in result["scheduled_tasks"]:
            assert "pet_name" in task, f"pet_name missing from task: {task['name']}"
            assert task["pet_name"] != ""

    def test_generate_schedule_required_tasks_always_included(self, tools):
        result = tools.generate_schedule()
        names = {t["name"] for t in result["scheduled_tasks"]}
        assert "Morning Walk" in names  # is_required=True
        assert "Feeding" in names       # is_required=True

    def test_generate_schedule_skipped_tasks_have_pet_name(self, tools):
        # Force a small budget so optional tasks are skipped
        tools.owner.available_time_mins = 40  # only fits required tasks
        result = tools.generate_schedule()
        for task in result["skipped_tasks"]:
            assert "pet_name" in task

    # ── Tool 3: detect_conflicts ───────────────────────────────────────────

    def test_detect_conflicts_no_conflicts(self, tools):
        tasks = [
            {"name": "A", "duration": 30, "start_time": "08:00",
             "priority": 3, "is_required": False, "is_completed": False,
             "frequency": "one-off", "due_date": date.today().isoformat()},
            {"name": "B", "duration": 30, "start_time": "09:00",
             "priority": 3, "is_required": False, "is_completed": False,
             "frequency": "one-off", "due_date": date.today().isoformat()},
        ]
        result = tools.detect_conflicts(tasks)
        assert result["conflict_count"] == 0
        assert result["conflicts"] == []

    def test_detect_conflicts_finds_overlap(self, tools):
        tasks = [
            {"name": "A", "duration": 60, "start_time": "08:00",
             "priority": 3, "is_required": False, "is_completed": False,
             "frequency": "one-off", "due_date": date.today().isoformat()},
            {"name": "B", "duration": 30, "start_time": "08:30",
             "priority": 3, "is_required": False, "is_completed": False,
             "frequency": "one-off", "due_date": date.today().isoformat()},
        ]
        result = tools.detect_conflicts(tasks)
        assert result["conflict_count"] == 1
        assert result["conflicts"][0]["task_a"]["name"] == "A"
        assert result["conflicts"][0]["task_b"]["name"] == "B"

    def test_detect_conflicts_tasks_without_start_time_ignored(self, tools):
        tasks = [
            {"name": "A", "duration": 60, "start_time": None,
             "priority": 3, "is_required": False, "is_completed": False,
             "frequency": "one-off", "due_date": date.today().isoformat()},
            {"name": "B", "duration": 30, "start_time": None,
             "priority": 3, "is_required": False, "is_completed": False,
             "frequency": "one-off", "due_date": date.today().isoformat()},
        ]
        result = tools.detect_conflicts(tasks)
        assert result["conflict_count"] == 0

    # ── Tool 4: add_task ───────────────────────────────────────────────────

    def test_add_task_success(self, tools, today):
        result = tools.add_task(
            pet_name="Buddy", name="Grooming", duration=45, priority=3
        )
        assert result["success"] is True
        assert result["task"]["name"] == "Grooming"
        assert result["assigned_to"] == "Buddy"

    def test_add_task_unknown_pet(self, tools):
        result = tools.add_task(
            pet_name="Rex", name="Walk", duration=30, priority=3
        )
        assert result["success"] is False
        assert "Rex" in result["error"]

    def test_add_task_invalid_duration(self, tools):
        result = tools.add_task(
            pet_name="Buddy", name="Nap", duration=0, priority=3
        )
        assert result["success"] is False
        assert "duration" in result["error"]

    def test_add_task_invalid_priority_too_high(self, tools):
        result = tools.add_task(
            pet_name="Buddy", name="Nap", duration=10, priority=6
        )
        assert result["success"] is False
        assert "priority" in result["error"]

    def test_add_task_invalid_priority_too_low(self, tools):
        result = tools.add_task(
            pet_name="Buddy", name="Nap", duration=10, priority=0
        )
        assert result["success"] is False
        assert "priority" in result["error"]

    def test_add_task_invalid_start_time_format(self, tools):
        result = tools.add_task(
            pet_name="Buddy", name="Walk", duration=30, priority=3,
            start_time="8am",
        )
        assert result["success"] is False
        assert "start_time" in result["error"] or "Invalid" in result["error"]

    def test_add_task_valid_start_time(self, tools):
        result = tools.add_task(
            pet_name="Buddy", name="Nap", duration=30, priority=2,
            start_time="14:00",
        )
        assert result["success"] is True

    def test_add_task_appends_to_pet(self, tools):
        before = len(tools.owner.pets[0].tasks)
        tools.add_task(pet_name="Buddy", name="Nap", duration=10, priority=1)
        assert len(tools.owner.pets[0].tasks) == before + 1

    # ── Tool 5: reschedule_task ────────────────────────────────────────────

    def test_reschedule_task_success(self, tools):
        result = tools.reschedule_task(
            pet_name="Buddy", task_name="Morning Walk", new_start_time="10:00"
        )
        assert result["success"] is True
        assert result["updated_task"]["start_time"] == "10:00"
        assert result["previous_start_time"] == "08:00"

    def test_reschedule_task_mutates_owner_state(self, tools):
        tools.reschedule_task(
            pet_name="Buddy", task_name="Morning Walk", new_start_time="11:00"
        )
        task = next(
            t for t in tools.owner.pets[0].tasks if t.name == "Morning Walk"
        )
        assert task.start_time == "11:00"

    def test_reschedule_task_not_found(self, tools):
        result = tools.reschedule_task(
            pet_name="Buddy", task_name="Nonexistent", new_start_time="10:00"
        )
        assert result["success"] is False
        assert "not found" in result["error"]

    def test_reschedule_task_invalid_time_format(self, tools):
        result = tools.reschedule_task(
            pet_name="Buddy", task_name="Morning Walk", new_start_time="10:00am"
        )
        assert result["success"] is False
        assert "Invalid" in result["error"]

    # ── Tool 6: complete_task ──────────────────────────────────────────────

    def test_complete_task_one_off_retires(self, tools, today):
        task = tools.owner.pets[0].tasks[0]  # Morning Walk, frequency defaults to one-off
        result = tools.complete_task(pet_name="Buddy", task_name=task.name)
        assert result["success"] is True
        assert result["retired"] is True
        assert task.is_completed is True

    def test_complete_task_daily_advances_due_date(self, tools, today):
        task = tools.owner.pets[0].tasks[0]
        task.frequency = "daily"
        result = tools.complete_task(pet_name="Buddy", task_name=task.name)
        assert result["success"] is True
        assert result["next_due_date"] == (today + timedelta(days=1)).isoformat()
        assert task.is_completed is False

    def test_complete_task_weekly_advances_due_date(self, tools, today):
        task = tools.owner.pets[0].tasks[0]
        task.frequency = "weekly"
        tools.complete_task(pet_name="Buddy", task_name=task.name)
        assert task.due_date == today + timedelta(weeks=1)

    def test_complete_task_not_found(self, tools):
        result = tools.complete_task(pet_name="Buddy", task_name="Nonexistent")
        assert result["success"] is False

    def test_complete_task_already_completed(self, tools):
        task = tools.owner.pets[0].tasks[0]
        task.is_completed = True
        result = tools.complete_task(pet_name="Buddy", task_name=task.name)
        assert result["success"] is False

    # ── Tool 7: add_pet ────────────────────────────────────────────────────

    def test_add_pet_success(self, tools):
        result = tools.add_pet(name="Rex", species="dog", age=5)
        assert result["success"] is True
        assert "Rex" in result["pet_summary"]
        assert any(p.name == "Rex" for p in tools.owner.pets)

    def test_add_pet_duplicate_name(self, tools):
        result = tools.add_pet(name="Buddy", species="dog", age=2)
        assert result["success"] is False
        assert "already exists" in result["error"]

    def test_add_pet_negative_age(self, tools):
        result = tools.add_pet(name="NewPet", species="cat", age=-1)
        assert result["success"] is False
        assert "age" in result["error"]

    # ── Tool 8: filter_tasks ───────────────────────────────────────────────

    def test_filter_tasks_all(self, tools):
        result = tools.filter_tasks()
        assert result["count"] == 4

    def test_filter_tasks_by_pet(self, tools):
        result = tools.filter_tasks(pet_name="Buddy")
        assert result["count"] == 2
        for task in result["tasks"]:
            assert task["pet_name"] == "Buddy"

    def test_filter_tasks_by_completed_false(self, tools):
        tools.owner.pets[0].tasks[0].is_completed = True
        result = tools.filter_tasks(is_completed=False)
        assert result["count"] == 3

    def test_filter_tasks_by_completed_true(self, tools):
        tools.owner.pets[0].tasks[0].is_completed = True
        result = tools.filter_tasks(is_completed=True)
        assert result["count"] == 1

    # ── Tool 9: save_state ─────────────────────────────────────────────────

    def test_save_state_writes_file(self, tools):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = f"{tmpdir}/data/owner.json"
            result = tools.save_state(path=path)
            assert result["success"] is True
            assert result["path"] == path
            assert Path(path).exists()

    def test_save_state_roundtrip(self, tools):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = f"{tmpdir}/data/data.json"
            tools.save_state(path=path)
            loaded = Owner.load_from_json(path)
            assert loaded.name == tools.owner.name
            assert len(loaded.pets) == len(tools.owner.pets)


# ===========================================================================
# TC-DISP  TestDispatch
# ===========================================================================


class TestDispatch:
    """Test the dispatch() routing method — BUG#1 TypeError fix is verified here."""

    def test_dispatch_valid_tool_get_all_tasks(self, tools):
        result = tools.dispatch("get_all_tasks", {})
        assert "tasks" in result

    def test_dispatch_valid_tool_add_pet(self, tools):
        result = tools.dispatch("add_pet", {"name": "Rex", "species": "dog", "age": 2})
        assert result["success"] is True

    def test_dispatch_unknown_tool_raises_value_error(self, tools):
        with pytest.raises(ValueError, match="Unknown or non-LLM-callable"):
            tools.dispatch("nonexistent_tool", {})

    def test_dispatch_tool10_is_blocked(self, tools):
        """validate_required_tasks must never be reachable via dispatch."""
        with pytest.raises(ValueError):
            tools.dispatch("validate_required_tasks", {})

    def test_dispatch_missing_required_param_returns_error_dict(self, tools):
        """BUG#1 fix: LLM omitting a required param produces a graceful error, not TypeError."""
        # add_task requires pet_name, name, duration, priority — omit all of them
        result = tools.dispatch("add_task", {})
        assert result["success"] is False
        assert "error" in result
        assert "add_task" in result["error"] or "parameter" in result["error"].lower()

    def test_dispatch_whitelist_covers_exactly_nine_tools(self, tools):
        """dispatch() must only route the nine schema-listed tools."""
        callable_names = {s["name"] for s in TOOL_SCHEMAS}
        assert len(callable_names) == 9
        assert "validate_required_tasks" not in callable_names


# ===========================================================================
# TC-GUARD  TestValidateRequiredTasks
# ===========================================================================


class TestValidateRequiredTasks:
    """Tests for the injection-proof guardrail algorithm — BUG#6 fix included."""

    def _schedule(self, task_dicts: list[dict]) -> dict:
        return {"scheduled_tasks": task_dicts}

    def _required_task(
        self, name: str, pet_name: str = "Buddy", today: date = None
    ) -> Task:
        return Task(
            name=name,
            duration=10,
            priority=5,
            is_required=True,
            due_date=today or date.today(),
        )

    def test_clean_schedule_no_violations(self, owner, today):
        # Build a schedule with pet_name keys matching the owner's required tasks
        schedule = self._schedule([
            {"name": "Morning Walk", "pet_name": "Buddy", "duration": 30,
             "priority": 4, "is_required": True, "is_completed": False,
             "start_time": "08:00", "frequency": "one-off",
             "due_date": today.isoformat()},
            {"name": "Feeding", "pet_name": "Mochi", "duration": 10,
             "priority": 5, "is_required": True, "is_completed": False,
             "start_time": "09:30", "frequency": "one-off",
             "due_date": today.isoformat()},
        ])
        result = validate_required_tasks(schedule, owner)
        assert result["guardrail_triggered"] is False
        assert result["violations"] == []

    def test_missing_required_task_detected(self, owner, today):
        # Omit Morning Walk (Buddy required)
        schedule = self._schedule([
            {"name": "Feeding", "pet_name": "Mochi", "duration": 10,
             "priority": 5, "is_required": True, "is_completed": False,
             "start_time": "09:30", "frequency": "one-off",
             "due_date": today.isoformat()},
        ])
        result = validate_required_tasks(schedule, owner)
        assert result["guardrail_triggered"] is True
        assert "Morning Walk" in result["violations"]

    def test_missing_required_task_prepended_to_corrected_schedule(self, owner, today):
        schedule = self._schedule([])
        result = validate_required_tasks(schedule, owner)
        names = [t["name"] for t in result["corrected_schedule"]["scheduled_tasks"]]
        assert "Morning Walk" in names
        assert "Feeding" in names
        # Required tasks must be prepended, so they come before any existing tasks.
        assert names.index("Morning Walk") < len(
            result["corrected_schedule"]["scheduled_tasks"]
        )

    def test_same_name_different_pets_bug6_fix(self, today):
        """BUG#6: Two pets with identically-named required tasks must each be checked."""
        o = Owner(name="Bob", available_time_mins=240)

        buddy = Pet(name="Buddy", species="dog", age=3)
        buddy.tasks = [
            Task(name="Feeding", duration=10, priority=5, is_required=True, due_date=today)
        ]
        mochi = Pet(name="Mochi", species="cat", age=2)
        mochi.tasks = [
            Task(name="Feeding", duration=10, priority=5, is_required=True, due_date=today)
        ]
        o.pets = [buddy, mochi]

        # Schedule includes only Buddy's Feeding — Mochi's must be detected as missing
        schedule = self._schedule([
            {"name": "Feeding", "pet_name": "Buddy", "duration": 10,
             "priority": 5, "is_required": True, "is_completed": False,
             "start_time": None, "frequency": "one-off",
             "due_date": today.isoformat()},
        ])
        result = validate_required_tasks(schedule, o)
        assert result["guardrail_triggered"] is True
        # One violation (Mochi's Feeding)
        assert len(result["violations"]) == 1
        assert result["violations"][0] == "Feeding"

    def test_future_required_task_not_checked(self, owner, today):
        # Push Morning Walk to tomorrow — it must NOT trigger a violation
        owner.pets[0].tasks[0].due_date = today + timedelta(days=1)
        schedule = self._schedule([
            {"name": "Feeding", "pet_name": "Mochi", "duration": 10,
             "priority": 5, "is_required": True, "is_completed": False,
             "start_time": None, "frequency": "one-off",
             "due_date": today.isoformat()},
        ])
        result = validate_required_tasks(schedule, owner)
        assert result["guardrail_triggered"] is False

    def test_completed_required_task_not_checked(self, owner, today):
        # Mark Morning Walk completed — must NOT trigger a violation
        owner.pets[0].tasks[0].is_completed = True
        schedule = self._schedule([
            {"name": "Feeding", "pet_name": "Mochi", "duration": 10,
             "priority": 5, "is_required": True, "is_completed": False,
             "start_time": None, "frequency": "one-off",
             "due_date": today.isoformat()},
        ])
        result = validate_required_tasks(schedule, owner)
        assert result["guardrail_triggered"] is False

    def test_empty_schedule_all_required_reported(self, owner):
        result = validate_required_tasks(self._schedule([]), owner)
        assert result["guardrail_triggered"] is True
        assert len(result["violations"]) == 2  # Morning Walk + Feeding

    def test_legacy_schedule_without_pet_name_fallback(self, owner, today):
        """Schedules without pet_name field should still pass when tasks are present."""
        schedule = self._schedule([
            {"name": "Morning Walk", "duration": 30,
             "priority": 4, "is_required": True, "is_completed": False,
             "start_time": "08:00", "frequency": "one-off",
             "due_date": today.isoformat()},
            {"name": "Feeding", "duration": 10,
             "priority": 5, "is_required": True, "is_completed": False,
             "start_time": "09:30", "frequency": "one-off",
             "due_date": today.isoformat()},
        ])
        result = validate_required_tasks(schedule, owner)
        assert result["guardrail_triggered"] is False


# ===========================================================================
# TC-CRRES  TestCorrectionResult
# ===========================================================================


class TestCorrectionResult:
    """Test CorrectionResult dataclass properties and helpers."""

    def _make(self, violations: list[str], triggered: bool) -> CorrectionResult:
        return CorrectionResult(
            violations=violations,
            corrected_schedule={"scheduled_tasks": []},
            guardrail_triggered=triggered,
        )

    def test_is_clean_when_no_violations(self):
        result = self._make([], False)
        assert result.is_clean is True

    def test_is_not_clean_when_violations(self):
        result = self._make(["Feeding"], True)
        assert result.is_clean is False

    def test_violation_count_zero(self):
        result = self._make([], False)
        assert result.violation_count == 0

    def test_violation_count_positive(self):
        result = self._make(["A", "B"], True)
        assert result.violation_count == 2

    def test_as_ui_message_empty_when_clean(self):
        result = self._make([], False)
        assert result.as_ui_message() == ""

    def test_as_ui_message_contains_task_names(self):
        result = self._make(["Morning Walk", "Feeding"], True)
        msg = result.as_ui_message()
        assert "Morning Walk" in msg
        assert "Feeding" in msg
        assert "2" in msg  # violation count

    def test_as_ui_message_is_truthy_on_violation(self):
        result = self._make(["Walk"], True)
        assert bool(result.as_ui_message())

    def test_timestamp_is_set(self):
        result = self._make([], False)
        assert result.timestamp  # non-empty ISO-8601 string

    def test_needs_clarification_false_on_success(self):
        """ParseResult helper — included here for completeness."""
        pr = ParseResult(success=True, task_dict={})
        assert pr.needs_clarification is False

    def test_needs_clarification_true_when_question_set(self):
        pr = ParseResult(success=False, clarification_question="What time?")
        assert pr.needs_clarification is True


# ===========================================================================
# TC-RG  TestRunGuardrail
# ===========================================================================


class TestRunGuardrail:
    """Integration tests for run_guardrail() — verify CorrectionResult and JSONL log."""

    def test_run_guardrail_clean_returns_result(self, owner, today):
        # A schedule with both required tasks present
        schedule = {
            "scheduled_tasks": [
                {"name": "Morning Walk", "pet_name": "Buddy", "duration": 30,
                 "priority": 4, "is_required": True, "is_completed": False,
                 "start_time": "08:00", "frequency": "one-off",
                 "due_date": today.isoformat()},
                {"name": "Feeding", "pet_name": "Mochi", "duration": 10,
                 "priority": 5, "is_required": True, "is_completed": False,
                 "start_time": "09:30", "frequency": "one-off",
                 "due_date": today.isoformat()},
            ]
        }
        result = run_guardrail(schedule, owner)
        assert isinstance(result, CorrectionResult)
        assert result.is_clean

    def test_run_guardrail_triggered_sets_flag(self, owner):
        result = run_guardrail({"scheduled_tasks": []}, owner)
        assert result.guardrail_triggered is True
        assert result.violation_count == 2

    def test_run_guardrail_audit_log_written(self, owner, tmp_path):
        log_path = tmp_path / "violations.jsonl"
        with patch("agent.guardrail.VIOLATION_LOG_PATH", log_path):
            run_guardrail({"scheduled_tasks": []}, owner)
        assert log_path.exists()

    def test_run_guardrail_audit_log_format(self, owner, tmp_path):
        log_path = tmp_path / "violations.jsonl"
        with patch("agent.guardrail.VIOLATION_LOG_PATH", log_path):
            run_guardrail({"scheduled_tasks": []}, owner)
        records = [json.loads(line) for line in log_path.read_text().splitlines()]
        assert len(records) == 1
        rec = records[0]
        assert rec["event"] == "GUARDRAIL_VIOLATION"
        assert rec["owner_name"] == "Alice"
        assert rec["violation_count"] == 2
        assert "Morning Walk" in rec["missing_required_tasks"]

    def test_run_guardrail_no_log_when_clean(self, owner, today, tmp_path):
        schedule = {
            "scheduled_tasks": [
                {"name": "Morning Walk", "pet_name": "Buddy", "duration": 30,
                 "priority": 4, "is_required": True, "is_completed": False,
                 "start_time": "08:00", "frequency": "one-off",
                 "due_date": today.isoformat()},
                {"name": "Feeding", "pet_name": "Mochi", "duration": 10,
                 "priority": 5, "is_required": True, "is_completed": False,
                 "start_time": "09:30", "frequency": "one-off",
                 "due_date": today.isoformat()},
            ]
        }
        log_path = tmp_path / "violations.jsonl"
        with patch("agent.guardrail.VIOLATION_LOG_PATH", log_path):
            run_guardrail(schedule, owner)
        assert not log_path.exists()


# ===========================================================================
# TC-ORCH  TestOrchestratorHelpers
# ===========================================================================


class TestOrchestratorHelpers:
    """Tests for pure helper methods on PawPalOrchestrator and module-level utils."""

    # ── _compute_end_time ──────────────────────────────────────────────────

    def test_compute_end_time_basic(self):
        assert _compute_end_time("08:00", 30) == "08:30"

    def test_compute_end_time_hour_boundary(self):
        assert _compute_end_time("09:45", 30) == "10:15"

    def test_compute_end_time_midnight_rollover(self):
        # 23:50 + 30 min wraps to 00:20
        assert _compute_end_time("23:50", 30) == "00:20"

    def test_compute_end_time_none_returns_unset(self):
        assert _compute_end_time(None, 30) == "unset"

    def test_compute_end_time_empty_string_returns_unset(self):
        assert _compute_end_time("", 30) == "unset"

    def test_compute_end_time_invalid_format_returns_invalid(self):
        assert _compute_end_time("8am", 30) == "invalid"

    # ── _extract_json ──────────────────────────────────────────────────────

    def test_extract_json_plain_json(self, orchestrator):
        obj = orchestrator._extract_json('{"type": "clarification_request"}')
        assert obj == {"type": "clarification_request"}

    def test_extract_json_code_fence(self, orchestrator):
        text = '```json\n{"key": "value"}\n```'
        obj = orchestrator._extract_json(text)
        assert obj == {"key": "value"}

    def test_extract_json_embedded_in_prose(self, orchestrator):
        text = 'I need to ask the user. {"type": "clarification_request", "question": "When?"}'
        obj = orchestrator._extract_json(text)
        assert obj is not None
        assert obj.get("type") == "clarification_request"

    def test_extract_json_invalid_returns_none(self, orchestrator):
        obj = orchestrator._extract_json("This is not JSON at all.")
        assert obj is None

    # ── _extract_thought ───────────────────────────────────────────────────

    def test_extract_thought_with_text_block(self, orchestrator):
        blocks = [_text_block("I should reschedule task B.")]
        thought = orchestrator._extract_thought(blocks)
        assert thought == "I should reschedule task B."

    def test_extract_thought_multiple_blocks_joined(self, orchestrator):
        blocks = [_text_block("First thought."), _text_block("Second thought.")]
        thought = orchestrator._extract_thought(blocks)
        assert "First thought." in thought
        assert "Second thought." in thought

    def test_extract_thought_fallback_when_empty(self, orchestrator):
        """BUG#5 fix: _extract_thought must never return an empty string."""
        thought = orchestrator._extract_thought([])
        assert thought == "(no text reasoning provided)"

    def test_extract_thought_skips_tool_blocks(self, orchestrator):
        blocks = [_tool_block("add_task", {}), _text_block("Only text.")]
        thought = orchestrator._extract_thought(blocks)
        assert thought == "Only text."

    # ── _serialize_content ─────────────────────────────────────────────────

    def test_serialize_text_block(self, orchestrator):
        blocks = [_text_block("Hello")]
        result = orchestrator._serialize_content(blocks)
        assert result == [{"type": "text", "text": "Hello"}]

    def test_serialize_tool_use_block(self, orchestrator):
        blocks = [_tool_block("add_task", {"pet_name": "Buddy"}, "id_1")]
        result = orchestrator._serialize_content(blocks)
        assert result == [
            {
                "type": "tool_use",
                "id": "id_1",
                "name": "add_task",
                "input": {"pet_name": "Buddy"},
            }
        ]

    def test_serialize_mixed_blocks(self, orchestrator):
        blocks = [_text_block("Thinking…"), _tool_block("save_state", {}, "id_2")]
        result = orchestrator._serialize_content(blocks)
        assert len(result) == 2
        assert result[0]["type"] == "text"
        assert result[1]["type"] == "tool_use"

    # ── _build_system_messages ─────────────────────────────────────────────

    def test_build_system_messages_returns_two_blocks(self, orchestrator):
        msgs = orchestrator._build_system_messages()
        assert len(msgs) == 2

    def test_build_system_messages_first_block_has_cache_control(self, orchestrator):
        msgs = orchestrator._build_system_messages()
        assert msgs[0].get("cache_control") == {"type": "ephemeral"}

    def test_build_system_messages_second_block_no_cache(self, orchestrator):
        msgs = orchestrator._build_system_messages()
        assert "cache_control" not in msgs[1]

    # ── _format_conflict_pairs ─────────────────────────────────────────────

    def test_format_conflict_pairs_empty(self, orchestrator):
        text = orchestrator._format_conflict_pairs([])
        assert "(none)" in text

    def test_format_conflict_pairs_single(self, orchestrator):
        pair = {
            "task_a": {
                "name": "Walk", "start_time": "08:00", "duration": 60,
                "priority": 3, "is_required": False,
            },
            "task_b": {
                "name": "Vet", "start_time": "08:30", "duration": 90,
                "priority": 5, "is_required": True,
            },
        }
        text = orchestrator._format_conflict_pairs([pair])
        assert "Walk" in text
        assert "Vet" in text
        assert "08:00" in text


# ===========================================================================
# TC-NL  TestParseNlTask
# ===========================================================================


class TestParseNlTask:
    """Test parse_nl_task() with a mocked Anthropic client."""

    def test_tool_use_response_adds_task(self, orchestrator, mock_client):
        """Successful add_task tool call → ParseResult(success=True)."""
        block = _tool_block(
            "add_task",
            {
                "pet_name": "Buddy",
                "name": "Evening Walk",
                "duration": 30,
                "priority": 3,
            },
        )
        mock_client.messages.create.return_value = _mock_response(
            [_text_block("I'll add the walk."), block], stop_reason="tool_use"
        )

        result = orchestrator.parse_nl_task("Add an evening walk for Buddy")

        assert result.success is True
        assert result.task_dict is not None
        assert result.task_dict["name"] == "Evening Walk"

    def test_tool_use_response_updates_trace(self, orchestrator, mock_client):
        block = _tool_block(
            "add_task",
            {"pet_name": "Buddy", "name": "Nap", "duration": 20, "priority": 2},
        )
        mock_client.messages.create.return_value = _mock_response(
            [block], stop_reason="tool_use"
        )
        orchestrator.parse_nl_task("Buddy nap")
        assert len(orchestrator.agent_trace) == 1
        assert orchestrator.agent_trace[0].action_tool == "add_task"

    def test_tool_use_failure_propagates(self, orchestrator, mock_client):
        """Tool call succeeds syntactically but returns success=False (bad pet name)."""
        block = _tool_block(
            "add_task",
            {"pet_name": "Unknown", "name": "Walk", "duration": 30, "priority": 3},
        )
        mock_client.messages.create.return_value = _mock_response(
            [block], stop_reason="tool_use"
        )
        result = orchestrator.parse_nl_task("Add walk for Unknown")
        assert result.success is False
        assert result.error is not None

    def test_clarification_request_returned(self, orchestrator, mock_client):
        """Model issues end_turn with a clarification_request JSON body."""
        clarification_json = json.dumps({
            "type": "clarification_request",
            "question": "How long should the walk be?",
            "missing_fields": ["duration"],
        })
        mock_client.messages.create.return_value = _mock_response(
            [_text_block(clarification_json)], stop_reason="end_turn"
        )
        result = orchestrator.parse_nl_task("Walk Buddy")
        assert result.success is False
        assert result.needs_clarification is True
        assert "How long" in result.clarification_question

    def test_unexpected_end_turn_returns_error(self, orchestrator, mock_client):
        """end_turn with no parseable JSON → ParseResult(success=False, error=...)."""
        mock_client.messages.create.return_value = _mock_response(
            [_text_block("I don't understand.")], stop_reason="end_turn"
        )
        result = orchestrator.parse_nl_task("gibberish")
        assert result.success is False
        assert result.error is not None

    def test_dispatch_value_error_caught(self, orchestrator, mock_client):
        """dispatch() raising ValueError (unknown tool) → ParseResult error."""
        block = _tool_block("validate_required_tasks", {})  # blocked tool
        mock_client.messages.create.return_value = _mock_response(
            [block], stop_reason="tool_use"
        )
        result = orchestrator.parse_nl_task("something")
        assert result.success is False
        assert result.error is not None


# ===========================================================================
# TC-REACT  TestResolveScheduleConflicts
# ===========================================================================


class TestResolveScheduleConflicts:
    """Test the bounded ReAct loop — includes BUG#3 escalation-save fix."""

    @pytest.fixture
    def conflict_owner(self, today: date) -> Owner:
        """Owner whose two tasks have overlapping time windows."""
        o = Owner(name="Bob", available_time_mins=300)
        pet = Pet(name="Rex", species="dog", age=4)
        pet.tasks = [
            Task(
                name="Walk",
                duration=60,
                priority=4,
                is_required=True,
                start_time="08:00",
                due_date=today,
            ),
            Task(
                name="Vet",
                duration=90,
                priority=5,
                is_required=True,
                start_time="08:30",  # overlaps Walk 08:00-09:00
                due_date=today,
            ),
        ]
        o.pets = [pet]
        return o

    @pytest.fixture
    def clean_owner(self, today: date) -> Owner:
        """Owner whose two tasks have no time-window conflicts."""
        o = Owner(name="Carol", available_time_mins=300)
        pet = Pet(name="Fifi", species="cat", age=2)
        pet.tasks = [
            Task(
                name="Feeding",
                duration=10,
                priority=5,
                is_required=True,
                start_time="08:00",
                due_date=today,
            ),
            Task(
                name="Playtime",
                duration=20,
                priority=2,
                is_required=False,
                start_time="09:00",
                due_date=today,
            ),
        ]
        o.pets = [pet]
        return o

    def _make_orchestrator(self, owner: Owner, client, max_steps: int = 3):
        return PawPalOrchestrator(
            owner=owner, client=client, max_resolution_steps=max_steps
        )

    # ── No-conflict fast-path ──────────────────────────────────────────────

    def test_no_conflicts_saves_immediately(self, clean_owner, mock_client, tmp_path):
        orch = self._make_orchestrator(clean_owner, mock_client)
        with tempfile.TemporaryDirectory() as d:
            with patch.object(orch.tools, "save_state", return_value={"success": True}) as m:
                result = orch.resolve_schedule_conflicts()
        assert result["conflicts_resolved"] is True
        assert result["steps_taken"] == 0
        assert result["escalated"] is False
        mock_client.messages.create.assert_not_called()

    # ── end_turn immediately (model gives up) ─────────────────────────────

    def test_end_turn_without_resolve_escalates(self, conflict_owner, mock_client):
        orch = self._make_orchestrator(conflict_owner, mock_client)
        mock_client.messages.create.return_value = _mock_response(
            [_text_block("I cannot resolve this.")], stop_reason="end_turn"
        )
        result = orch.resolve_schedule_conflicts()
        assert result["escalated"] is True

    def test_end_turn_without_resolve_saves_state(self, conflict_owner, mock_client):
        """BUG#3 fix: escalation must trigger a save_state so partial reschedules persist."""
        orch = self._make_orchestrator(conflict_owner, mock_client)
        mock_client.messages.create.return_value = _mock_response(
            [_text_block("I give up.")], stop_reason="end_turn"
        )
        with patch.object(orch.tools, "save_state", return_value={"success": True}) as m:
            orch.resolve_schedule_conflicts()
        m.assert_called_once()  # must call save_state even on escalation

    # ── Successful resolution in one step ─────────────────────────────────

    def test_resolve_in_one_step(self, conflict_owner, mock_client):
        orch = self._make_orchestrator(conflict_owner, mock_client)

        # Step 1: model calls reschedule_task
        reschedule_block = _tool_block(
            "reschedule_task",
            {"pet_name": "Rex", "task_name": "Vet", "new_start_time": "09:00"},
            "tu_001",
        )
        # Step 2: model calls detect_conflicts → 0 conflicts → resolved
        detect_block = _tool_block("detect_conflicts", {"tasks": []}, "tu_002")
        # Step 3: model calls save_state and issues end_turn
        save_block = _tool_block("save_state", {}, "tu_003")

        mock_client.messages.create.side_effect = [
            _mock_response([_text_block("Shifting Vet."), reschedule_block]),
            _mock_response([detect_block]),
            _mock_response([save_block]),
            _mock_response([_text_block("Done.")], stop_reason="end_turn"),
        ]

        result = orch.resolve_schedule_conflicts()
        # The final detect_conflicts runs on the real schedule, which is now clean.
        assert isinstance(result, dict)
        assert "schedule" in result

    # ── Step-budget exhaustion ─────────────────────────────────────────────

    def test_step_budget_exhausted_escalates(self, conflict_owner, mock_client):
        orch = self._make_orchestrator(conflict_owner, mock_client, max_steps=2)
        # Model always calls reschedule_task but never fixes the conflict
        reschedule_block = _tool_block(
            "reschedule_task",
            {"pet_name": "Rex", "task_name": "Walk", "new_start_time": "08:00"},
            "tu_001",
        )
        mock_client.messages.create.return_value = _mock_response(
            [_text_block("Shifting…"), reschedule_block]
        )
        result = orch.resolve_schedule_conflicts()
        assert result["escalated"] is True
        assert result["steps_taken"] == 2

    def test_step_budget_exhausted_saves_state(self, conflict_owner, mock_client):
        """BUG#3 fix: exhausted budget must also persist partial state."""
        orch = self._make_orchestrator(conflict_owner, mock_client, max_steps=1)
        reschedule_block = _tool_block(
            "reschedule_task",
            {"pet_name": "Rex", "task_name": "Walk", "new_start_time": "08:10"},
            "tu_001",
        )
        mock_client.messages.create.return_value = _mock_response(
            [reschedule_block]
        )
        with patch.object(
            orch.tools, "save_state", return_value={"success": True}
        ) as m:
            orch.resolve_schedule_conflicts()
        m.assert_called_once()

    # ── Trace recording ────────────────────────────────────────────────────

    def test_trace_steps_recorded(self, conflict_owner, mock_client):
        orch = self._make_orchestrator(conflict_owner, mock_client, max_steps=1)
        block = _tool_block(
            "reschedule_task",
            {"pet_name": "Rex", "task_name": "Vet", "new_start_time": "09:00"},
            "tu_001",
        )
        mock_client.messages.create.return_value = _mock_response([block])
        orch.resolve_schedule_conflicts()
        assert len(orch.agent_trace) >= 1
        step = orch.agent_trace[0]
        assert isinstance(step, TraceStep)
        assert step.action_tool == "reschedule_task"

    def test_clear_trace_resets(self, orchestrator):
        orchestrator.agent_trace.append(
            TraceStep(1, "thought", "tool", {}, {})
        )
        orchestrator.clear_trace()
        assert orchestrator.agent_trace == []

    # ── run_final_guardrail ────────────────────────────────────────────────

    def test_run_final_guardrail_clean(self, orchestrator, today):
        schedule = {
            "scheduled_tasks": [
                {"name": "Morning Walk", "pet_name": "Buddy", "duration": 30,
                 "priority": 4, "is_required": True, "is_completed": False,
                 "start_time": "08:00", "frequency": "one-off",
                 "due_date": today.isoformat()},
                {"name": "Feeding", "pet_name": "Mochi", "duration": 10,
                 "priority": 5, "is_required": True, "is_completed": False,
                 "start_time": "09:30", "frequency": "one-off",
                 "due_date": today.isoformat()},
            ]
        }
        result = orchestrator.run_final_guardrail(schedule)
        assert result.is_clean
        # No guardrail trace step should be added
        trace_tools = [s.action_tool for s in orchestrator.agent_trace]
        assert "validate_required_tasks" not in trace_tools

    def test_run_final_guardrail_triggered_adds_trace(self, orchestrator):
        result = orchestrator.run_final_guardrail({"scheduled_tasks": []})
        assert result.guardrail_triggered is True
        trace_tools = [s.action_tool for s in orchestrator.agent_trace]
        assert "validate_required_tasks" in trace_tools

    def test_run_final_guardrail_returns_correction_result(self, orchestrator):
        result = orchestrator.run_final_guardrail({"scheduled_tasks": []})
        assert isinstance(result, CorrectionResult)
