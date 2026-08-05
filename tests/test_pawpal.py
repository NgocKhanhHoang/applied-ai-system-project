"""Tests for the PawPal+ core system."""

import pytest

from pawpal_system import (
    Task,
    Pet,
    Owner,
    Scheduler,
    Priority,
    Frequency,
    parse_hhmm,
    format_hhmm,
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


# ---------------------------------------------------------------------------
# Placement: appointments first, then flexible tasks fill the gaps
# ---------------------------------------------------------------------------

def test_appointment_does_not_collide_with_flexible_task():
    # Arrange: one flexible HIGH task and one pinned MEDIUM appointment at 08:00.
    # Placing by priority would put the flexible task at 08:00 first, then stamp
    # the appointment on top of it.
    pet = Pet(name="Rex", species="dog", food="kibble")
    pet.add_task(Task("Feed", 30, Priority.HIGH))
    pet.add_task(Task("Vet", 30, Priority.MEDIUM, start_time=8 * 60))
    owner = Owner(name="Sam", pets=[pet], available_minutes=120)

    # Act: build the plan.
    scheduler = Scheduler().generate_plan(owner)

    # Assert: both are scheduled and the planner invented no conflict.
    assert scheduler.task_count() == 2
    assert scheduler.conflicts == []


def test_time_before_an_appointment_is_used():
    # Arrange: an appointment late in the day plus one flexible task.
    pet = Pet(name="Rex", species="dog", food="kibble")
    pet.add_task(Task("Vet", 30, Priority.HIGH, start_time=14 * 60))
    walk = Task("Walk", 30, Priority.LOW)
    pet.add_task(walk)
    owner = Owner(name="Sam", pets=[pet], available_minutes=120)

    # Act: build the plan.
    Scheduler().generate_plan(owner)

    # Assert: the walk goes in the morning, not pushed past the appointment.
    assert walk.scheduled_start == 8 * 60


def test_task_is_unplaced_when_no_gap_is_big_enough():
    # Arrange: a one-hour day and two 45-minute tasks. Both fit the budget, but
    # only one can fit on the clock.
    pet = Pet(name="Rex", species="dog", food="kibble")
    pet.add_task(Task("A walk", 45, Priority.HIGH))
    pet.add_task(Task("B walk", 45, Priority.HIGH))
    owner = Owner(name="Sam", pets=[pet], available_minutes=300)

    # Act: plan inside an 08:00-09:00 window.
    scheduler = Scheduler(day_start=8 * 60, day_end=9 * 60).generate_plan(owner)

    # Assert: one placed, one reported as having no slot - not silently dropped.
    assert scheduler.task_count() == 1
    assert [t.description for t in scheduler.unplaced_tasks] == ["B walk"]


def test_appointment_keeps_its_time_budget():
    # Arrange: only enough time for one task. The appointment is LOW priority,
    # the flexible task is HIGH - but an appointment is a commitment.
    pet = Pet(name="Rex", species="dog", food="kibble")
    pet.add_task(Task("Long walk", 30, Priority.HIGH))
    pet.add_task(Task("Vet visit", 30, Priority.LOW, start_time=9 * 60))
    owner = Owner(name="Sam", pets=[pet], available_minutes=30)

    # Act: build the plan.
    scheduler = Scheduler().generate_plan(owner)

    # Assert: the appointment wins the budget.
    assert [t.description for t in scheduler.tasks] == ["Vet visit"]
    assert [t.description for t in scheduler.skipped_tasks] == ["Long walk"]


def test_appointment_outside_the_day_is_flagged():
    # Arrange: an appointment at 20:00 in a day that ends at 17:00.
    pet = Pet(name="Rex", species="dog", food="kibble")
    pet.add_task(Task("Late vet", 30, Priority.HIGH, start_time=20 * 60))
    owner = Owner(name="Sam", pets=[pet], available_minutes=120)

    # Act: build the plan.
    scheduler = Scheduler(day_start=8 * 60, day_end=17 * 60).generate_plan(owner)

    # Assert: kept where the owner pinned it, but warned about.
    assert scheduler.task_count() == 1
    assert len(scheduler.warnings) == 1


def test_replanning_clears_a_dropped_tasks_time():
    # Arrange: a task that gets scheduled on the first run.
    pet = Pet(name="Rex", species="dog", food="kibble")
    walk = Task("Walk", 30, Priority.HIGH)
    pet.add_task(walk)
    owner = Owner(name="Sam", pets=[pet], available_minutes=60)
    Scheduler().generate_plan(owner)
    assert walk.scheduled_start is not None

    # Act: the owner loses their free time, so re-plan with no budget.
    owner.available_minutes = 0
    Scheduler().generate_plan(owner)

    # Assert: no stale time left over from the first plan.
    assert walk.scheduled_start is None
    assert walk.time_label() == "anytime"


# ---------------------------------------------------------------------------
# Time budget: finished work costs minutes
# ---------------------------------------------------------------------------

def test_completed_task_uses_up_available_minutes():
    # Arrange: 60 minutes, half of it already spent on a finished bath.
    pet = Pet(name="Rex", species="dog", food="kibble")
    bath = Task("Bath", 30, Priority.MEDIUM)
    pet.add_task(bath)
    walk = Task("Walk", 40, Priority.HIGH)
    pet.add_task(walk)
    owner = Owner(name="Sam", pets=[pet], available_minutes=60)
    bath.mark_complete()

    # Act + Assert: only 30 min are left, so the 40-min walk can't fit.
    assert owner.remaining_minutes() == 30
    scheduler = Scheduler().generate_plan(owner)
    assert scheduler.skipped_tasks == [walk]


# ---------------------------------------------------------------------------
# Input validation: bad data is refused at the door
# ---------------------------------------------------------------------------

def test_task_rejects_zero_or_negative_duration():
    # A task that takes no time can't be scheduled or checked for overlap.
    with pytest.raises(ValueError):
        Task("Nothing", 0, Priority.LOW)
    with pytest.raises(ValueError):
        Task("Backwards", -30, Priority.LOW)


def test_task_cannot_belong_to_two_pets():
    # Arrange: one Task object, two pets.
    rex = Pet(name="Rex", species="dog", food="kibble")
    mimi = Pet(name="Mimi", species="cat", food="tuna")
    walk = Task("Walk", 30, Priority.HIGH)
    rex.add_task(walk)

    # Act + Assert: sharing it would double-count its minutes and make it
    # overlap itself, so the second pet refuses it.
    with pytest.raises(ValueError):
        mimi.add_task(walk)


def test_owner_rejects_duplicate_pet_name():
    # Names identify a pet in the UI and in filter_by_pet, so they must be unique.
    owner = Owner(name="Sam")
    owner.add_pet(Pet(name="Rex", species="dog", food="kibble"))
    with pytest.raises(ValueError):
        owner.add_pet(Pet(name="Rex", species="cat", food="tuna"))


def test_parse_hhmm_accepts_real_times_and_rejects_junk():
    assert parse_hhmm("08:30") == 8 * 60 + 30
    assert parse_hhmm("8:30") == 8 * 60 + 30
    assert parse_hhmm("00:00") == 0
    assert parse_hhmm("23:59") == 23 * 60 + 59
    for junk in ["", "  ", "+8:30", "08:30:00", "25:00", "08:60", "half eight"]:
        assert parse_hhmm(junk) is None


def test_format_hhmm_shows_time_past_midnight():
    # 24:30 makes the overflow visible; wrapping to 00:30 would hide it.
    assert format_hhmm(24 * 60 + 30) == "24:30"
    assert format_hhmm(None) == ""
