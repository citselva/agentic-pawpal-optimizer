"""tests/test_e2e.py — End-to-end integration tests for PawPal+.

Covers:
- TC-UI:     app.py helper functions (_priority_badge, _priority_badge_html,
             _section_header)
- TC-WF:     Full schedule workflow — single/multi-pet, required-task overflow,
             completed-task exclusion, daily recurrence
- TC-GUARD:  Guardrail E2E — clean pass, violations detected/restored, audit log
- TC-PERS:   Persistence round-trip (all field types) and DEFECT-1 regression
- TC-DEF:    DEFECT-2 regression (malformed task dicts in detect_conflicts)
- TC-METRICS: RunMetrics.format_summary() output verification
- TC-CHAT:   Mocked LLM chat — NL parse success, clarification, unknown pet,
             trace accumulation
"""

from __future__ import annotations

import json
import sys
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# sys.path — ensure project root is importable when tests run via pytest
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent.parent))

from pawpal_system import Task, Pet, Owner, Scheduler, ScheduleResult
from agent.tools import PawPalTools, validate_required_tasks
from agent.guardrail import CorrectionResult, run_guardrail, VIOLATION_LOG_PATH
from agent.orchestrator import (
    PawPalOrchestrator,
    RunMetrics,
    ApiCallRecord,
    TraceStep,
    ParseResult,
)

# Import app helpers directly (no Streamlit execution — module-level st.* calls
# are bypassed because the functions we need are plain Python below app init).
import importlib, types

def _load_app_helpers():
    """Import only the pure-Python helper functions from app.py without
    triggering Streamlit's top-level widget calls."""
    import ast, textwrap

    src = Path(__file__).parent.parent / "app.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))

    # Collect function defs we need
    targets = {"_priority_badge", "_priority_badge_html", "_sidebar_section"}
    func_src_lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in targets:
            func_src_lines.append(ast.get_source_segment(src.read_text(encoding="utf-8"), node))

    ns: dict[str, Any] = {}
    for snippet in func_src_lines:
        exec(compile(snippet, "<app_helpers>", "exec"), ns)

    return ns


_APP = _load_app_helpers()
_priority_badge = _APP["_priority_badge"]
_priority_badge_html = _APP["_priority_badge_html"]
_sidebar_section = _APP["_sidebar_section"]


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def today():
    return date.today()


@pytest.fixture
def owner_with_tasks(today):
    """Owner with one dog and three tasks (one required, one optional, one future)."""
    pet = Pet(name="Rex", species="dog", age=4)
    req = Task(
        name="Morning Walk",
        duration=30,
        priority=5,
        is_required=True,
        due_date=today,
        start_time="08:00",
        frequency="daily",
    )
    opt = Task(
        name="Grooming",
        duration=20,
        priority=3,
        is_required=False,
        due_date=today,
        start_time="09:00",
        frequency="weekly",
    )
    future = Task(
        name="Vet Checkup",
        duration=60,
        priority=4,
        is_required=False,
        due_date=today + timedelta(days=7),
    )
    pet.tasks.extend([req, opt, future])
    return Owner(name="Alice", available_time_mins=90, pets=[pet])


@pytest.fixture
def tools(owner_with_tasks):
    return PawPalTools(owner_with_tasks)


@pytest.fixture
def mock_client():
    """Minimal MagicMock that mimics anthropic.Anthropic."""
    client = MagicMock()
    return client


# ---------------------------------------------------------------------------
# TC-UI: app.py helper functions
# ---------------------------------------------------------------------------


class TestPriorityBadge:
    """TC-UI-01: _priority_badge() plain-text labels."""

    def test_priority_5_returns_high(self):
        assert _priority_badge(5) == "High"

    def test_priority_above_5_returns_high(self):
        assert _priority_badge(10) == "High"

    def test_priority_3_returns_medium(self):
        assert _priority_badge(3) == "Medium"

    def test_priority_4_returns_medium(self):
        assert _priority_badge(4) == "Medium"

    def test_priority_2_returns_low(self):
        assert _priority_badge(2) == "Low"

    def test_priority_1_returns_low(self):
        assert _priority_badge(1) == "Low"


class TestPriorityBadgeHtml:
    """TC-UI-02: _priority_badge_html() HTML pill content."""

    def test_high_contains_HIGH(self):
        html = _priority_badge_html(5)
        assert "HIGH" in html

    def test_high_uses_red_background(self):
        html = _priority_badge_html(5)
        assert "#FECACA" in html

    def test_medium_contains_MED(self):
        html = _priority_badge_html(3)
        assert "MED" in html

    def test_medium_uses_yellow_background(self):
        html = _priority_badge_html(3)
        assert "#FDE68A" in html

    def test_low_contains_LOW(self):
        html = _priority_badge_html(1)
        assert "LOW" in html

    def test_low_uses_green_background(self):
        html = _priority_badge_html(1)
        assert "#A7F3D0" in html

    def test_returns_span_tag(self):
        for p in (1, 3, 5):
            html = _priority_badge_html(p)
            assert "<span" in html
            assert "</span>" in html

    def test_priority_4_is_medium(self):
        html = _priority_badge_html(4)
        assert "MED" in html

    def test_priority_2_is_low(self):
        html = _priority_badge_html(2)
        assert "LOW" in html


