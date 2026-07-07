"""Tests for the PawPal+ core system."""

from pawpal_system import (
    Task,
    Pet,
    Owner,
    Scheduler,
    Priority,
    Frequency,
)


def test_mark_complete_changes_status():
    # Arrange: a fresh task starts out NOT completed.
    task = Task("Morning walk", 30, Priority.HIGH)
    assert task.completed is False        # sanity check before we act

    # Act: mark it done.
    task.mark_complete()

    # Assert: the status actually flipped to True.
    assert task.completed is True


def test_add_task_increases_pet_task_count():
    # Arrange: a pet with no tasks yet.
    pet = Pet(name="Rex", species="dog", food="kibble")
    assert len(pet.tasks) == 0            # starts empty

    # Act: add one task.
    pet.add_task(Task("Feed dinner", 10, Priority.MEDIUM))

    # Assert: the pet's task count went up by one.
    assert len(pet.tasks) == 1


# ---------------------------------------------------------------------------
# Sorting correctness: tasks come back in chronological order
# ---------------------------------------------------------------------------

def test_sort_by_time_returns_chronological_order():
    # Arrange: three fixed-time tasks handed over out of order.
    scheduler = Scheduler()
    noon = Task("Lunch", 15, Priority.LOW, start_time=12 * 60)      # 12:00
    morning = Task("Walk", 30, Priority.HIGH, start_time=8 * 60)    # 08:00
    evening = Task("Dinner", 20, Priority.MEDIUM, start_time=18 * 60)  # 18:00

    # Act: sort by time.
    ordered = scheduler.sort_by_time([noon, morning, evening])

    # Assert: earliest first, latest last.
    assert [t.description for t in ordered] == ["Walk", "Lunch", "Dinner"]


def test_generate_plan_lays_out_tasks_chronologically():
    # Arrange: a pet whose tasks are added in non-chronological order.
    pet = Pet(name="Rex", species="dog", food="kibble")
    pet.add_task(Task("Evening walk", 30, Priority.HIGH, start_time=18 * 60))
    pet.add_task(Task("Morning walk", 30, Priority.HIGH, start_time=8 * 60))
    owner = Owner(name="Sam", pets=[pet], available_minutes=120)

    # Act: build the plan.
    scheduler = Scheduler().generate_plan(owner)

    # Assert: the resulting timeline is sorted by start time (non-decreasing).
    starts = [t.scheduled_start for t in scheduler.tasks]
    assert starts == sorted(starts)
    assert [t.description for t in scheduler.tasks] == ["Morning walk", "Evening walk"]


def test_sort_tasks_tie_break_is_deterministic():
    # Arrange: equal priority + equal duration -> description must break the tie,
    # and the result must not depend on the input order.
    scheduler = Scheduler()
    a = Task("Apple task", 10, Priority.HIGH)
    b = Task("Banana task", 10, Priority.HIGH)

    # Act: sort both orderings.
    forward = scheduler.sort_tasks([a, b])
    backward = scheduler.sort_tasks([b, a])

    # Assert: same deterministic order regardless of input order.
    assert [t.description for t in forward] == ["Apple task", "Banana task"]
    assert [t.description for t in backward] == ["Apple task", "Banana task"]


# ---------------------------------------------------------------------------
# Recurrence logic: a completed daily task comes back the next day
# ---------------------------------------------------------------------------

def test_completed_daily_task_recurs_next_day():
    # Arrange: one daily task, plenty of time.
    pet = Pet(name="Rex", species="dog", food="kibble")
    walk = Task("Morning walk", 30, Priority.HIGH, frequency=Frequency.DAILY)
    pet.add_task(walk)
    owner = Owner(name="Sam", pets=[pet], available_minutes=120)

    # Act 1: it's done today, so today's plan should hide it.
    walk.mark_complete()
    today = Scheduler().generate_plan(owner, day_index=0)
    assert walk not in today.tasks

    # Act 2: roll over to a new day, then plan again.
    owner.reset_day()
    tomorrow = Scheduler().generate_plan(owner, day_index=1)

    # Assert: reset cleared per-day state and the task is scheduled again.
    assert walk.completed is False
    assert walk in tomorrow.tasks


