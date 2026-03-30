from dataclasses import dataclass, field
from typing import List


@dataclass
class Task:
    name: str
    duration: int
    priority: int  # 1-5
    category: str
    is_required: bool = False
    is_completed: bool = False


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


@dataclass
class User:
    name: str
    available_time_mins: int

    def __post_init__(self):
        if self.available_time_mins < 0:
            raise ValueError(
                f"available_time_mins cannot be negative, got {self.available_time_mins}"
            )


class CarePlanner:
    def __init__(self, user: User, pet: Pet) -> None:
        self.user = user
        self.pet = pet

    def generate_schedule(self) -> ScheduleResult:
        if self.user.available_time_mins == 0:
            return ScheduleResult(
                scheduled_tasks=[],
                skipped_tasks=self.pet.tasks[:],
                total_time_used=0,
                reasoning="No time available for tasks today.",
            )

        pass

    def get_reasoning(self) -> str:
        pass