class TestSidebarSection:
    """TC-UI-03: _sidebar_section() HTML structure."""

    def test_contains_icon(self):
        html = _sidebar_section("🐾", "Tasks")
        assert "🐾" in html

    def test_contains_title(self):
        html = _sidebar_section("🐾", "My Tasks")
        assert "My Tasks" in html

    def test_no_subtitle_when_omitted(self):
        html = _sidebar_section("🐾", "Tasks")
        # subtitle div has margin-top:2px — absent when no subtitle supplied
        assert "margin-top:2px" not in html

    def test_subtitle_appears_when_provided(self):
        html = _sidebar_section("🐾", "Tasks", "Manage your schedule")
        assert "Manage your schedule" in html
        assert "margin-top:2px" in html

    def test_returns_string(self):
        assert isinstance(_sidebar_section("🐾", "X"), str)


# ---------------------------------------------------------------------------
# TC-WF: Full schedule workflow
# ---------------------------------------------------------------------------


class TestFullScheduleWorkflow:
    """TC-WF-01 — End-to-end scheduling from Owner through Scheduler."""

    def test_single_pet_schedule_includes_due_tasks(self, owner_with_tasks, today):
        scheduler = Scheduler(owner_with_tasks)
        result = scheduler.generate_schedule()
        names = [t.name for t in result.scheduled_tasks]
        assert "Morning Walk" in names
        assert "Grooming" in names
        # future task must not appear
        assert "Vet Checkup" not in names

    def test_required_task_always_scheduled(self, today):
        """Required task is scheduled even when it alone exceeds the budget."""
        pet = Pet(name="Buddy", species="cat", age=2)
        task = Task(
            name="Medication",
            duration=120,
            priority=5,
            is_required=True,
            due_date=today,
        )
        pet.tasks.append(task)
        owner = Owner(name="Bob", available_time_mins=30, pets=[pet])
        scheduler = Scheduler(owner)
        result = scheduler.generate_schedule()
        assert any(t.name == "Medication" for t in result.scheduled_tasks)
        assert "Time Deficit" in result.reasoning

    def test_optional_task_skipped_when_budget_full(self, today):
        pet = Pet(name="Luna", species="rabbit", age=1)
        req = Task(name="Feed", duration=60, priority=5, is_required=True, due_date=today)
        opt = Task(name="Play", duration=30, priority=2, is_required=False, due_date=today)
        pet.tasks.extend([req, opt])
        owner = Owner(name="Carol", available_time_mins=60, pets=[pet])
        result = Scheduler(owner).generate_schedule()
        assert any(t.name == "Feed" for t in result.scheduled_tasks)
        assert any(t.name == "Play" for t in result.skipped_tasks)

    def test_multi_pet_tasks_all_flattened(self, today):
        p1 = Pet(name="Rover", species="dog", age=3)
        p1.tasks.append(Task(name="Walk", duration=30, priority=4, due_date=today))
        p2 = Pet(name="Whiskers", species="cat", age=5)
        p2.tasks.append(Task(name="Feed", duration=10, priority=5, is_required=True, due_date=today))
        owner = Owner(name="Dave", available_time_mins=120, pets=[p1, p2])
        all_tasks = owner.get_all_tasks()
        names = [t.name for t in all_tasks]
        assert "Walk" in names and "Feed" in names

    def test_completed_one_off_excluded(self, today):
        """TC-WF-STATE-01: Completed one-off tasks must not re-enter scheduling."""
        pet = Pet(name="Pip", species="hamster", age=1)
        task = Task(name="Cage Clean", duration=15, priority=3, due_date=today, frequency="one-off")
        pet.tasks.append(task)
        owner = Owner(name="Eve", available_time_mins=60, pets=[pet])
        pet.complete_task(task)
        assert task.is_completed is True
        tasks_after = owner.get_all_tasks()
        assert not any(t.name == "Cage Clean" for t in tasks_after)

    def test_daily_task_resurfaces_tomorrow(self, today):
        """TC-WF-STATE-02: Daily task advances due_date by one day on completion."""
        pet = Pet(name="Cleo", species="cat", age=3)
        task = Task(name="Morning Feed", duration=5, priority=4, due_date=today, frequency="daily")
        pet.tasks.append(task)
        pet.complete_task(task)
        assert task.due_date == today + timedelta(days=1)
        assert task.is_completed is False

    def test_weekly_task_advances_seven_days(self, today):
        pet = Pet(name="Max", species="dog", age=2)
        task = Task(name="Bath", duration=25, priority=3, due_date=today, frequency="weekly")
        pet.tasks.append(task)
        pet.complete_task(task)
        assert task.due_date == today + timedelta(weeks=1)
        assert task.is_completed is False

    def test_zero_budget_skips_all_tasks(self, today):
        pet = Pet(name="Mole", species="dog", age=1)
        pet.tasks.append(Task(name="Fetch", duration=10, priority=3, due_date=today))
        owner = Owner(name="Frank", available_time_mins=0, pets=[pet])
        result = Scheduler(owner).generate_schedule()
        assert result.scheduled_tasks == []
        assert len(result.skipped_tasks) == 1
        assert "all tasks skipped" in result.reasoning.lower()

    def test_sort_tasks_priority_then_duration(self, today):
        pet = Pet(name="Rex", species="dog", age=2)
        t1 = Task(name="A", duration=30, priority=3, due_date=today)
        t2 = Task(name="B", duration=10, priority=5, due_date=today)
        t3 = Task(name="C", duration=5, priority=5, due_date=today)
        pet.tasks.extend([t1, t2, t3])
        owner = Owner(name="G", available_time_mins=120, pets=[pet])
        scheduler = Scheduler(owner)
        sorted_tasks = scheduler.sort_tasks([t1, t2, t3])
        # priority 5 first (shorter duration first among ties), then priority 3
        assert sorted_tasks[0].name == "C"
        assert sorted_tasks[1].name == "B"
        assert sorted_tasks[2].name == "A"


