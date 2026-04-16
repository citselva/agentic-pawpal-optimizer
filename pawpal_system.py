import json
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple


@dataclass
class Task:
    """Represents a single care activity with duration, priority, and completion state."""

    name: str
    duration: int
    priority: int  # 1-5
    is_required: bool = False
    is_completed: bool = False
    start_time: Optional[str] = None  # e.g. '08:30' — used for chronological sorting
    frequency: str = 'one-off'  # 'one-off' | 'daily' | 'weekly'
    due_date: date = field(default_factory=date.today)

    @property
    def end_time(self) -> Optional[str]:
        """Computes the wall-clock time at which this task finishes.

        Parses ``start_time`` as a zero-padded ``HH:MM`` string, adds
        ``duration`` minutes using ``datetime.timedelta``, and formats the
        result back to ``HH:MM``. Tasks that span midnight will roll over
        correctly (e.g. 23:50 + 20 min → 00:10).

        Returns:
            The end time as a ``'HH:MM'`` string, or ``None`` when
            ``start_time`` is not set.
        """
        if self.start_time is None:
            return None
        t = datetime.strptime(self.start_time, "%H:%M")
        t += timedelta(minutes=self.duration)
        return t.strftime("%H:%M")

    def toggle_complete(self) -> None:
        """Toggles the completion status of the task."""
        self.is_completed = not self.is_completed

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "duration": self.duration,
            "priority": self.priority,
            "is_required": self.is_required,
            "is_completed": self.is_completed,
            "start_time": self.start_time,
            "frequency": self.frequency,
            "due_date": self.due_date.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        return cls(
            name=data["name"],
            duration=data["duration"],
            priority=data["priority"],
            is_required=data.get("is_required", False),
            is_completed=data.get("is_completed", False),
            start_time=data.get("start_time"),
            frequency=data.get("frequency", "one-off"),
            due_date=date.fromisoformat(data.get("due_date", date.today().isoformat())),
        )


@dataclass
class ScheduleResult:
    """Immutable result returned by the Scheduler containing scheduled/skipped tasks and reasoning."""

    scheduled_tasks: List[Task]
    skipped_tasks: List[Task]
    total_time_used: int
    reasoning: str


@dataclass
class Pet:
    """Models a single pet with its species, age, and associated care tasks."""

    name: str
    species: str
    age: int
    tasks: List[Task] = field(default_factory=list)

    def get_summary(self) -> str:
        """Returns a human-readable one-line summary of the pet and its task count."""
        return (
            f"{self.name} ({self.species}, age {self.age}) "
            f"— {len(self.tasks)} task(s)"
        )

    def complete_task(self, task: Task) -> None:
        """Marks a task done or advances its due date for recurring tasks.

        Behavior varies by ``task.frequency``:

        * ``'one-off'``: sets ``is_completed = True`` so the task is retired
          permanently and will no longer appear in future schedules.
        * ``'daily'``: advances ``due_date`` by one day so the task resurfaces
          in tomorrow's schedule without creating a new ``Task`` object.
        * ``'weekly'``: advances ``due_date`` by seven days so the task
          resurfaces on the same weekday next week.

        Args:
            task: The ``Task`` belonging to this pet that has been completed.
                Must already be present in ``self.tasks``; this method mutates
                the task in place and does not validate ownership.

        Returns:
            None
        """
        if task.frequency == 'daily':
            task.due_date = date.today() + timedelta(days=1)
        elif task.frequency == 'weekly':
            task.due_date = date.today() + timedelta(weeks=1)
        else:
            task.is_completed = True

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "species": self.species,
            "age": self.age,
            "tasks": [t.to_dict() for t in self.tasks],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Pet":
        pet = cls(name=data["name"], species=data["species"], age=data["age"])
        pet.tasks = [Task.from_dict(t) for t in data.get("tasks", [])]
        return pet


