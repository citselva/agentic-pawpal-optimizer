from dataclasses import dataclass, field
from typing import List


@dataclass
class Task:
    name: str
    duration: int
    priority: int  # 1-5
    is_required: bool = False
    is_completed: bool = False

    def toggle_complete(self) -> None:
        self.is_completed = not self.is_completed


@dataclass
class ScheduleResult:
    scheduled_tasks: List[Task]
    skipped_tasks: List[Task]
    total_time_used: int
    reasoning: str


@dataclass
class Pet:
    name: str
    species: str
    age: int
    tasks: List[Task] = field(default_factory=list)

    def get_summary(self) -> str:
        return (
            f"{self.name} ({self.species}, age {self.age}) "
            f"— {len(self.tasks)} task(s)"
        )


@dataclass
class Owner:
    name: str
    available_time_mins: int
    pets: List[Pet] = field(default_factory=list)

    def __post_init__(self):
        if self.available_time_mins < 0:
            raise ValueError(
                f"available_time_mins cannot be negative, got {self.available_time_mins}"
            )

    def get_all_tasks(self) -> List[Task]:
        return [task for pet in self.pets for task in pet.tasks]


class Scheduler:
    def __init__(self, owner: Owner) -> None:
        self.owner = owner

    def generate_schedule(self) -> ScheduleResult:
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

        reasoning = " ".join(notes)
        return ScheduleResult(
            scheduled_tasks=scheduled,
            skipped_tasks=skipped,
            total_time_used=time_used,
            reasoning=reasoning,
        )