# ---------------------------------------------------------------------------
# TC-GUARD: Guardrail workflow
# ---------------------------------------------------------------------------


class TestGuardrailWorkflow:
    """TC-GUARD-01 through TC-GUARD-05."""

    def _owner_with_required(self, today):
        pet = Pet(name="Biscuit", species="dog", age=2)
        req1 = Task(name="Morning Walk", duration=30, priority=5, is_required=True, due_date=today)
        req2 = Task(name="Feeding", duration=10, priority=5, is_required=True, due_date=today)
        opt = Task(name="Play", duration=20, priority=2, due_date=today)
        pet.tasks.extend([req1, req2, opt])
        return Owner(name="Alice", available_time_mins=120, pets=[pet])

    def test_clean_schedule_passes_guardrail(self, today):
        """TC-GUARD-01: guardrail passes when all required tasks are present."""
        owner = self._owner_with_required(today)
        proposed = {
            "scheduled_tasks": [
                {"name": "Morning Walk", "duration": 30, "priority": 5, "is_required": True,
                 "is_completed": False, "start_time": None, "frequency": "daily",
                 "due_date": today.isoformat()},
                {"name": "Feeding", "duration": 10, "priority": 5, "is_required": True,
                 "is_completed": False, "start_time": None, "frequency": "one-off",
                 "due_date": today.isoformat()},
            ],
            "skipped_tasks": [],
            "total_time_used": 40,
            "reasoning": "OK",
        }
        result = run_guardrail(proposed, owner)
        assert result.is_clean
        assert result.guardrail_triggered is False
        assert result.violations == []
        assert result.as_ui_message() == ""

    def test_guardrail_detects_missing_required_tasks(self, today, tmp_path, monkeypatch):
        """TC-GUARD-02: guardrail fires when required tasks are dropped."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "data").mkdir()

        owner = self._owner_with_required(today)
        proposed = {
            "scheduled_tasks": [
                {"name": "Play", "duration": 20, "priority": 2, "is_required": False,
                 "is_completed": False, "start_time": None, "frequency": "one-off",
                 "due_date": today.isoformat()},
            ],
            "skipped_tasks": [],
            "total_time_used": 20,
            "reasoning": "Partial",
        }
        result = run_guardrail(proposed, owner)
        assert result.guardrail_triggered is True
        assert result.violation_count == 2
        assert "Morning Walk" in result.violations
        assert "Feeding" in result.violations

    def test_guardrail_restores_missing_tasks_in_corrected_schedule(self, today, tmp_path, monkeypatch):
        """TC-GUARD-03: corrected_schedule contains all required tasks."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "data").mkdir()

        owner = self._owner_with_required(today)
        proposed = {
            "scheduled_tasks": [],
            "skipped_tasks": [],
            "total_time_used": 0,
            "reasoning": "Empty",
        }
        result = run_guardrail(proposed, owner)
        corrected_names = [t["name"] for t in result.corrected_schedule["scheduled_tasks"]]
        assert "Morning Walk" in corrected_names
        assert "Feeding" in corrected_names

    def test_guardrail_ui_message_format(self, today, tmp_path, monkeypatch):
        """TC-GUARD-04: as_ui_message() contains violation count and task names."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "data").mkdir()

        owner = self._owner_with_required(today)
        proposed = {"scheduled_tasks": [], "skipped_tasks": [], "total_time_used": 0, "reasoning": ""}
        result = run_guardrail(proposed, owner)
        msg = result.as_ui_message()
        assert "2" in msg  # violation count
        assert "Morning Walk" in msg
        assert "Feeding" in msg
        assert "restored" in msg.lower()

    def test_guardrail_writes_audit_log(self, today, tmp_path, monkeypatch):
        """TC-GUARD-05: violation event is appended to guardrail_violations.jsonl."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "data").mkdir()

        owner = self._owner_with_required(today)
        proposed = {"scheduled_tasks": [], "skipped_tasks": [], "total_time_used": 0, "reasoning": ""}

        import agent.guardrail as guardrail_mod
        orig_path = guardrail_mod.VIOLATION_LOG_PATH
        log_path = tmp_path / "data" / "guardrail_violations.jsonl"
        monkeypatch.setattr(guardrail_mod, "VIOLATION_LOG_PATH", log_path)

        run_guardrail(proposed, owner)

        assert log_path.exists()
        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["event"] == "GUARDRAIL_VIOLATION"
        assert record["owner_name"] == "Alice"
        assert record["violation_count"] == 2
        assert "Morning Walk" in record["missing_required_tasks"]

        monkeypatch.setattr(guardrail_mod, "VIOLATION_LOG_PATH", orig_path)

    def test_validate_required_tasks_direct(self, today):
        """TC-GUARD-06: validate_required_tasks() injects required tasks correctly."""
        pet = Pet(name="Bolt", species="dog", age=1)
        req = Task(name="Meds", duration=5, priority=5, is_required=True, due_date=today)
        opt = Task(name="Nap", duration=60, priority=1, due_date=today)
        pet.tasks.extend([req, opt])
        owner = Owner(name="Hank", available_time_mins=120, pets=[pet])

        proposed = {"scheduled_tasks": [], "skipped_tasks": [], "total_time_used": 0, "reasoning": ""}
        raw = validate_required_tasks(proposed, owner)
        assert raw["guardrail_triggered"] is True
        assert "Meds" in raw["violations"]
        corrected_names = [t["name"] for t in raw["corrected_schedule"]["scheduled_tasks"]]
        assert "Meds" in corrected_names


