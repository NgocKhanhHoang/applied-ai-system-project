from __future__ import annotations

from pawpal_system import (
    Task, Pet, Owner, Scheduler, Priority, Frequency, parse_hhmm,
)


def show(title: str, tasks: list[Task]) -> None:
    """Print a titled list of tasks, one per line."""
    print(f"\n=== {title} ===")
    if not tasks:
        print("  (none)")
        return
    for task in tasks:
        print(f"  - {task}")


# --- Build pets and add tasks intentionally OUT OF ORDER ---
# Mixed priorities and durations, one fixed-time task, one weekly task, and one
# already-completed task, so the sorting/filtering methods have real work to do.
ice_cream = Pet(name="Ice Cream", species="dog", food="meat")
ice_cream.add_task(Task("Feed dinner", 10, Priority.MEDIUM))
ice_cream.add_task(Task("Morning walk", 60, Priority.HIGH, location="park"))
ice_cream.add_task(Task("Nail trim", 20, Priority.LOW, frequency=Frequency.WEEKLY))
# Two tasks pinned to the SAME time (12:00) - the owner can't do both at once,
# so the Scheduler should flag this as a conflict.
ice_cream.add_task(Task("Give medicine", 10, Priority.HIGH, start_time=parse_hhmm("12:00")))

meo = Pet(name="Meo", species="cat", food="tuna")
meo.add_task(Task("Brushing", 15, Priority.LOW, location="living room"))
meo.add_task(Task("Clean litter", 15, Priority.HIGH))
meo.add_task(Task("Playtime", 10, Priority.MEDIUM, completed=True))  # already done today
meo.add_task(Task("Feed lunch", 20, Priority.MEDIUM, start_time=parse_hhmm("12:00")))

owner = Owner(name="Lilia", pets=[ice_cream, meo], available_minutes=200)
scheduler = Scheduler()

all_tasks = owner.all_tasks()

# 1) As entered - deliberately unsorted.
show("Tasks as entered (out of order)", all_tasks)

# 2) sort_tasks: priority first (High -> Low), shorter duration as tie-breaker.
show("Sorted by priority (sort_tasks)", scheduler.sort_tasks(all_tasks))

# 3) filter_by_pet: just one pet's tasks.
show("Only Ice Cream's tasks (filter_by_pet)",
     scheduler.filter_by_pet(all_tasks, "Ice Cream"))

# 4) filter_by_status: hide the ones already done (Playtime drops out).
show("Only pending tasks (filter_by_status)",
     scheduler.filter_by_status(all_tasks, completed=False))

# 5) filter_by_priority: only the urgent ones.
show("Only HIGH priority (filter_by_priority)",
     scheduler.filter_by_priority(all_tasks, Priority.HIGH))

# 6) filter_due: the weekly "Nail trim" is due today (day 0) but not tomorrow (day 1).
show("Due on day 0 (filter_due)", scheduler.filter_due(all_tasks, day_index=0))
show("Due on day 1 - weekly Nail trim drops out (filter_due)",
     scheduler.filter_due(all_tasks, day_index=1))

# 7) Full plan: generate_plan sorts by TIME (sort_by_time), flags conflicts
#    (the two 12:00 tasks), and lists anything that didn't fit. display() prints
#    it all as a timeline, including a "Conflicts:" warning.
print("\n")
scheduler.generate_plan(owner)
scheduler.display()

# --- Verify the two same-time tasks were caught ---
same_time = [
    (a, b) for a, b in scheduler.conflicts
    if a.scheduled_start == b.scheduled_start
]
print(f"\nVerification: {len(same_time)} same-time conflict(s) detected.")
assert same_time, "Expected the two 12:00 tasks to be flagged as a conflict!"
print("PASS: Scheduler correctly warned about two tasks booked at the same time.")