def test_weekly_task_not_due_midweek():
    # Arrange: a weekly task.
    task = Task("Brush fur", 20, Priority.LOW, frequency=Frequency.WEEKLY)

    # Assert: due on the cadence days (0, 7) but not in between.
    assert task.is_due(0) is True
    assert task.is_due(1) is False
    assert task.is_due(6) is False
    assert task.is_due(7) is True


# ---------------------------------------------------------------------------
# Conflict detection: overlapping / duplicate times are flagged
# ---------------------------------------------------------------------------

def test_scheduler_flags_duplicate_times():
    # Arrange: two tasks pinned to the exact same start time.
    pet = Pet(name="Rex", species="dog", food="kibble")
    pet.add_task(Task("Vet call", 30, Priority.HIGH, start_time=9 * 60))
    pet.add_task(Task("Grooming", 30, Priority.HIGH, start_time=9 * 60))
    owner = Owner(name="Sam", pets=[pet], available_minutes=120)

    # Act: build the plan.
    scheduler = Scheduler().generate_plan(owner)

    # Assert: exactly one overlapping pair is reported.
    assert len(scheduler.conflicts) == 1
    assert "conflict" in scheduler.reasoning.lower()


def test_back_to_back_tasks_do_not_conflict():
    # Arrange: one task ends exactly when the next begins (half-open windows).
    first = Task("Walk", 30, Priority.HIGH, start_time=8 * 60)   # 08:00-08:30
    second = Task("Feed", 30, Priority.HIGH, start_time=8 * 60 + 30)  # 08:30-09:00
    first.scheduled_start = first.start_time
    second.scheduled_start = second.start_time

    # Act + Assert: touching endpoints are NOT an overlap.
    assert first.overlaps(second) is False


def test_detect_conflicts_ignores_unscheduled_tasks():
    # Arrange: two tasks that were never placed on the clock.
    scheduler = Scheduler()
    a = Task("Walk", 30, Priority.HIGH)
    b = Task("Feed", 30, Priority.HIGH)

    # Act + Assert: no scheduled_start means nothing can overlap.
    assert scheduler.detect_conflicts([a, b]) == []


# ---------------------------------------------------------------------------
# Budget fitting edge cases
# ---------------------------------------------------------------------------

def test_task_that_exactly_fills_budget_is_included():
    # Arrange: a single task whose duration equals the whole budget.
    pet = Pet(name="Rex", species="dog", food="kibble")
    pet.add_task(Task("Long walk", 60, Priority.HIGH))
    owner = Owner(name="Sam", pets=[pet], available_minutes=60)

    # Act: build the plan.
    scheduler = Scheduler().generate_plan(owner)

    # Assert: exact fit is scheduled, nothing skipped.
    assert scheduler.task_count() == 1
    assert scheduler.skipped_tasks == []


def test_oversized_task_skipped_but_smaller_task_still_fits():
    # Arrange: a big HIGH task that won't fit, plus a small LOW one that will.
    pet = Pet(name="Rex", species="dog", food="kibble")
    pet.add_task(Task("Huge outing", 90, Priority.HIGH))
    pet.add_task(Task("Quick treat", 10, Priority.LOW))
    owner = Owner(name="Sam", pets=[pet], available_minutes=30)

    # Act: build the plan.
    scheduler = Scheduler().generate_plan(owner)

    # Assert: skipping the oversized task must not block the smaller one.
    scheduled = [t.description for t in scheduler.tasks]
    skipped = [t.description for t in scheduler.skipped_tasks]
    assert "Quick treat" in scheduled
    assert "Huge outing" in skipped