# ---------------------------------------------------------------------------
# TC-PERS: Persistence round-trip
# ---------------------------------------------------------------------------


class TestPersistenceRoundTrip:
    """TC-PERS-01 through TC-PERS-03."""

    def _full_owner(self, today):
        pet = Pet(name="Noodle", species="cat", age=7)
        t1 = Task(
            name="Vet",
            duration=45,
            priority=5,
            is_required=True,
            is_completed=False,
            start_time="10:00",
            frequency="one-off",
            due_date=today,
        )
        t2 = Task(
            name="Feed",
            duration=5,
            priority=4,
            is_required=False,
            is_completed=False,
            start_time="07:30",
            frequency="daily",
            due_date=today,
        )
        pet.tasks.extend([t1, t2])
        owner = Owner(name="Iris", available_time_mins=180, pets=[pet])
        return owner

    def test_round_trip_owner_name(self, tmp_path, today):
        owner = self._full_owner(today)
        path = str(tmp_path / "owner.json")
        owner.save_to_json(path)
        loaded = Owner.load_from_json(path)
        assert loaded.name == "Iris"

    def test_round_trip_available_time(self, tmp_path, today):
        owner = self._full_owner(today)
        path = str(tmp_path / "owner.json")
        owner.save_to_json(path)
        loaded = Owner.load_from_json(path)
        assert loaded.available_time_mins == 180

    def test_round_trip_pet_fields(self, tmp_path, today):
        owner = self._full_owner(today)
        path = str(tmp_path / "owner.json")
        owner.save_to_json(path)
        loaded = Owner.load_from_json(path)
        pet = loaded.pets[0]
        assert pet.name == "Noodle"
        assert pet.species == "cat"
        assert pet.age == 7

    def test_round_trip_task_all_fields(self, tmp_path, today):
        owner = self._full_owner(today)
        path = str(tmp_path / "owner.json")
        owner.save_to_json(path)
        loaded = Owner.load_from_json(path)
        vet = next(t for t in loaded.pets[0].tasks if t.name == "Vet")
        assert vet.duration == 45
        assert vet.priority == 5
        assert vet.is_required is True
        assert vet.start_time == "10:00"
        assert vet.frequency == "one-off"
        assert vet.due_date == today

    def test_round_trip_daily_task_frequency(self, tmp_path, today):
        owner = self._full_owner(today)
        path = str(tmp_path / "owner.json")
        owner.save_to_json(path)
        loaded = Owner.load_from_json(path)
        feed = next(t for t in loaded.pets[0].tasks if t.name == "Feed")
        assert feed.frequency == "daily"

    def test_defect1_regression_filename_only_path(self, tmp_path, monkeypatch, today):
        """DEFECT-1 regression: save_to_json must not crash on bare filename (no dir)."""
        monkeypatch.chdir(tmp_path)
        owner = self._full_owner(today)
        # This must NOT raise FileNotFoundError on Windows
        owner.save_to_json("owner_bare.json")
        assert (tmp_path / "owner_bare.json").exists()


