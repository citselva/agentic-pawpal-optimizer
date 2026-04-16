import unittest
from datetime import date, timedelta

from pawpal_system import Owner, Pet, Scheduler, Task


class TestPawPal(unittest.TestCase):
    """Comprehensive test suite for PawPal+ scheduler and task logic.

    setUp builds a reusable baseline Owner → Pet → Scheduler graph.
    Individual tests add tasks directly so each case controls its own
    input data precisely.
    """

    def setUp(self):
        """Create a standard owner/pet fixture used as the base for every test."""
        self.pet = Pet(name="Buddy", species="Dog", age=3)
        self.owner = Owner(name="Alex", available_time_mins=60, pets=[self.pet])
        self.scheduler = Scheduler(self.owner)

    # ------------------------------------------------------------------
    # Existing baseline tests (preserved)
    # ------------------------------------------------------------------

    def test_task_toggle(self):
        """toggle_complete flips is_completed and is idempotent on double-call."""
        task = Task(name="Walk", duration=30, priority=3)
        task.toggle_complete()
        self.assertTrue(task.is_completed, "First toggle should set is_completed to True")
        task.toggle_complete()
        self.assertFalse(task.is_completed, "Second toggle should reset is_completed to False")

    def test_pet_task_addition(self):
        """Tasks appended to pet.tasks are stored and retrievable."""
        task = Task(name="Feed", duration=10, priority=5)
        self.pet.tasks.append(task)
        self.assertEqual(len(self.pet.tasks), 1, "Pet should hold exactly one task after one append")

    # ------------------------------------------------------------------
    # TC-SORT: Sorting correctness
    # ------------------------------------------------------------------

    def test_sorting_correctness(self):
        """sort_tasks implements (-priority, duration) so higher priority wins;
        among equal-priority tasks, shorter duration is scheduled first."""
        low_priority = Task(name="Play",       duration=5,  priority=2)
        high_priority = Task(name="Medication", duration=30, priority=5)
        same_pri_long = Task(name="Bath",       duration=45, priority=3)
        same_pri_short = Task(name="Brush",     duration=10, priority=3)

        tasks = [low_priority, same_pri_long, high_priority, same_pri_short]
        result = self.scheduler.sort_tasks(tasks)

        self.assertEqual(
            result[0].name, "Medication",
            "priority=5 task must be first regardless of duration",
        )
        self.assertEqual(
            result[1].name, "Brush",
            "Among priority=3 tasks, shorter duration (10 min) must come before longer (45 min)",
        )
        self.assertEqual(
            result[2].name, "Bath",
            "priority=3 long-duration task must follow the shorter priority=3 task",
        )
        self.assertEqual(
            result[3].name, "Play",
            "priority=2 task must be last",
        )

    def test_sorting_does_not_mutate_source_list(self):
        """sort_tasks must return a new list; the caller's list must be unchanged."""
        task_a = Task(name="A", duration=5, priority=1)
        task_b = Task(name="B", duration=5, priority=5)
        original = [task_a, task_b]

        self.scheduler.sort_tasks(original)

        self.assertEqual(
            original[0].name, "A",
            "sort_tasks must not sort the source list in place",
        )

    # ------------------------------------------------------------------
    # TC-STATE: Recurrence and state transitions
    # ------------------------------------------------------------------

    def test_daily_recurrence(self):
        """complete_task on a 'daily' task advances due_date by 1 day and
        does NOT retire the task (is_completed must stay False)."""
        today = date.today()
        task = Task(name="Feed", duration=10, priority=5, frequency="daily", due_date=today)
        self.pet.tasks.append(task)

        self.pet.complete_task(task)

        self.assertFalse(
            task.is_completed,
            "Daily task must NOT be marked is_completed=True — it recurs tomorrow",
        )
        self.assertEqual(
            task.due_date,
            today + timedelta(days=1),
            "Daily task due_date must advance by exactly 1 day",
        )

    def test_weekly_recurrence(self):
        """complete_task on a 'weekly' task advances due_date by 7 days and
        does NOT retire the task."""
        today = date.today()
        task = Task(name="Bath", duration=20, priority=3, frequency="weekly", due_date=today)
        self.pet.tasks.append(task)

        self.pet.complete_task(task)

        self.assertFalse(
            task.is_completed,
            "Weekly task must NOT be marked is_completed=True — it recurs next week",
        )
        self.assertEqual(
            task.due_date,
            today + timedelta(weeks=1),
            "Weekly task due_date must advance by exactly 7 days",
        )

    def test_one_off_recurrence(self):
        """complete_task on a 'one-off' task permanently retires it via is_completed=True."""
        task = Task(name="Vet Visit", duration=60, priority=5, frequency="one-off")
        self.pet.tasks.append(task)

        self.pet.complete_task(task)

        self.assertTrue(
            task.is_completed,
            "One-off task must be marked is_completed=True after completion",
        )

    def test_one_off_task_excluded_from_schedule_after_completion(self):
        """TC-STATE-01b: After completing a one-off task it must not re-enter
        get_all_tasks() and must not be rescheduled on the same day.

        get_all_tasks() filters by ``due_date <= today and not is_completed``,
        so a completed one-off task is permanently excluded from scheduling.
        """
        task = Task(name="Vet Visit", duration=60, priority=5, frequency="one-off")
        self.pet.tasks.append(task)

        self.pet.complete_task(task)
        remaining = self.owner.get_all_tasks()

        self.assertNotIn(
            task, remaining,
            "Completed one-off task must be excluded from get_all_tasks() — "
            "PRODUCTION BUG: get_all_tasks() does not filter by is_completed, "
            "so this task is currently re-scheduled on the same day it was completed.",
        )

    def test_daily_recurrence_resurfaces_next_day(self):
        """Completing a daily task must configure it to resurface in tomorrow's schedule.

        The task object is mutated in place rather than replaced, but functionally
        it acts as a 'new task for the following day': it vanishes from today's
        get_all_tasks() and its due_date guarantees it reappears when tomorrow's
        date is reached.

        This is the three-way contract for daily recurrence:
          1. NOT in today's schedule (excluded immediately).
          2. due_date == tomorrow (guaranteed to resurface).
          3. is_completed == False (task is recurring, not retired).
        """
        today    = date.today()
        tomorrow = today + timedelta(days=1)
        task = Task(name="Feed", duration=10, priority=5, frequency="daily", due_date=today)
        self.pet.tasks.append(task)

        self.pet.complete_task(task)

        self.assertNotIn(
            task, self.owner.get_all_tasks(),
            "Completed daily task must NOT appear in today's get_all_tasks()",
        )
        self.assertEqual(
            task.due_date, tomorrow,
            "due_date must equal tomorrow — this is what guarantees the task "
            "resurfaces in the next day's schedule",
        )
        self.assertFalse(
            task.is_completed,
            "is_completed must stay False — daily tasks recur, they are never retired",
        )

    def test_daily_task_excluded_from_todays_schedule_after_completion(self):
        """After complete_task advances due_date to tomorrow, get_all_tasks
        must not return the task for today's schedule."""
        today = date.today()
        task = Task(name="Feed", duration=10, priority=5, frequency="daily", due_date=today)
        self.pet.tasks.append(task)

        self.pet.complete_task(task)
        remaining = self.owner.get_all_tasks()

        self.assertNotIn(
            task, remaining,
            "Completed daily task (due_date=tomorrow) must not appear in today's get_all_tasks()",
        )

    # ------------------------------------------------------------------
    # TC-CONF: Conflict detection
    # ------------------------------------------------------------------

    def test_conflict_detection(self):
        """Overlapping tasks must be flagged; adjacent tasks sharing an
        exact boundary must NOT be flagged (strict < operator)."""

        # --- True overlap ---
        overlap_a = Task(name="Feed", duration=30, priority=5, start_time="09:00")
        overlap_b = Task(name="Walk", duration=20, priority=4, start_time="09:15")
        # overlap_a window: 09:00–09:30; overlap_b starts inside that window

        conflicts = self.scheduler.detect_conflicts([overlap_a, overlap_b])

        self.assertEqual(
            len(conflicts), 1,
            "One conflict expected when task B starts before task A ends",
        )
        self.assertIn(
            (overlap_a, overlap_b), conflicts,
            "Conflict tuple must identify the correct (prev, curr) pair",
        )

        # --- Adjacent boundary (no conflict) ---
        adjacent_a = Task(name="Feed",   duration=30, priority=5, start_time="08:00")
        adjacent_b = Task(name="Groom",  duration=20, priority=4, start_time="08:30")
        # adjacent_a ends exactly at 08:30; adjacent_b starts at 08:30
        # "08:30" < "08:30" is False → no conflict

        adjacent_conflicts = self.scheduler.detect_conflicts([adjacent_a, adjacent_b])

        self.assertEqual(
            len(adjacent_conflicts), 0,
            "Adjacent tasks (end == start) must NOT be flagged as conflicting — "
            "the strict < operator defines a closed-open interval [start, end)",
        )

    def test_chronological_ordering_in_conflict_detection(self):
        """detect_conflicts() must sort tasks by start_time internally before
        the sweep-line comparison, so that results are correct regardless of
        the order tasks are passed in.

        Proof: tasks are deliberately given in REVERSE chronological order
        (afternoon first, morning second). Without an internal sort the sweep
        would treat the afternoon task as 'prev' and check whether the morning
        task starts before the afternoon task ends — producing a false positive.
        With the correct internal sort, morning is evaluated first and the
        adjacent boundary is correctly treated as non-conflicting.
        """
        # Provided in reverse order on purpose
        afternoon = Task(name="Walk",  duration=60, priority=4, start_time="10:00")
        morning   = Task(name="Feed",  duration=60, priority=5, start_time="09:00")
        # Correct chronological order: morning 09:00–10:00 | afternoon 10:00–11:00
        # Adjacent, not overlapping → 0 conflicts expected.
        # Without internal sort: afternoon is prev (ends 11:00), morning is curr
        #   "09:00" < "11:00" → True → FALSE POSITIVE conflict

        conflicts = self.scheduler.detect_conflicts([afternoon, morning])

        self.assertEqual(
            len(conflicts), 0,
            "Tasks given in reverse chronological order must still be evaluated "
            "in the correct order; adjacent morning/afternoon tasks must NOT conflict",
        )

    def test_scheduler_flags_duplicate_start_times(self):
        """Two tasks with the same start_time are always overlapping because one
        starts while the other is already running.

        Verifies two things:
          1. detect_conflicts() returns a conflict tuple for the pair.
          2. generate_schedule() appends a WARNING to the reasoning string,
             so the problem surfaces to the owner through the UI.
        """
        task_a = Task(
            name="Morning Pill",
            duration=10,
            priority=5,
            is_required=True,
            start_time="08:00",
        )
        task_b = Task(
            name="Morning Feed",
            duration=20,
            priority=5,
            is_required=True,
            start_time="08:00",
        )
        self.pet.tasks.extend([task_a, task_b])

        # Level 1: detect_conflicts() sees the overlap directly
        # After sort both sit at "08:00"; prev ends at "08:10" or "08:20".
        # curr.start_time "08:00" < prev.end_time → True → conflict flagged.
        conflicts = self.scheduler.detect_conflicts([task_a, task_b])
        self.assertEqual(
            len(conflicts), 1,
            "Two tasks at the same start_time must produce exactly one conflict tuple: "
            "curr.start_time '08:00' < prev.end_time ('08:10' or '08:20') is True",
        )

        # Level 2: generate_schedule() must surface the WARNING in reasoning
        result = self.scheduler.generate_schedule()
        self.assertIn(
            "WARNING", result.reasoning,
            "Scheduler must append a WARNING to reasoning when duplicate start_times "
            "are detected in the final scheduled list",
        )

    def test_conflict_detection_untimed_tasks_ignored(self):
        """Tasks with no start_time must not raise an exception and must not
        participate in conflict comparison."""
        timed   = Task(name="Feed", duration=30, priority=5, start_time="09:00")
        untimed = Task(name="Pill", duration=5,  priority=5)  # start_time=None

        conflicts = self.scheduler.detect_conflicts([timed, untimed])

        self.assertEqual(
            len(conflicts), 0,
            "Untimed task must be silently excluded; no crash, no false conflict",
        )

    def test_conflict_detection_no_conflict(self):
        """Completely non-overlapping tasks must produce an empty conflicts list."""
        morning = Task(name="Feed",  duration=20, priority=5, start_time="08:00")
        evening = Task(name="Walk",  duration=30, priority=4, start_time="17:00")

        conflicts = self.scheduler.detect_conflicts([morning, evening])

        self.assertEqual(
            len(conflicts), 0,
            "Tasks separated by hours must produce zero conflicts",
        )

    # ------------------------------------------------------------------
    # TC-SCHED: Constraint exhaustion and scheduler phases
    # ------------------------------------------------------------------

    def test_zero_time_budget(self):
        """When available_time_mins is 0 the scheduler must return the early-exit
        ScheduleResult: no tasks scheduled, all tasks skipped, total_time_used=0,
        and the reasoning string must indicate no time was available."""
        task = Task(name="Walk", duration=30, priority=5)
        self.pet.tasks.append(task)

        zero_owner = Owner(name="Alex", available_time_mins=0, pets=[self.pet])
        result = Scheduler(zero_owner).generate_schedule()

        self.assertEqual(
            result.scheduled_tasks, [],
            "Zero time budget must produce an empty scheduled_tasks list",
        )
        self.assertEqual(
            result.total_time_used, 0,
            "total_time_used must be 0 when no time is available",
        )
        self.assertIn(
            task, result.skipped_tasks,
            "Every task must appear in skipped_tasks when budget is zero",
        )
        self.assertIn(
            "No time available", result.reasoning,
            "Reasoning must indicate that no time was available",
        )

    def test_required_tasks_exceed_budget_time_deficit(self):
        """Required tasks must always be scheduled even when their total duration
        exceeds available_time_mins. The reasoning must surface a 'Time Deficit' warning."""
        med = Task(name="Medication", duration=15, priority=5, is_required=True)
        self.pet.tasks.append(med)

        tight_owner = Owner(name="Alex", available_time_mins=10, pets=[self.pet])
        result = Scheduler(tight_owner).generate_schedule()

        self.assertIn(
            med, result.scheduled_tasks,
            "Required task must be scheduled even when it exceeds the time budget",
        )
        self.assertEqual(
            result.total_time_used, 15,
            "total_time_used must reflect actual time used, not the capped budget",
        )
        self.assertIn(
            "Time Deficit", result.reasoning,
            "Reasoning must warn the owner about the time deficit",
        )

    def test_exact_budget_match_no_deficit(self):
        """When required_time == available_time_mins exactly, no Time Deficit should
        be reported and optional tasks should be skipped (remaining=0)."""
        required  = Task(name="Medication", duration=30, priority=5, is_required=True)
        optional  = Task(name="Play",       duration=10, priority=3)
        self.pet.tasks.extend([required, optional])

        exact_owner = Owner(name="Alex", available_time_mins=30, pets=[self.pet])
        result = Scheduler(exact_owner).generate_schedule()

        self.assertIn(
            required, result.scheduled_tasks,
            "Required task must be scheduled when budget exactly covers it",
        )
        self.assertIn(
            optional, result.skipped_tasks,
            "Optional task must be skipped when no remaining time exists after required tasks",
        )
        self.assertNotIn(
            "Time Deficit", result.reasoning,
            "No Time Deficit warning should appear when required tasks fit exactly",
        )

    def test_optional_tasks_scheduled_by_priority(self):
        """When competing for limited remaining time, higher-priority optional tasks
        must be scheduled before lower-priority ones."""
        low_pri  = Task(name="Groom", duration=10, priority=2)
        high_pri = Task(name="Play",  duration=10, priority=4)
        self.pet.tasks.extend([low_pri, high_pri])

        # Only 10 minutes available — room for exactly one optional task
        tight_owner = Owner(name="Alex", available_time_mins=10, pets=[self.pet])
        result = Scheduler(tight_owner).generate_schedule()

        self.assertIn(
            high_pri, result.scheduled_tasks,
            "Higher-priority optional task (priority=4) must win the slot",
        )
        self.assertIn(
            low_pri, result.skipped_tasks,
            "Lower-priority optional task (priority=2) must be skipped when budget is exhausted",
        )

    def test_negative_time_budget_raises_value_error(self):
        """Owner.__post_init__ must reject available_time_mins < 0 with a ValueError
        before any scheduling can occur."""
        with self.assertRaises(ValueError, msg="Negative available_time_mins must raise ValueError"):
            Owner(name="Alex", available_time_mins=-1, pets=[])

    # ------------------------------------------------------------------
    # TC-FILTER: Date-based task filtering
    # ------------------------------------------------------------------

    def test_future_dated_tasks_excluded_from_schedule(self):
        """Tasks with due_date in the future must not appear in get_all_tasks()
        and therefore cannot enter the scheduler."""
        future_task = Task(
            name="Future Vet",
            duration=60,
            priority=5,
            due_date=date.today() + timedelta(days=1),
        )
        self.pet.tasks.append(future_task)

        actionable = self.owner.get_all_tasks()

        self.assertNotIn(
            future_task, actionable,
            "Future-dated task must be excluded from get_all_tasks() — due_date > today",
        )

    def test_overdue_tasks_included_in_schedule(self):
        """Tasks with due_date in the past (overdue) must appear in get_all_tasks()
        because the filter condition is due_date <= today."""
        overdue_task = Task(
            name="Missed Bath",
            duration=20,
            priority=3,
            due_date=date.today() - timedelta(days=1),
        )
        self.pet.tasks.append(overdue_task)

        actionable = self.owner.get_all_tasks()

        self.assertIn(
            overdue_task, actionable,
            "Overdue task (due_date < today) must be included in get_all_tasks()",
        )

    # ------------------------------------------------------------------
    # TC-CONF-04: Midnight Rollover — Known Limitation (Documentation Test)
    # ------------------------------------------------------------------

    def test_midnight_rollover_known_failure(self):
        """KNOWN LIMITATION: detect_conflicts() cannot identify overlaps that cross
        midnight because start_time values are sorted lexicographically.

        Scenario:
            late_task  starts at 23:50, runs 30 min → ends at 00:20 (next day)
            early_task starts at 00:05

        Expected correct behavior: conflict detected (00:05 falls inside 23:50–00:20).
        Actual behavior:           no conflict detected.

        Root cause: lexicographic sort places '00:05' before '23:50', so the
        sweep-line evaluates ('00:05' task as prev, '23:50' task as curr) and
        checks '23:50' < '00:15' → False → no conflict reported.

        This test asserts the CURRENT (broken) behavior so that:
          1. The blind spot is visible in CI output.
          2. Any future fix that makes this test pass will be caught immediately.
        """
        late_task = Task(
            name="Midnight Med",
            duration=30,
            priority=5,
            start_time="23:50",
        )
        # end_time = '00:20' (timedelta wraps correctly, but sort does not)
        early_task = Task(
            name="Morning Pill",
            duration=10,
            priority=5,
            start_time="00:05",
        )

        conflicts = self.scheduler.detect_conflicts([late_task, early_task])

        # Assert the KNOWN INCORRECT result to document the blind spot.
        # When this assertion fails, the bug has been fixed — update accordingly.
        self.assertEqual(
            len(conflicts), 0,
            "KNOWN LIMITATION: midnight-crossing overlap is NOT detected due to "
            "lexicographic string sort. '00:05' sorts before '23:50', so the "
            "sweep never compares them in the correct order. "
            "Expected correct result would be len(conflicts) == 1.",
        )


if __name__ == "__main__":
    unittest.main()