@dataclass
class Owner:
    """Represents a pet owner with a time budget and a collection of pets."""

    name: str
    available_time_mins: int
    pets: List[Pet] = field(default_factory=list)

    def __post_init__(self):
        """Validates that available_time_mins is non-negative after initialization."""
        if self.available_time_mins < 0:
            raise ValueError(
                f"available_time_mins cannot be negative, got {self.available_time_mins}"
            )

    def get_all_tasks(self) -> List[Task]:
        """Collects every task across all pets whose due date is today or earlier.

        Iterates over every ``Pet`` in ``self.pets`` and flattens their
        ``tasks`` lists into a single sequence, filtering out tasks whose
        ``due_date`` is in the future and tasks that are permanently completed.
        This drives the scheduler's view of what work is actionable on a given day.

        Returns:
            A flat list of ``Task`` objects due today or overdue that have not
            been permanently completed, in pet-insertion order. Returns an empty
            list when the owner has no pets or all tasks are future-dated or done.
        """
        today = date.today()
        return [
            task
            for pet in self.pets
            for task in pet.tasks
            if task.due_date <= today and not task.is_completed
        ]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "available_time_mins": self.available_time_mins,
            "pets": [p.to_dict() for p in self.pets],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Owner":
        owner = cls(name=data["name"], available_time_mins=data["available_time_mins"])
        owner.pets = [Pet.from_dict(p) for p in data.get("pets", [])]
        return owner

    def save_to_json(self, filename: str) -> None:
        parent = os.path.dirname(filename)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(filename, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load_from_json(cls, filename: str) -> "Owner":
        with open(filename, "r") as f:
            return cls.from_dict(json.load(f))

    def filter_tasks(
        self,
        pet_name: str = None,
        is_completed: bool = None,
    ) -> List[Task]:
        """Returns tasks matching the given criteria.

        Args:
            pet_name: If provided, only include tasks belonging to this pet.
            is_completed: If provided, only include tasks whose completion
                state matches this value.

        Returns:
            A list of Task objects that satisfy all supplied filters.
        """
        result: List[Task] = []
        for pet in self.pets:
            if pet_name is not None and pet.name != pet_name:
                continue
            for task in pet.tasks:
                if is_completed is not None and task.is_completed != is_completed:
                    continue
                result.append(task)
        return result


class Scheduler:
    """Builds an optimized daily care schedule for all of an owner's pets."""

    def __init__(self, owner: Owner) -> None:
        """Initializes the Scheduler with the given owner."""
        self.owner = owner

    def sort_tasks(self, tasks: List[Task] = None) -> List[Task]:
        """Returns tasks sorted by priority descending, then duration ascending.

        The composite key ``(-priority, duration)`` means higher-priority tasks
        come first; among ties on priority, shorter tasks come first.

        Args:
            tasks: Tasks to sort. Defaults to all tasks across the owner's pets.

        Returns:
            A new sorted list — the original list is not mutated.

        Bonus — chronological sort by start_time:
            If tasks carry a ``start_time`` string (e.g. ``'08:30'``), replace
            the lambda with::

                key=lambda t: (
                    tuple(int(p) for p in t.start_time.split(":"))
                    if t.start_time else (99, 99)
                )

            Zero-padded ``HH:MM`` strings sort lexicographically in the same
            order as chronologically, so ``str`` comparison alone also works —
            but converting to ``(int, int)`` tuples is more explicit and safe.
        """
        if tasks is None:
            tasks = self.owner.get_all_tasks()
        return sorted(tasks, key=lambda t: (-t.priority, t.duration))

    def detect_conflicts(self, tasks: List[Task]) -> List[Tuple[Task, Task]]:
        """Identifies pairs of tasks whose time windows overlap.

        Only tasks that carry a ``start_time`` value participate in conflict
        checking; tasks without one are silently ignored. The filtered list is
        sorted chronologically by ``start_time`` (lexicographic order on
        zero-padded ``HH:MM`` strings is equivalent to chronological order).
        Adjacent pairs are then compared: a conflict exists when the current
        task's ``start_time`` is strictly less than the previous task's
        ``end_time``, meaning the two windows intersect.

        Args:
            tasks: The list of ``Task`` objects to check, typically the
                scheduler's final ``scheduled`` list. Tasks without a
                ``start_time`` are excluded from comparison.

        Returns:
            A list of ``(prev, curr)`` tuples for each overlapping pair,
            in chronological order of occurrence. Returns an empty list when
            no conflicts are found or when fewer than two tasks have a
            ``start_time``.
        """
        timed = [t for t in tasks if t.start_time is not None]
        timed.sort(key=lambda t: t.start_time)
        conflicts: List[Tuple[Task, Task]] = []
        for i in range(1, len(timed)):
            prev, curr = timed[i - 1], timed[i]
            if prev.end_time is not None and curr.start_time < prev.end_time:
                conflicts.append((prev, curr))
        return conflicts

    def generate_schedule(self) -> ScheduleResult:
        """Builds a two-phase tiered schedule for the owner's available time budget.

        **Phase 1 — Required tasks:** All tasks flagged ``is_required=True`` are
        scheduled unconditionally, even if their combined duration exceeds
        ``available_time_mins``. A "Time Deficit" note is appended to the
        reasoning when this occurs, so the caller can surface it to the user.

        **Phase 2 — Optional tasks:** The remaining time is filled greedily with
        optional tasks sorted by ``priority`` descending. Each task is included
        only if its full ``duration`` fits within the remaining budget; tasks
        that do not fit are added to ``skipped_tasks``.

        **Conflict check:** After both phases, ``detect_conflicts()`` is called
        on the final scheduled list. Any overlapping ``start_time`` windows
        produce a ``WARNING`` entry appended to the reasoning string.

        Returns:
            A ``ScheduleResult`` containing:

            * ``scheduled_tasks``: ordered list of tasks accepted into the plan.
            * ``skipped_tasks``: optional tasks that exceeded the time budget.
            * ``total_time_used``: sum of durations for all scheduled tasks
              (may exceed ``available_time_mins`` when required tasks overflow).
            * ``reasoning``: human-readable narrative of scheduling decisions
              and any conflict warnings, suitable for display in the UI.
        """
        available = self.owner.available_time_mins
        all_tasks = self.owner.get_all_tasks()

        if available == 0:
            return ScheduleResult(
                scheduled_tasks=[],
                skipped_tasks=all_tasks[:],
                total_time_used=0,
                reasoning="No time available — all tasks skipped.",
            )

        scheduled: List[Task] = []
        skipped: List[Task] = []
        time_used = 0
        notes: List[str] = []

        # Phase 1: required tasks (always included)
        required = [t for t in all_tasks if t.is_required]
        required_time = sum(t.duration for t in required)

        scheduled.extend(required)
        time_used += required_time

        if required_time > available:
            notes.append(
                f"Time Deficit: required tasks need {required_time} min but only "
                f"{available} min available. All required tasks included anyway."
            )
        else:
            notes.append(
                f"Phase 1: {len(required)} required task(s) scheduled "
                f"({required_time} min)."
            )

        # Phase 2: optional tasks sorted by priority descending
        remaining = available - time_used
        optional = sorted(
            [t for t in all_tasks if not t.is_required],
            key=lambda t: t.priority,
            reverse=True,
        )

        optional_scheduled = 0
        for task in optional:
            if task.duration <= remaining:
                scheduled.append(task)
                time_used += task.duration
                remaining -= task.duration
                optional_scheduled += 1
            else:
                skipped.append(task)

        notes.append(
            f"Phase 2: {optional_scheduled} optional task(s) added by priority "
            f"({time_used - required_time} min). {len(skipped)} task(s) skipped."
        )

        conflicts = self.detect_conflicts(scheduled)
        for task_a, task_b in conflicts:
            notes.append(
                f"WARNING: Overlapping tasks detected: [{task_a.name}] and [{task_b.name}]."
            )

        reasoning = " ".join(notes)
        return ScheduleResult(
            scheduled_tasks=scheduled,
            skipped_tasks=skipped,
            total_time_used=time_used,
            reasoning=reasoning,
        )