# ---------------------------------------------------------------------------
# TC-DEF: DEFECT-2 regression — detect_conflicts malformed task dicts
# ---------------------------------------------------------------------------


class TestDetectConflictsRobustness:
    """TC-DEF-01 through TC-DEF-03: DEFECT-2 regression tests."""

    def test_missing_duration_returns_empty_conflicts(self, tools, today):
        """DEFECT-2 regression: missing 'duration' key must not raise KeyError."""
        malformed = [
            {
                "name": "Walk",
                "start_time": "08:00",
                "priority": 3,
                "is_required": False,
                "is_completed": False,
                "frequency": "one-off",
                "due_date": today.isoformat(),
                # 'duration' intentionally omitted
            }
        ]
        result = tools.detect_conflicts(malformed)
        assert result["conflict_count"] == 0
        assert result["conflicts"] == []

    def test_missing_name_returns_empty_conflicts(self, tools, today):
        """DEFECT-2 regression: missing 'name' key must not raise KeyError."""
        malformed = [
            {
                "duration": 30,
                "start_time": "08:00",
                "priority": 3,
                "is_required": False,
                "is_completed": False,
                "frequency": "one-off",
                "due_date": today.isoformat(),
                # 'name' intentionally omitted
            }
        ]
        result = tools.detect_conflicts(malformed)
        assert result["conflict_count"] == 0

    def test_missing_priority_returns_empty_conflicts(self, tools, today):
        """DEFECT-2 regression: missing 'priority' key must not raise KeyError."""
        malformed = [
            {
                "name": "Bath",
                "duration": 20,
                "start_time": "09:00",
                "is_required": False,
                "is_completed": False,
                "frequency": "one-off",
                "due_date": today.isoformat(),
                # 'priority' intentionally omitted
            }
        ]
        result = tools.detect_conflicts(malformed)
        assert result["conflict_count"] == 0

    def test_valid_non_overlapping_tasks_no_conflict(self, tools, today):
        """Sanity check: properly formed non-overlapping tasks produce no conflict."""
        tasks = [
            {
                "name": "Walk",
                "duration": 30,
                "start_time": "08:00",
                "priority": 3,
                "is_required": False,
                "is_completed": False,
                "frequency": "daily",
                "due_date": today.isoformat(),
            },
            {
                "name": "Feed",
                "duration": 10,
                "start_time": "09:00",
                "priority": 4,
                "is_required": False,
                "is_completed": False,
                "frequency": "daily",
                "due_date": today.isoformat(),
            },
        ]
        result = tools.detect_conflicts(tasks)
        assert result["conflict_count"] == 0

    def test_valid_overlapping_tasks_detected(self, tools, today):
        """Sanity check: properly formed overlapping tasks are detected."""
        tasks = [
            {
                "name": "Walk",
                "duration": 30,
                "start_time": "08:00",
                "priority": 3,
                "is_required": False,
                "is_completed": False,
                "frequency": "daily",
                "due_date": today.isoformat(),
            },
            {
                "name": "Feed",
                "duration": 15,
                "start_time": "08:20",  # overlaps Walk (08:00–08:30)
                "priority": 4,
                "is_required": False,
                "is_completed": False,
                "frequency": "daily",
                "due_date": today.isoformat(),
            },
        ]
        result = tools.detect_conflicts(tasks)
        assert result["conflict_count"] == 1

    def test_empty_list_returns_zero_conflicts(self, tools):
        result = tools.detect_conflicts([])
        assert result["conflict_count"] == 0


# ---------------------------------------------------------------------------
# TC-METRICS: RunMetrics format_summary()
# ---------------------------------------------------------------------------


