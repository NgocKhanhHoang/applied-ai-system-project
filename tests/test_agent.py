"""Tests for the PawPal+ AI planner.

Every test uses ScriptedClient, so no API key and no network. What's tested is
the part we control: pre-filter, evaluator, repair loop, fallback, and approval.
"""

import json

import pytest

from pawpal_system import Owner, Pet, Priority, Scheduler, Task
from pawpal_agent import (
    AgentError,
    Evaluator,
    PlannerAgent,
    ScriptedClient,
    build_context,
    candidate_tasks,
    parse_plan,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_owner(minutes: int = 120) -> Owner:
    """An owner with one dog: a flexible walk, a flexible feed, a pinned vet."""
    rex = Pet(name="Rex", species="dog", food="kibble")
    rex.add_task(Task("Morning walk", 30, Priority.HIGH))
    rex.add_task(Task("Feed dinner", 15, Priority.MEDIUM))
    rex.add_task(Task("Vet visit", 30, Priority.LOW, start_time=14 * 60))
    return Owner(name="Sam", pets=[rex], available_minutes=minutes)


def reply(schedule, skipped=(), reasoning="A calm day.", tips=()) -> str:
    """Build a model reply the way Gemini would return it."""
    return json.dumps({
        "schedule": [
            {"id": task_id, "start": start, "why": "because"}
            for task_id, start in schedule
        ],
        "skipped": [{"id": task_id, "why": "no time"} for task_id in skipped],
        "reasoning": reasoning,
        "tips": list(tips),
    })


GOOD_PLAN = reply(
    schedule=[("t1", "08:00"), ("t2", "08:30"), ("t3", "14:00")],
)


# ---------------------------------------------------------------------------
# B: what the agent is allowed to see
# ---------------------------------------------------------------------------

def test_candidates_exclude_done_and_not_due_tasks():
    # Arrange: one finished task and one weekly task that isn't due tomorrow.
    owner = make_owner()
    pet = owner.pets[0]
    pet.tasks[0].mark_complete()

    # Act: build the candidate list for day 1.
    candidates = candidate_tasks(owner, day_index=1)

    # Assert: recurrence and completion are settled before the model is asked.
    assert "Morning walk" not in [t.description for t in candidates.values()]
    assert len(candidates) == 2


def test_context_reports_the_real_budget_and_fixed_times():
    # Arrange: 120 minutes, 30 of them already spent on a completed task.
    owner = make_owner()
    owner.pets[0].tasks[1].mark_complete()   # Feed dinner, 15 min
    candidates = candidate_tasks(owner)

    # Act: serialize what the model will see.
    context = build_context(owner, candidates)

    # Assert: the budget is the remaining time, and the vet keeps its pin.
    assert context["available_minutes"] == 105
    vet = next(t for t in context["candidate_tasks"] if t["description"] == "Vet visit")
    assert vet["fixed_start"] == "14:00"


# ---------------------------------------------------------------------------
# Parsing the model's reply
# ---------------------------------------------------------------------------

def test_parse_plan_reads_times_and_reasons():
    plan = parse_plan(GOOD_PLAN)
    assert plan.scheduled_ids() == ["t1", "t2", "t3"]
    assert plan.slots[0].start == 8 * 60
    assert plan.reasoning == "A calm day."


def test_parse_plan_forgives_a_markdown_fence():
    # Models sometimes wrap JSON in a fence; that's the one slip worth forgiving.
    plan = parse_plan(f"```json\n{GOOD_PLAN}\n```")
    assert plan.scheduled_ids() == ["t1", "t2", "t3"]


def test_parse_plan_rejects_prose():
    with pytest.raises(Exception):
        parse_plan("Sure! Here's a lovely plan for Rex.")


# ---------------------------------------------------------------------------
# D: the evaluator catches what a model gets wrong
# ---------------------------------------------------------------------------

def evaluate(owner, model_reply):
    """Run the evaluator over one reply and return (violations, candidates)."""
    candidates = candidate_tasks(owner)
    evaluator = Evaluator(
        day_start=8 * 60,
        day_end=21 * 60,
        available_minutes=owner.remaining_minutes(),
    )
    return evaluator.check(parse_plan(model_reply), candidates), candidates


def codes(violations, severity="error"):
    return {v.code for v in violations if v.severity == severity}


def test_valid_plan_passes_with_no_errors():
    violations, _ = evaluate(make_owner(), GOOD_PLAN)
    assert Evaluator.errors(violations) == []


def test_overlapping_tasks_are_rejected():
    # Arrange: a 30-min walk at 08:00 and a feed at 08:15 - 15 minutes collide.
    bad = reply([("t1", "08:00"), ("t2", "08:15"), ("t3", "14:00")])

    violations, _ = evaluate(make_owner(), bad)

    assert "overlap" in codes(violations)


def test_back_to_back_tasks_are_allowed():
    # A task ending at 08:30 and one starting at 08:30 only touch.
    ok = reply([("t1", "08:00"), ("t2", "08:30"), ("t3", "14:00")])

    violations, _ = evaluate(make_owner(), ok)

    assert "overlap" not in codes(violations)


def test_moving_a_pinned_appointment_is_rejected():
    # The vet is pinned to 14:00; the model tried to slide it to 15:00.
    bad = reply([("t1", "08:00"), ("t2", "08:30"), ("t3", "15:00")])

    violations, _ = evaluate(make_owner(), bad)

    assert "moved_appointment" in codes(violations)


def test_invented_task_is_rejected():
    bad = reply([("t1", "08:00"), ("t2", "08:30"), ("t3", "14:00"), ("t99", "16:00")])

    violations, _ = evaluate(make_owner(), bad)

    assert "unknown_task" in codes(violations)


def test_silently_dropped_task_is_rejected():
    # t2 is neither scheduled nor listed as skipped - it just vanished.
    bad = reply([("t1", "08:00"), ("t3", "14:00")])

    violations, _ = evaluate(make_owner(), bad)

    assert "missing_task" in codes(violations)


def test_task_scheduled_twice_is_rejected():
    bad = reply([("t1", "08:00"), ("t1", "10:00"), ("t2", "09:00"), ("t3", "14:00")])

    violations, _ = evaluate(make_owner(), bad)

    assert "duplicate_task" in codes(violations)


def test_plan_over_the_time_budget_is_rejected():
    # Arrange: only 40 minutes available, but the plan books 75.
    owner = make_owner(minutes=40)
    bad = reply([("t1", "08:00"), ("t2", "08:30"), ("t3", "14:00")])

    violations, _ = evaluate(owner, bad)

    assert "over_budget" in codes(violations)


def test_flexible_task_outside_the_day_is_rejected():
    # 22:00 is past a 21:00 day end, and nothing pinned it there.
    bad = reply([("t1", "22:00"), ("t2", "08:30"), ("t3", "14:00")])

    violations, _ = evaluate(make_owner(), bad)

    assert "outside_day" in codes(violations)


def test_owner_pinned_appointment_outside_the_day_is_only_a_warning():
    # Arrange: the owner themselves pinned a vet visit at 22:00.
    rex = Pet(name="Rex", species="dog", food="kibble")
    rex.add_task(Task("Late vet", 30, Priority.HIGH, start_time=22 * 60))
    owner = Owner(name="Sam", pets=[rex], available_minutes=120)

    violations, _ = evaluate(owner, reply([("t1", "22:00")]))

    # Assert: the agent obeyed the pin, so it's flagged but not rejected.
    assert Evaluator.errors(violations) == []
    assert "appointment_outside_day" in codes(violations, severity="warning")


def test_unreadable_time_is_rejected():
    bad = reply([("t1", "eight in the morning"), ("t2", "08:30"), ("t3", "14:00")])

    violations, _ = evaluate(make_owner(), bad)

    assert "bad_time" in codes(violations)


def test_skipping_a_high_task_to_keep_a_lower_one_is_warned():
    # Arrange: the walk (High) is skipped while the feed (Medium) is kept.
    bad = reply([("t2", "08:00"), ("t3", "14:00")], skipped=["t1"])

    violations, _ = evaluate(make_owner(), bad)

    # Assert: a judgement call, not a rule break - warn, don't reject.
    assert Evaluator.errors(violations) == []
    assert "priority_inversion" in codes(violations, severity="warning")


def test_empty_plan_with_time_to_spare_is_rejected():
    bad = reply([], skipped=["t1", "t2", "t3"])

    violations, _ = evaluate(make_owner(), bad)

    assert "empty_plan" in codes(violations)


# ---------------------------------------------------------------------------
# C + D: the repair loop
# ---------------------------------------------------------------------------

def test_agent_returns_a_valid_plan_on_the_first_try():
    owner = make_owner()
    client = ScriptedClient([GOOD_PLAN])

    run = PlannerAgent(client=client).suggest(owner)

    assert run.ok
    assert len(run.attempts) == 1
    assert not run.used_fallback


def test_bad_plan_is_sent_back_and_repaired():
    # Arrange: the model overlaps two tasks, then fixes it when told.
    owner = make_owner()
    overlapping = reply([("t1", "08:00"), ("t2", "08:15"), ("t3", "14:00")])
    client = ScriptedClient([overlapping, GOOD_PLAN])

    # Act.
    run = PlannerAgent(client=client).suggest(owner)

    # Assert: two calls, first rejected, second accepted.
    assert len(run.attempts) == 2
    assert run.attempts[0].passed is False
    assert run.attempts[1].passed is True
    assert run.ok


def test_repair_prompt_names_the_actual_problem():
    # Arrange: the model invents a task, so the retry must say so.
    owner = make_owner()
    invented = reply([("t1", "08:00"), ("t2", "08:30"), ("t3", "14:00"), ("t9", "16:00")])
    client = ScriptedClient([invented, GOOD_PLAN])

    PlannerAgent(client=client).suggest(owner)

    # Assert: the second prompt carries the violation, not just "try again".
    second_user_prompt = client.calls[1][1]
    assert "unknown_task" in second_user_prompt
    assert "'t9'" in second_user_prompt


def test_agent_falls_back_to_the_rule_based_scheduler_after_max_attempts():
    # Arrange: a model that never stops overlapping tasks.
    owner = make_owner()
    overlapping = reply([("t1", "08:00"), ("t2", "08:15"), ("t3", "14:00")])
    client = ScriptedClient([overlapping] * 3)

    # Act.
    run = PlannerAgent(client=client, max_attempts=3).suggest(owner)

    # Assert: three tries, then a plan the owner can still use.
    assert len(run.attempts) == 3
    assert run.ok is False
    assert run.used_fallback
    assert run.fallback.task_count() > 0


def test_transport_failure_stops_retrying_and_falls_back():
    # Arrange: a dead client (no replies left) - a bad key or no network.
    owner = make_owner()

    run = PlannerAgent(client=ScriptedClient([])).suggest(owner)

    # Assert: one attempt, no pointless retries, still a usable plan.
    assert len(run.attempts) == 1
    assert run.used_fallback


def test_empty_day_never_calls_the_model():
    # Arrange: an owner with no tasks at all.
    owner = Owner(name="Sam", available_minutes=120)
    client = ScriptedClient([GOOD_PLAN])

    run = PlannerAgent(client=client).suggest(owner)

    # Assert: no call spent, and the run still reports cleanly.
    assert client.calls == []
    assert run.attempts == []
    assert run.rows() == []


# ---------------------------------------------------------------------------
# E -> F: human review
# ---------------------------------------------------------------------------

def test_suggestion_does_not_touch_tasks_until_approved():
    # Arrange: a valid suggestion the owner hasn't accepted yet.
    owner = make_owner()
    run = PlannerAgent(client=ScriptedClient([GOOD_PLAN])).suggest(owner)

    # Assert: previewing shows the plan but changes nothing on the tasks.
    assert len(run.rows()) == 3
    assert all(task.scheduled_start is None for task in owner.all_tasks())


def test_approving_writes_the_plan_onto_the_tasks():
    # Arrange: the same valid suggestion.
    owner = make_owner()
    run = PlannerAgent(client=ScriptedClient([GOOD_PLAN])).suggest(owner)

    # Act: the owner approves.
    scheduler = run.approve()

    # Assert: real times land on the tasks, in chronological order, conflict-free.
    walk = next(t for t in owner.all_tasks() if t.description == "Morning walk")
    assert walk.scheduled_start == 8 * 60
    assert [t.description for t in scheduler.tasks] == [
        "Morning walk", "Feed dinner", "Vet visit",
    ]
    assert scheduler.conflicts == []
    assert isinstance(scheduler, Scheduler)


def test_approving_clears_a_time_from_an_earlier_plan():
    # Arrange: a rule-based plan ran first and stamped every task.
    owner = make_owner()
    Scheduler().generate_plan(owner)
    feed = next(t for t in owner.all_tasks() if t.description == "Feed dinner")
    assert feed.scheduled_start is not None

    # Act: the agent's plan skips the feed, and the owner approves it.
    plan = reply([("t1", "08:00"), ("t3", "14:00")], skipped=["t2"])
    run = PlannerAgent(client=ScriptedClient([plan])).suggest(owner)
    run.approve()

    # Assert: no stale time left behind on the dropped task.
    assert feed.scheduled_start is None
    assert feed.time_label() == "anytime"


def test_a_rejected_plan_cannot_be_approved():
    # Arrange: the model never produces a valid plan.
    owner = make_owner()
    overlapping = reply([("t1", "08:00"), ("t2", "08:15"), ("t3", "14:00")])
    run = PlannerAgent(client=ScriptedClient([overlapping] * 3)).suggest(owner)

    # Act + Assert: approval is blocked, so a bad plan can't reach the owner's day.
    with pytest.raises(AgentError):
        run.approve()


def test_owner_feedback_is_sent_back_to_the_model():
    # Arrange: a plan the owner wants changed.
    owner = make_owner()
    agent = PlannerAgent(client=ScriptedClient([GOOD_PLAN]))
    run = agent.suggest(owner)

    # Act: the owner asks for a later walk, and the model obliges.
    later = reply([("t1", "17:00"), ("t2", "08:30"), ("t3", "14:00")])
    agent.client = ScriptedClient([later])
    revised = agent.revise(owner, run, feedback="Walk Rex after work, not at dawn.")

    # Assert: the request reached the model and the new plan holds up.
    assert "after work" in agent.client.calls[0][1]
    assert revised.ok
    walk_slot = next(s for s in revised.plan.slots if s.task_id == "t1")
    assert walk_slot.start == 17 * 60


def test_revision_still_has_to_pass_the_evaluator():
    # Arrange: the owner asks for something that would break a hard rule.
    owner = make_owner()
    agent = PlannerAgent(client=ScriptedClient([GOOD_PLAN]))
    run = agent.suggest(owner)

    # Act: the model caves and double-books, every time.
    stacked = reply([("t1", "14:00"), ("t2", "08:30"), ("t3", "14:00")])
    agent.client = ScriptedClient([stacked] * 3)
    revised = agent.revise(owner, run, feedback="Just put the walk at the vet time.")

    # Assert: politeness doesn't get past the checker.
    assert revised.ok is False
    assert revised.used_fallback
