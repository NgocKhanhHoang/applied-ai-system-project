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
from datetime import datetime
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
    try:
        clock = datetime.strptime(text.strip(), "%H:%M")
    except ValueError:
        return None
    return clock.hour * 60 + clock.minute


def format_hhmm(minutes: int | None) -> str:
    """Format minutes-since-midnight as "HH:MM" (empty string for None).

    Never wraps: a task running past midnight shows as "24:30", not "00:30".
    """
    if minutes is None:
        return ""
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

    def __post_init__(self) -> None:
        """Reject values that can't describe a real task."""
        if self.duration <= 0:
            raise ValueError(f"{self.description!r}: duration must be at least 1 minute.")
        if self.start_time is not None and not 0 <= self.start_time < 24 * 60:
            raise ValueError(f"{self.description!r}: start_time must be 00:00-23:59.")

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
        """Attach a task to this pet. A task belongs to one pet only."""
        if task.pet_name:
            raise ValueError(f"{task.description!r} already belongs to {task.pet_name}.")
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
        """Add a pet. Names must be unique - they identify a pet everywhere else."""
        if any(existing.name == pet.name for existing in self.pets):
            raise ValueError(f"There is already a pet called {pet.name!r}.")
        self.pets.append(pet)

    def time_availability(self) -> int:
        """Return the total minutes the owner has available today."""
        return self.available_minutes

    def remaining_minutes(self, day_index: int = 0) -> int:
        """Minutes still free today, after time spent on tasks already done."""
        spent = sum(
            task.duration
            for task in self.all_tasks()
            if task.completed and task.is_due(day_index)
        )
        return max(0, self.available_minutes - spent)

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
    day_end: int = 21 * 60    # when the day ends (minutes since midnight; 21:00)
    conflicts: list[tuple[Task, Task]] = field(default_factory=list)  # overlapping pairs
    skipped_tasks: list[Task] = field(default_factory=list)           # didn't fit the budget
    unplaced_tasks: list[Task] = field(default_factory=list)   # fit the budget, but no free slot
    warnings: list[str] = field(default_factory=list)          # appointments outside the day

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

        Answer 2 questions in order:
        1. Which tasks make the cut? Appointments first, then most important,
           until the owner's minutes run out.
        2. Where do they go? Appointments claim their slot first, then flexible
           tasks fill the gaps left between them.
        """
        available = owner.remaining_minutes(day_index)
        pending = self.filter_by_status(self.retrieve_tasks(owner), completed=False)
        due = self.filter_due(pending, day_index)
        not_due = len(pending) - len(due)
        self.warnings = []

        # Forget where things went in any earlier run, so a task that drops out
        # of today's plan can't still show an old time.
        for task in pending:
            task.scheduled_start = None

        # Which tasks fit the time budget? Appointments first (a pinned time is a
        # commitment, not a preference), then most important. sort is stable, so
        # priority order survives inside each group.
        ordered = self.sort_tasks(due)
        ordered.sort(key=lambda t: t.start_time is None)

        chosen: list[Task] = []
        skipped_tasks: list[Task] = []
        used = 0
        for task in ordered:
            if used + task.duration <= available:
                chosen.append(task)
                used += task.duration
            else:
                skipped_tasks.append(task)   # keep going, a shorter task may fit

        # Appointments go on the calendar first.
        placed: list[Task] = []
        busy: list[tuple[int, int]] = [] # (start, end)
        for task in chosen:
            if task.start_time is not None:  # appointment
                task.scheduled_start = task.start_time
                busy.append((task.scheduled_start, task.scheduled_end))
                placed.append(task)
                self._warn_if_outside_day(task)

        # Flexible tasks fill the gaps between appointments. If a task fits the budget but has no free slot, it is unplaced.
        unplaced: list[Task] = []
        for task in chosen:
            if task.start_time is None: # flexible
                slot = self.find_free_slot(task.duration, busy)
                if slot is None:
                    unplaced.append(task) # No room for today, try next task
                    used -= task.duration # give the minutes back
                else:
                    task.scheduled_start = slot
                    busy.append((slot, task.scheduled_end))
                    placed.append(task)

        self.tasks = self.sort_by_time(placed)
        self.skipped_tasks = skipped_tasks
        self.unplaced_tasks = unplaced
        self.conflicts = self.detect_conflicts(self.tasks)
        clash = self.overlap_minutes()
        self.reasoning = (
            f"Scheduled {len(placed)} task(s) using {used}/{available} min between "
            f"{format_hhmm(self.day_start)} and {format_hhmm(self.day_end)}, "
            f"appointments first, then by priority. {len(skipped_tasks)} over budget; "
            f"{len(unplaced)} had no free slot; {not_due} not due today; "
            f"{len(self.conflicts)} conflict(s)"
            + (f", {clash} min double-booked." if clash else ".")
        )
        return self

    def _warn_if_outside_day(self, task: Task) -> None:
        """Flag an appointment that falls outside the planning window."""
        if not self.day_start <= task.scheduled_start or task.scheduled_end > self.day_end:
            self.warnings.append(
                f"{task.description!r} ({task.time_label()}) is outside your "
                f"{format_hhmm(self.day_start)}-{format_hhmm(self.day_end)} day."
            )

    def overlap_minutes(self) -> int:
        """Minutes the plan double-books, summed over every conflicting pair."""
        return sum(
            min(a.scheduled_end, b.scheduled_end) - max(a.scheduled_start, b.scheduled_start)
            for a, b in self.conflicts
        )

    def find_free_slot(self, duration: int, busy: list[tuple[int, int]]) -> int | None:
        """Earliest start with `duration` free minutes, or None if the day is full.

        Walks the day from day_start, stepping over each slot already taken.
        """
        start = self.day_start
        for busy_start, busy_end in sorted(busy):
            if start + duration <= busy_start:
                return start          # it fits in the gap before this block
            start = max(start, busy_end)   # no room - jump past the block
        if start + duration <= self.day_end:
            return start              # it fits in the rest of the day
        return None                   # nowhere left to put it

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
        if self.unplaced_tasks:
            print("\nNo free time slot today:")
            for task in self.unplaced_tasks:
                print(f"  - {task.description} ({task.duration} min)")
        if self.warnings:
            print("\nWarnings:")
            for line in self.warnings:
                print(f"  - {line}")

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