class TestRunMetrics:
    """TC-METRICS-01 through TC-METRICS-04."""

    def _record(self, **kwargs):
        defaults = dict(
            call_index=1,
            method="test_call",
            model="claude-haiku-4-5-20251001",
            latency_ms=120.0,
            input_tokens=100,
            output_tokens=50,
            cache_creation_tokens=500,
            cache_read_tokens=0,
        )
        defaults.update(kwargs)
        return ApiCallRecord(**defaults)

    def test_format_summary_contains_header(self):
        m = RunMetrics()
        m.add(self._record())
        summary = m.format_summary()
        assert "### Token & Latency Report" in summary

    def test_format_summary_contains_api_calls_row(self):
        m = RunMetrics()
        m.add(self._record(call_index=1))
        m.add(self._record(call_index=2))
        summary = m.format_summary()
        assert "| API calls | 2 |" in summary

    def test_format_summary_contains_cache_hit_rate(self):
        m = RunMetrics()
        r1 = self._record(cache_read_tokens=0)
        r2 = self._record(call_index=2, cache_read_tokens=400)
        m.add(r1)
        m.add(r2)
        summary = m.format_summary()
        assert "Cache hit rate" in summary
        assert "50% of calls" in summary

    def test_format_summary_token_reduction_nonzero(self):
        m = RunMetrics()
        m.add(self._record(
            input_tokens=100,
            cache_creation_tokens=1000,
            cache_read_tokens=500,
        ))
        summary = m.format_summary()
        assert "Token reduction (cache)" in summary
        # reduction = 500/(100+1000+500) = 31.25%
        assert "31.2%" in summary

    def test_empty_metrics_zero_reduction(self):
        m = RunMetrics()
        assert m.effective_token_reduction_pct == 0.0
        assert m.cache_hit_rate == 0.0

    def test_total_tokens_property(self):
        r = self._record(
            input_tokens=100,
            output_tokens=50,
            cache_creation_tokens=200,
            cache_read_tokens=300,
        )
        assert r.total_tokens == 650

    def test_cache_saved_property_true(self):
        r = self._record(cache_read_tokens=10)
        assert r.cache_saved is True

    def test_cache_saved_property_false(self):
        r = self._record(cache_read_tokens=0)
        assert r.cache_saved is False

    def test_reset_clears_calls(self):
        m = RunMetrics()
        m.add(self._record())
        m.reset()
        assert m.total_calls == 0


# ---------------------------------------------------------------------------
# TC-CHAT: PawPalOrchestrator.parse_nl_task (mocked LLM)
# ---------------------------------------------------------------------------


def _make_text_block(text: str):
    b = MagicMock()
    b.type = "text"
    b.text = text
    return b


def _make_tool_use_block(name: str, input_dict: dict, block_id: str = "tu_1"):
    b = MagicMock()
    b.type = "tool_use"
    b.name = name
    b.input = input_dict
    b.id = block_id
    return b


def _make_response(stop_reason: str, content: list, usage=None):
    resp = MagicMock()
    resp.stop_reason = stop_reason
    resp.content = content
    if usage is None:
        u = MagicMock()
        u.input_tokens = 100
        u.output_tokens = 50
        u.cache_creation_input_tokens = 0
        u.cache_read_input_tokens = 0
        resp.usage = u
    else:
        resp.usage = usage
    return resp


