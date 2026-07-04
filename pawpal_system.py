"""PawPal+ core system.

Class skeletons generated from diagrams/uml_draft.mmd.
These are stubs only: attributes and method signatures are defined,
but the scheduling/behavior logic is not implemented yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Priority(Enum):
    """Task priority level. Lower number = higher priority (sorts first)."""

    HIGH = 1
    MEDIUM = 2
    LOW = 3


@dataclass
class Pet:
    """A pet that the owner is caring for."""

    name: str
    type: str          # e.g. "dog", "cat", "other"
    food: str
    care_needs: str = ""   # what the owner typed, e.g. "washing, walking"

    def pet_info(self) -> str:
        """Return a human-readable summary of this pet."""
        raise NotImplementedError

    def need_care(self) -> str:
        """Return what this pet needs.

        Uses the owner's typed care_needs if given; otherwise falls back
        to a sensible default based on the pet's type.
        """
        if self.care_needs:
            return self.care_needs
        elif self.type == "dog":
            return "walks and feeding"
        elif self.type == "cat":
            return "grooming and feeding"
        else:
            return "enrichment and feeding"


@dataclass
class Task:
    """A single pet-care task to be scheduled."""

    duration: int              # minutes
    priority: Priority
    location: str
    specific_note: str

    def is_urgent(self) -> str:
        """Return an urgency label based on this task's priority."""
        if self.priority == Priority.HIGH:
            return "Urgent"
        elif self.priority == Priority.MEDIUM:
            return "Medium"
        else:
            return "Normal"


@dataclass
class Plan:
    """A generated daily plan: an ordered set of tasks plus reasoning."""

    tasks: list[Task] = field(default_factory=list)
    reasoning: str = ""

    def display(self) -> None:
        """Print / render the plan for the user."""
        raise NotImplementedError

    def total_duration(self) -> int:
        """Return the summed duration (minutes) of all tasks in the plan."""
        raise NotImplementedError

    def task_count(self) -> int:
        """Return the number of tasks in the plan."""
        raise NotImplementedError


@dataclass
class Owner:
    """The pet owner who has pets, tasks, and a generated plan."""

    tasks: list[Task] = field(default_factory=list)
    pets: list[Pet] = field(default_factory=list)
    plan: Plan | None = None

    def time_availability(self) -> int:
        """Return the total minutes the owner has available today."""
        raise NotImplementedError

    def sort_tasks(self) -> list[Task]:
        """Return the owner's tasks sorted (e.g. by priority, duration)."""
        raise NotImplementedError

    def filter_by_urgency(self) -> list[Task]:
        """Return only the urgent tasks from the owner's task list."""
        raise NotImplementedError

    def generate_plan(self) -> Plan:
        """Build and return a Plan based on tasks and constraints."""
        raise NotImplementedError
