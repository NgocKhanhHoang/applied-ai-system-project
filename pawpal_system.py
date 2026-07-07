"""PawPal+ core system.

Four classes model a pet-care planner:

    Task      - one activity to be done (feed, walk, groom, ...).
    Pet       - a pet's details plus its own list of Tasks.
    Owner     - the person; owns several Pets and gives access to all their tasks.
    Scheduler - the "brain": retrieves every task from the owner's pets,
                organizes them, and builds a daily plan.
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
class Task:
    """A single pet-care task to be scheduled."""

    description: str            # what to do, e.g. "morning walk"
    duration: int              # minutes
    priority: Priority
    location: str = ""
    frequency: str = "daily"   # e.g. "daily", "weekly"
    completed: bool = False     # has this task been done today?
    specific_note: str = ""
    pet_name: str = ""          # which pet this task belongs to (set by Pet.add_task)

    def priority_label(self) -> str:
        """Return a human-readable priority label, e.g. "Priority: High"."""
        return f"Priority: {self.priority.name.title()}"

    def mark_complete(self) -> None:
        """Mark this task as done."""
        self.completed = True

    def __str__(self) -> str:
        """Return a one-line summary of this task for printing."""
        status = "done" if self.completed else "todo"
        return (
            f"[{self.priority_label()}] {self.description} "
            f"({self.duration} min, {self.frequency}) - {status}"
        )


@dataclass
class Pet:
    """A pet that the owner is caring for. Owns its own list of tasks."""

    name: str
    species: str          # e.g. "dog", "cat", "other"
    food: str
    tasks: list[Task] = field(default_factory=list)

    def add_task(self, task: Task) -> None:
        """Attach a task to this pet, tagging it with this pet's name."""
        task.pet_name = self.name
        self.tasks.append(task)

    def pet_info(self) -> str:
        """Return a human-readable summary of this pet."""
        return (
            f"{self.name} the {self.species} "
            f"(eats {self.food}) [{len(self.tasks)} task(s)]"
        )


@dataclass
class Owner:
    """The pet owner. Holds pets and provides access to all their tasks."""

    name: str = ""
    pets: list[Pet] = field(default_factory=list)
    available_minutes: int = 0   # total time the owner has today

    def add_pet(self, pet: Pet) -> None:
        """Add a pet to this owner."""
        self.pets.append(pet)

    def time_availability(self) -> int:
        """Return the total minutes the owner has available today."""
        return self.available_minutes

    def all_tasks(self) -> list[Task]:
        """Return every task from every one of the owner's pets as one flat list."""
        collected: list[Task] = []
        for pet in self.pets:
            collected.extend(pet.tasks)
        return collected


@dataclass
class Scheduler:
    """The brain: retrieves tasks across pets, organizes them, builds a plan.

    `tasks` holds the organized plan once generated; `reasoning` explains it.
    """

    tasks: list[Task] = field(default_factory=list)
    reasoning: str = ""

    def retrieve_tasks(self, owner: Owner) -> list[Task]:
        """Pull every task from the owner's pets.

        The Scheduler asks the Owner for all its tasks; the Owner is the one
        that loops over its pets. This keeps each class responsible for its
        own data (see Owner.all_tasks).
        """
        return owner.all_tasks()

    def sort_tasks(self, tasks: list[Task]) -> list[Task]:
        """Return tasks sorted by priority (high first), then shorter first."""
        return sorted(tasks, key=lambda t: (t.priority.value, t.duration))

    def filter_by_urgency(self, tasks: list[Task]) -> list[Task]:
        """Return only the HIGH-priority (urgent) tasks."""
        return [t for t in tasks if t.priority == Priority.HIGH]

    def generate_plan(self, owner: Owner) -> "Scheduler":
        """Build today's plan from the owner's pets and time available.

        Steps: retrieve all tasks -> drop completed ones -> sort by priority
        -> greedily fit tasks into the available minutes.
        """
        available = owner.time_availability()
        ordered = self.sort_tasks(self.retrieve_tasks(owner))

        chosen: list[Task] = []
        used = 0
        skipped = 0
        for task in ordered:
            if task.completed:
                continue
            if used + task.duration <= available:
                chosen.append(task)
                used += task.duration
            else:
                skipped += 1

        self.tasks = chosen
        self.reasoning = (
            f"Scheduled {len(chosen)} task(s) using {used}/{available} min, "
            f"ordered by priority. {skipped} task(s) didn't fit."
        )
        return self

    def total_duration(self) -> int:
        """Return the summed duration (minutes) of all tasks in the plan."""
        return sum(task.duration for task in self.tasks)

    def task_count(self) -> int:
        """Return the number of tasks in the plan."""
        return len(self.tasks)

    def display(self) -> None:
        """Print the plan as an aligned table, in do-first order."""
        print("=== Today's Schedule (do these in order) ===")
        if not self.tasks:
            print("(no tasks scheduled)")
            print(f"Total: {self.task_count()} task(s), {self.total_duration()} min")
            print(f"Why: {self.reasoning}")
            return

        # Build the header plus one row of cells per task (all strings).
        headers = ["#", "Pet", "Priority", "Task", "Duration", "Frequency", "Status"]
        rows = []
        for i, task in enumerate(self.tasks, start=1):
            rows.append([
                str(i),
                task.pet_name or "Unassigned",
                task.priority.name.title(),
                task.description,
                f"{task.duration} min",
                task.frequency,
                "done" if task.completed else "todo",
            ])

        # Each column is as wide as its widest cell (header included).
        widths = [
            max(len(headers[c]), *(len(row[c]) for row in rows))
            for c in range(len(headers))
        ]

        def format_row(cells: list[str]) -> str:
            return "  ".join(cell.ljust(widths[c]) for c, cell in enumerate(cells))

        print(format_row(headers))
        print("-" * len(format_row(headers)))
        for row in rows:
            print(format_row(row))

        print(f"\nTotal: {self.task_count()} task(s), {self.total_duration()} min")
        print(f"Why: {self.reasoning}")


if __name__ == "__main__":
    # Small demo so you can run this file directly and see it work.
    rex = Pet(name="Rex", species="dog", food="kibble")
    rex.add_task(Task("Morning walk", 30, Priority.HIGH, location="park"))
    rex.add_task(Task("Feed dinner", 10, Priority.MEDIUM))

    mimi = Pet(name="Mimi", species="cat", food="tuna")
    mimi.add_task(Task("Clean litter", 15, Priority.HIGH))
    mimi.add_task(Task("Brush fur", 20, Priority.LOW, frequency="weekly"))

    owner = Owner(name="Sam", pets=[rex, mimi], available_minutes=60)

    scheduler = Scheduler()
    scheduler.generate_plan(owner)
    scheduler.display()