class TestChatOrchestratorFlow:
    """TC-CHAT-01 through TC-CHAT-05."""

    def _orch(self, mock_client, today):
        pet = Pet(name="Koda", species="dog", age=3)
        owner = Owner(name="Jane", available_time_mins=120, pets=[pet])
        orch = PawPalOrchestrator(owner=owner, client=mock_client, max_resolution_steps=3)
        return orch, owner, owner.pets[0]

    def test_successful_task_addition_via_nl(self, mock_client, today):
        """TC-CHAT-01: add_task tool_use → ParseResult(success=True)."""
        orch, owner, pet = self._orch(mock_client, today)
        tool_input = {
            "pet_name": "Koda",
            "name": "Evening Walk",
            "duration": 20,
            "priority": 3,
        }
        mock_client.messages.create.return_value = _make_response(
            stop_reason="tool_use",
            content=[_make_tool_use_block("add_task", tool_input)],
        )
        result = orch.parse_nl_task("Add a 20-min evening walk for Koda")
        assert result.success is True
        assert result.task_dict is not None
        # Task was actually added to the pet
        assert any(t.name == "Evening Walk" for t in pet.tasks)

    def test_clarification_request_returned(self, mock_client, today):
        """TC-CHAT-02: JSON clarification_request → ParseResult(needs_clarification=True)."""
        orch, owner, _ = self._orch(mock_client, today)
        clarification_json = json.dumps({
            "type": "clarification_request",
            "question": "Which pet should I add this task to?",
            "missing_fields": ["pet_name"],
        })
        mock_client.messages.create.return_value = _make_response(
            stop_reason="end_turn",
            content=[_make_text_block(clarification_json)],
        )
        result = orch.parse_nl_task("Add a grooming session")
        assert result.success is False
        assert result.needs_clarification is True
        assert "Which pet" in result.clarification_question

    def test_unknown_pet_returns_error(self, mock_client, today):
        """TC-CHAT-03: add_task with unknown pet_name → ParseResult(success=False)."""
        orch, owner, _ = self._orch(mock_client, today)
        tool_input = {
            "pet_name": "Fluffy",  # does not exist
            "name": "Bath",
            "duration": 15,
            "priority": 2,
        }
        mock_client.messages.create.return_value = _make_response(
            stop_reason="tool_use",
            content=[_make_tool_use_block("add_task", tool_input)],
        )
        result = orch.parse_nl_task("Give Fluffy a bath")
        assert result.success is False
        assert result.error is not None
        assert "Fluffy" in result.error or "not found" in result.error.lower()

    def test_trace_recorded_after_successful_parse(self, mock_client, today):
        """TC-CHAT-04: agent_trace grows by one step per successful tool call."""
        orch, owner, _ = self._orch(mock_client, today)
        tool_input = {"pet_name": "Koda", "name": "Morning Feed", "duration": 5, "priority": 4}
        mock_client.messages.create.return_value = _make_response(
            stop_reason="tool_use",
            content=[_make_tool_use_block("add_task", tool_input)],
        )
        assert len(orch.agent_trace) == 0
        orch.parse_nl_task("Feed Koda in the morning")
        assert len(orch.agent_trace) == 1
        step = orch.agent_trace[0]
        assert step.action_tool == "add_task"

    def test_clear_trace_resets_state(self, mock_client, today):
        """TC-CHAT-05: clear_trace() resets trace and metrics."""
        orch, owner, _ = self._orch(mock_client, today)
        tool_input = {"pet_name": "Koda", "name": "Nap", "duration": 60, "priority": 1}
        mock_client.messages.create.return_value = _make_response(
            stop_reason="tool_use",
            content=[_make_tool_use_block("add_task", tool_input)],
        )
        orch.parse_nl_task("Let Koda nap")
        assert len(orch.agent_trace) == 1

        orch.clear_trace()
        assert orch.agent_trace == []
        assert orch.run_metrics.total_calls == 0

    def test_metrics_updated_after_api_call(self, mock_client, today):
        """TC-CHAT-06: RunMetrics records call count and token usage."""
        orch, owner, _ = self._orch(mock_client, today)
        tool_input = {"pet_name": "Koda", "name": "Swim", "duration": 40, "priority": 3}
        u = MagicMock()
        u.input_tokens = 200
        u.output_tokens = 80
        u.cache_creation_input_tokens = 1000
        u.cache_read_input_tokens = 0
        mock_client.messages.create.return_value = _make_response(
            stop_reason="tool_use",
            content=[_make_tool_use_block("add_task", tool_input)],
            usage=u,
        )
        orch.parse_nl_task("Take Koda swimming")
        assert orch.run_metrics.total_calls == 1
        assert orch.run_metrics.total_input_tokens == 200
        assert orch.run_metrics.total_output_tokens == 80
        assert orch.run_metrics.total_cache_creation_tokens == 1000


# ---------------------------------------------------------------------------
# TC-ORCHTRACE: TraceStep serialisation
# ---------------------------------------------------------------------------


class TestTraceStep:
    """TC-TRACE-01: TraceStep.as_dict() produces the correct keys."""

    def test_as_dict_has_all_keys(self):
        step = TraceStep(
            step=1,
            thought="I should walk the dog.",
            action_tool="reschedule_task",
            action_input={"pet_name": "Rex", "task_name": "Walk", "new_start_time": "10:00"},
            observation={"success": True},
        )
        d = step.as_dict()
        assert set(d.keys()) == {"step", "thought", "action_tool", "action_input", "observation"}
        assert d["step"] == 1
        assert d["action_tool"] == "reschedule_task"

    def test_as_dict_round_trip_serialisable(self):
        step = TraceStep(
            step=2,
            thought="Checking for conflicts.",
            action_tool="detect_conflicts",
            action_input={"tasks": []},
            observation={"conflict_count": 0, "conflicts": []},
        )
        # Must be JSON-serialisable (no datetime or other non-primitive types)
        serialised = json.dumps(step.as_dict())
        restored = json.loads(serialised)
        assert restored["step"] == 2


# ---------------------------------------------------------------------------
# TC-CORRECTION: CorrectionResult helpers
# ---------------------------------------------------------------------------


