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


class Frequency(Enum):
    """How often a task recurs. Value = number of days between occurrences."""

    DAILY = 1
    WEEKLY = 7


def parse_hhmm(text: str) -> int | None:
    """Parse a "HH:MM" string into minutes since midnight.

    Returns None for blank or malformed input, so callers can treat a task
    with no fixed time as "anytime" (the scheduler will place it).
    """
    text = text.strip()
    if not text:
        return None
    try:
        hours_str, minutes_str = text.split(":")
        hours, minutes = int(hours_str), int(minutes_str)
    except ValueError:
        return None
    if 0 <= hours < 24 and 0 <= minutes < 60:
        return hours * 60 + minutes
    return None


def format_hhmm(minutes: int | None) -> str:
    """Format minutes-since-midnight as "HH:MM" (empty string for None)."""
    if minutes is None:
        return ""
    minutes %= 24 * 60
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


@dataclass
class Task:
    """A single pet-care task to be scheduled."""

    description: str            # what to do, e.g. "morning walk"
    duration: int              # minutes
    priority: Priority
    location: str = ""
    frequency: Frequency = Frequency.DAILY   # how often the task recurs
    completed: bool = False     # has this task been done today?
    specific_note: str = ""
    pet_name: str = ""          # which pet this task belongs to (set by Pet.add_task)
    # A fixed appointment (minutes since midnight), set by the user. None means
    # "flexible" - the Scheduler is free to place it wherever it fits.
    start_time: int | None = None
    # Where the Scheduler actually placed this task in today's plan (minutes
    # since midnight). Written by generate_plan; None until then.
    scheduled_start: int | None = None

    @property
    def scheduled_end(self) -> int | None:
        """Minute-of-day this task finishes, or None if not yet scheduled."""
        if self.scheduled_start is None:
            return None
        return self.scheduled_start + self.duration

    def time_label(self) -> str:
        """Return the scheduled time window, e.g. "08:00-08:30", or "anytime"."""
        if self.scheduled_start is None:
            return "anytime"
        return f"{format_hhmm(self.scheduled_start)}-{format_hhmm(self.scheduled_end)}"

    def priority_label(self) -> str:
        """Return a human-readable priority label, e.g. "Priority: High"."""
        return f"Priority: {self.priority.name.title()}"

    def is_due(self, day_index: int) -> bool:
        """Decide whether this recurring task should appear on a given day.

        Recurrence is modelled as a fixed cadence: the task repeats every
        ``frequency.value`` days (DAILY = 1, WEEKLY = 7), so it is due whenever
        ``day_index`` is an exact multiple of that interval.

        Args:
            day_index: Days counted from a reference day 0. Day 0 is due for
                every task, since 0 is a multiple of any interval.

        Returns:
            True if the task recurs on ``day_index``.

        Note:
            The cadence is absolute (days 0, 7, 14, ...) and ignores when the
            task was created. That keeps the math trivial and is fine for a
            daily planner; a fuller app would anchor to each task's start date.
        """
        return day_index % self.frequency.value == 0

    def reset_for_new_day(self) -> None:
        """Clear per-day state so a recurring task can be done again tomorrow."""
        self.completed = False
        self.scheduled_start = None

    def overlaps(self, other: "Task") -> bool:
        """Report whether this task's scheduled time collides with another's.

        Uses the standard half-open interval overlap test: two windows
        ``[a_start, a_end)`` and ``[b_start, b_end)`` intersect exactly when
        each one starts strictly before the other ends. Because the intervals
        are half-open, back-to-back tasks (one ends at the minute the next
        begins) do NOT count as overlapping.

        Args:
            other: The task to compare against.

        Returns:
            True if both tasks are scheduled and their time windows intersect.
            A task with no ``scheduled_start`` never overlaps anything.
        """
        if self.scheduled_start is None or other.scheduled_start is None:
            return False
        return (
            self.scheduled_start < other.scheduled_end
            and other.scheduled_start < self.scheduled_end
        )

    def mark_complete(self) -> None:
        """Mark this task as done."""
        self.completed = True

    def __str__(self) -> str:
        """Return a one-line summary of this task for printing."""
        status = "done" if self.completed else "todo"
        return (
            f"[{self.priority_label()}] {self.description} "
            f"({self.duration} min, {self.frequency.name.title()}) - {status}"
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

    def reset_day(self) -> None:
        """Reset every task's per-day state (call at the start of a new day)."""
        for task in self.all_tasks():
            task.reset_for_new_day()


@dataclass
class Scheduler:
    """The brain: retrieves tasks across pets, organizes them, builds a plan.

    `tasks` holds the organized plan once generated; `reasoning` explains it.
    """

    tasks: list[Task] = field(default_factory=list)
    reasoning: str = ""
    day_start: int = 8 * 60   # when the day begins (minutes since midnight; 08:00)
    conflicts: list[tuple[Task, Task]] = field(default_factory=list)  # overlapping pairs
    skipped_tasks: list[Task] = field(default_factory=list)           # didn't fit the budget

    def retrieve_tasks(self, owner: Owner) -> list[Task]:
        """Pull every task from the owner's pets.

        The Scheduler asks the Owner for all its tasks; the Owner is the one
        that loops over its pets. This keeps each class responsible for its
        own data (see Owner.all_tasks).
        """
        return owner.all_tasks()

    def sort_tasks(self, tasks: list[Task]) -> list[Task]:
        """Order tasks for planning: most important (and quickest) first.

        The sort key is the tuple ``(priority.value, duration, description)``:
          1. priority - HIGH (1) sorts before MEDIUM (2) before LOW (3);
          2. duration - among equal priority, shorter tasks come first so more
             of them fit within the time budget;
          3. description - a final tie-breaker so the result is stable and
             deterministic regardless of the input order.

        Args:
            tasks: The tasks to order (not mutated).

        Returns:
            A new list ordered for greedy scheduling (see generate_plan).
        """
        return sorted(tasks, key=lambda t: (t.priority.value, t.duration, t.description))

    def sort_by_time(self, tasks: list[Task]) -> list[Task]:
        """Order tasks chronologically for a timeline / do-in-order view.

        Each task is keyed by the best time available: its assigned
        ``scheduled_start`` if the plan has placed it, otherwise its fixed
        ``start_time``. Tasks with no time at all ("anytime") sort to the end,
        and description breaks any remaining ties for a deterministic order.

        Args:
            tasks: The tasks to order (not mutated).

        Returns:
            A new list in earliest-first order.
        """
        def key(t: Task) -> tuple[bool, int, str]:
            when = t.scheduled_start if t.scheduled_start is not None else t.start_time
            return (when is None, when or 0, t.description)

        return sorted(tasks, key=key)

    def filter_by_priority(self, tasks: list[Task], level: Priority) -> list[Task]:
        """Return only the tasks at the given priority level."""
        return [t for t in tasks if t.priority == level]

    def filter_by_urgency(self, tasks: list[Task]) -> list[Task]:
        """Return only the HIGH-priority (urgent) tasks."""
        return self.filter_by_priority(tasks, Priority.HIGH)

    def filter_by_pet(self, tasks: list[Task], pet_name: str) -> list[Task]:
        """Return only the tasks belonging to the named pet."""
        return [t for t in tasks if t.pet_name == pet_name]

    def filter_by_status(self, tasks: list[Task], completed: bool) -> list[Task]:
        """Return only the tasks whose completed flag matches `completed`.

        e.g. filter_by_status(tasks, completed=False) -> the still-to-do tasks.
        """
        return [t for t in tasks if t.completed == completed]

    def filter_due(self, tasks: list[Task], day_index: int) -> list[Task]:
        """Return only the tasks that recur on the given day (see Task.is_due)."""
        return [t for t in tasks if t.is_due(day_index)]

    def detect_conflicts(self, tasks: list[Task]) -> list[tuple[Task, Task]]:
        """Return every pair of tasks whose scheduled times overlap.

        Checks all pairs (O(n^2)) - simple and order-independent, which is fine
        for a day's worth of tasks. Each clashing pair is returned once.
        """
        conflicts: list[tuple[Task, Task]] = []
        for i, first in enumerate(tasks):
            for second in tasks[i + 1:]:
                if first.overlaps(second):
                    conflicts.append((first, second))
        return conflicts

    def describe_conflicts(self) -> list[str]:
        """Return one human-readable line per detected conflict."""
        lines: list[str] = []
        for first, second in self.conflicts:
            same_pet = (
                " (same pet - can't be in two places!)"
                if first.pet_name and first.pet_name == second.pet_name
                else ""
            )
            lines.append(
                f"{first.time_label()} {first.description} overlaps "
                f"{second.time_label()} {second.description}{same_pet}"
            )
        return lines

    def generate_plan(self, owner: Owner, day_index: int = 0) -> "Scheduler":
        """Build a plan for the given day from the owner's pets and time.

        Steps: retrieve all tasks -> drop completed ones -> drop tasks not due
        today -> sort by priority -> greedily fit into the available minutes
        -> stamp clock times -> return the plan in chronological order.

        day_index selects which day to plan (0 = today; see Task.is_due).
        """
        available = owner.time_availability()
        pending = self.filter_by_status(self.retrieve_tasks(owner), completed=False)
        due = self.filter_due(pending, day_index)
        not_due = len(pending) - len(due)
        ordered = self.sort_tasks(due)

        chosen: list[Task] = []
        skipped_tasks: list[Task] = []
        used = 0
        for task in ordered:
            if used + task.duration <= available:
                chosen.append(task)
                used += task.duration
            else:
                skipped_tasks.append(task)

        # Assign clock times. A task with a fixed start_time keeps it; the
        # running clock is pushed past its end so flexible tasks don't pile on
        # top of it. Flexible tasks drop into the next open slot in turn.
        clock = self.day_start
        for task in chosen:
            if task.start_time is not None:
                task.scheduled_start = task.start_time
                clock = max(clock, task.scheduled_start + task.duration)
            else:
                task.scheduled_start = clock
                clock += task.duration

        # Present the plan as a timeline (earliest first) rather than by priority.
        self.tasks = self.sort_by_time(chosen)
        self.skipped_tasks = skipped_tasks
        # Fixed appointments can still land on top of flexible tasks, so scan
        # the finished timeline for overlaps and report them.
        self.conflicts = self.detect_conflicts(self.tasks)
        self.reasoning = (
            f"Scheduled {len(chosen)} task(s) using {used}/{available} min, "
            f"chosen by priority and laid out from {format_hhmm(self.day_start)}. "
            f"{len(skipped_tasks)} task(s) didn't fit; {not_due} not due today; "
            f"{len(self.conflicts)} time conflict(s)."
        )
        return self

    def total_duration(self) -> int:
        """Return the summed duration (minutes) of all tasks in the plan."""
        return sum(task.duration for task in self.tasks)

    def task_count(self) -> int:
        """Return the number of tasks in the plan."""
        return len(self.tasks)

    def _print_footer(self) -> None:
        """Print the totals, the reasoning, and any conflicts / unfit tasks."""
        print(f"\nTotal: {self.task_count()} task(s), {self.total_duration()} min")
        print(f"Why: {self.reasoning}")
        if self.conflicts:
            print("\nConflicts:")
            for line in self.describe_conflicts():
                print(f"  - {line}")
        if self.skipped_tasks:
            print("\nDidn't fit today:")
            for task in self.skipped_tasks:
                print(f"  - {task.description} ({task.duration} min, {task.priority.name.title()})")

    def display(self) -> None:
        """Print the plan as an aligned table, in do-first order."""
        print("=== Today's Schedule (do these in order) ===")
        if not self.tasks:
            print("(no tasks scheduled)")
            self._print_footer()
            return

        # Build the header plus one row of cells per task (all strings).
        headers = ["#", "Time", "Pet", "Priority", "Task", "Duration", "Frequency", "Status"]
        rows = []
        for i, task in enumerate(self.tasks, start=1):
            rows.append([
                str(i),
                task.time_label(),
                task.pet_name or "Unassigned",
                task.priority.name.title(),
                task.description,
                f"{task.duration} min",
                task.frequency.name.title(),
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

        self._print_footer()


if __name__ == "__main__":
    # Small demo so you can run this file directly and see it work.
    rex = Pet(name="Rex", species="dog", food="kibble")
    rex.add_task(Task("Morning walk", 30, Priority.HIGH, location="park"))
    rex.add_task(Task("Feed dinner", 10, Priority.MEDIUM))

    mimi = Pet(name="Mimi", species="cat", food="tuna")
    mimi.add_task(Task("Clean litter", 15, Priority.HIGH))
    mimi.add_task(Task("Brush fur", 20, Priority.LOW, frequency=Frequency.WEEKLY))

    owner = Owner(name="Sam", pets=[rex, mimi], available_minutes=60)

    scheduler = Scheduler()
    scheduler.generate_plan(owner)
    scheduler.display()