class TestCorrectionResult:
    """TC-CRRES-E2E: CorrectionResult contract."""

    def _clean(self):
        return CorrectionResult(
            violations=[],
            corrected_schedule={"scheduled_tasks": [], "skipped_tasks": [], "total_time_used": 0, "reasoning": ""},
            guardrail_triggered=False,
        )

    def _violated(self):
        return CorrectionResult(
            violations=["Morning Walk", "Feeding"],
            corrected_schedule={
                "scheduled_tasks": [
                    {"name": "Morning Walk"}, {"name": "Feeding"}
                ],
                "skipped_tasks": [],
                "total_time_used": 40,
                "reasoning": "Restored.",
            },
            guardrail_triggered=True,
        )

    def test_is_clean_true_when_no_violations(self):
        assert self._clean().is_clean is True

    def test_is_clean_false_when_violations(self):
        assert self._violated().is_clean is False

    def test_violation_count_zero_when_clean(self):
        assert self._clean().violation_count == 0

    def test_violation_count_correct_when_violated(self):
        assert self._violated().violation_count == 2

    def test_as_ui_message_empty_when_clean(self):
        assert self._clean().as_ui_message() == ""

    def test_as_ui_message_nonempty_when_violated(self):
        msg = self._violated().as_ui_message()
        assert msg != ""
        assert "Morning Walk" in msg
        assert "Feeding" in msg

    def test_timestamp_is_set(self):
        cr = self._clean()
        assert cr.timestamp  # non-empty string

    def test_timestamp_is_iso_format(self):
        from datetime import datetime
        cr = self._clean()
        # Should parse without raising
        datetime.fromisoformat(cr.timestamp.replace("Z", "+00:00"))


# ---------------------------------------------------------------------------
# TC-STVAL: Start-time HH:MM format validation (FIX #5)
# ---------------------------------------------------------------------------


class TestStartTimeValidation:
    """TC-STVAL-01 through TC-STVAL-07: regex used by the Add Task form."""

    _RE = r"^\d{2}:\d{2}$"

    def test_valid_hhmm_passes(self):
        import re
        assert re.match(self._RE, "09:00") is not None

    def test_midnight_passes(self):
        import re
        assert re.match(self._RE, "00:00") is not None

    def test_end_of_day_passes(self):
        import re
        assert re.match(self._RE, "23:59") is not None

    def test_single_digit_hour_fails(self):
        import re
        assert re.match(self._RE, "9:00") is None

    def test_am_pm_notation_fails(self):
        import re
        assert re.match(self._RE, "9am") is None

    def test_seconds_included_fails(self):
        import re
        assert re.match(self._RE, "09:00:00") is None

    def test_empty_string_maps_to_none(self):
        st_val = "".strip() or None
        assert st_val is None

    def test_whitespace_only_maps_to_none(self):
        st_val = "   ".strip() or None
        assert st_val is None

    def test_valid_value_preserved(self):
        st_val = "14:30".strip() or None
        assert st_val == "14:30"


# ---------------------------------------------------------------------------
# TC-DUPCOMP: Duplicate task name completion via index (FIX #4)
# ---------------------------------------------------------------------------


class TestDuplicateTaskCompletion:
    """TC-DUPCOMP-01 through TC-DUPCOMP-04: index-based completion is unambiguous."""

    def _pet_with_duplicate_walks(self, today):
        pet = Pet(name="Rex", species="dog", age=3)
        pet.tasks = [
            Task(name="Walk", duration=30, priority=3, due_date=today, frequency="one-off"),
            Task(name="Walk", duration=45, priority=5, is_required=True, due_date=today, frequency="daily"),
            Task(name="Feed", duration=10, priority=5, due_date=today, frequency="daily"),
        ]
        return pet

    def test_complete_by_index_0_retires_first_task(self, today):
        pet = self._pet_with_duplicate_walks(today)
        task = pet.tasks[0]
        pet.complete_task(task)
        assert pet.tasks[0].is_completed is True
        assert pet.tasks[1].is_completed is False

    def test_complete_by_index_1_advances_second_task(self, today):
        pet = self._pet_with_duplicate_walks(today)
        task = pet.tasks[1]
        pet.complete_task(task)
        # daily — not retired, due_date advanced
        assert pet.tasks[1].is_completed is False
        assert pet.tasks[1].due_date == today + timedelta(days=1)
        # first Walk untouched
        assert pet.tasks[0].is_completed is False

    def test_index_lookup_via_identity(self, today):
        """id-based lookup (t is task) finds the correct task object."""
        pet = self._pet_with_duplicate_walks(today)
        target = pet.tasks[1]  # second Walk
        found_idx = next(
            (idx for idx, t in enumerate(pet.tasks) if t is target), None
        )
        assert found_idx == 1

    def test_third_distinct_task_not_affected(self, today):
        pet = self._pet_with_duplicate_walks(today)
        pet.complete_task(pet.tasks[0])
        assert pet.tasks[2].is_completed is False
