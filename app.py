import os
from datetime import time as clock

import streamlit as st
from pawpal_system import Pet, Owner, Task, Scheduler, Priority
from pawpal_agent import (
    DEFAULT_MODEL,
    AgentError,
    AgentUnavailable,
    GeminiClient,
    PlannerAgent,
)

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")

st.title("🐾 PawPal+")


def to_minutes(picked: clock | None) -> int | None:
    """Turn a time picker's value into minutes since midnight (None if empty)."""
    if picked is None:
        return None
    return picked.hour * 60 + picked.minute


def render_schedule(scheduler: Scheduler) -> None:
    """Show a finished plan: the timeline, then whatever didn't make it.

    Both planners end in a Scheduler, so an AI plan and a rule-based one look
    the same to the owner.
    """
    st.markdown(f"**Why:** {scheduler.reasoning}")
    if scheduler.tasks:
        st.table(
            [
                {
                    "#": i,
                    "Time": t.time_label(),
                    "Pet": t.pet_name or "Unassigned",
                    "Priority": t.priority.name.title(),
                    "Task": t.description,
                    "Duration (min)": t.duration,
                    "Status": "done" if t.completed else "todo",
                }
                for i, t in enumerate(scheduler.tasks, start=1)
            ]
        )
        st.caption(
            f"Total: {scheduler.task_count()} task(s), {scheduler.total_duration()} min"
        )
    else:
        st.warning("No tasks fit the schedule. Add tasks or increase available minutes.")

    # Overlapping time windows (e.g. a pinned appointment colliding with an
    # auto-placed task) so the owner can resolve them.
    if scheduler.conflicts:
        st.error("⚠️ Scheduling conflicts detected:")
        for line in scheduler.describe_conflicts():
            st.write(f"- {line}")

    # Tasks that couldn't fit the time budget, so nothing silently disappears.
    if scheduler.skipped_tasks:
        st.info("These tasks didn't fit today's time budget:")
        for t in scheduler.skipped_tasks:
            st.write(f"- {t.description} ({t.duration} min, {t.priority.name.title()})")

    # Tasks the owner had time for, but the day had no free gap big enough.
    if scheduler.unplaced_tasks:
        st.info("No free time slot for these — try a longer day or fewer appointments:")
        for t in scheduler.unplaced_tasks:
            st.write(f"- {t.description} ({t.duration} min)")

    # Appointments pinned outside the planning window.
    if scheduler.warnings:
        st.warning("Check these appointments:")
        for line in scheduler.warnings:
            st.write(f"- {line}")


st.divider()

# Map the friendly dropdown labels to the Priority enum from the backend.
PRIORITY_BY_LABEL = {"high": Priority.HIGH, "medium": Priority.MEDIUM, "low": Priority.LOW}

# The Owner is our persistent "vault" object: it holds every pet and, through
# each pet, every task. Create it once, then reuse it across reruns.
if "owner" not in st.session_state:
    st.session_state.owner = Owner()
owner = st.session_state.owner

st.subheader("Owner")
owner.name = st.text_input("Owner name", value=owner.name or "Jordan")
owner.available_minutes = st.number_input(
    "Minutes available today", min_value=0, max_value=1440, value=owner.available_minutes or 60
)

# The planning window: nothing gets placed outside these two times.
wcol1, wcol2 = st.columns(2)
with wcol1:
    day_start = to_minutes(st.time_input("Day starts", value=clock(8, 0), step=1800))
with wcol2:
    day_end = to_minutes(st.time_input("Day ends", value=clock(21, 0), step=1800))

if day_start >= day_end:
    st.error("Your day has to end after it starts. Using 08:00-21:00 for now.")
    day_start, day_end = 8 * 60, 21 * 60

st.divider()

st.subheader("Add a Pet")
with st.form("add_pet_form", clear_on_submit=True):
    pet_name = st.text_input("Pet name", value="Mochi")
    species = st.selectbox("Species", ["dog", "cat", "other"])
    food = st.text_input("Food", value="kibble")
    if st.form_submit_button("Add pet"):
        try:
            owner.add_pet(Pet(name=pet_name, species=species, food=food))
            st.success(f"Added {pet_name} the {species}.")
        except ValueError as error:
            st.error(str(error))

if owner.pets:
    st.write("Current pets:")
    for pet in owner.pets:
        info, remove = st.columns([6, 1])
        info.write(f"- {pet.pet_info()}")
        if remove.button("Remove", key=f"del-pet-{pet.name}"):
            owner.pets = [p for p in owner.pets if p is not pet]
            st.rerun()
else:
    st.info("No pets yet. Add one above.")

st.divider()

st.subheader("Add a Task")
if not owner.pets:
    st.caption("Add a pet first — tasks belong to a pet.")
else:
    with st.form("add_task_form", clear_on_submit=True):
        # Let the user choose which pet this task is for, by name.
        pet_names = [pet.name for pet in owner.pets]
        chosen_pet_name = st.selectbox("For which pet?", pet_names)

        col1, col2, col3 = st.columns(3)
        with col1:
            task_title = st.text_input("Task title", value="Morning walk")
        with col2:
            duration = st.number_input("Duration (minutes)", min_value=1, max_value=240, value=20)
        with col3:
            priority_label = st.selectbox("Priority", ["low", "medium", "high"], index=2)

        location = st.text_input("Location (optional)", value="")
        # A time picker rather than a typed HH:MM box: pick or type, and an empty
        # box means "no set time", which is what start_time=None means downstream.
        preferred = st.time_input(
            "Prefer time (optional)",
            value=None,
            step=300,
            help="Pick or type a time to lock this task to it, e.g. 2:00 PM. "
                 "Leave it empty and PawPal+ finds a free slot for you.",
        )

        if st.form_submit_button("Add task"):
            # Find the Pet object the user picked, then let it own the new Task.
            pet = next(p for p in owner.pets if p.name == chosen_pet_name)
            try:
                pet.add_task(
                    Task(
                        description=task_title,
                        duration=int(duration),
                        priority=PRIORITY_BY_LABEL[priority_label],
                        location=location,
                        start_time=to_minutes(preferred),
                    )
                )
                st.success(f"Added '{task_title}' for {chosen_pet_name}.")
            except ValueError as error:
                st.error(str(error))

# Show every task across all pets (Owner.all_tasks flattens them for us).
all_tasks = owner.all_tasks()
if all_tasks:
    st.write("Current tasks:")

    # Filter + sort controls. All of the logic lives in Scheduler so the UI just
    # calls it (single source of truth) — the table below is a direct view of what
    # the algorithmic layer produces.
    sched = Scheduler()
    fcol1, fcol2, fcol3 = st.columns([2, 2, 1])
    with fcol1:
        pet_filter = st.selectbox("Filter by pet", ["All pets"] + [p.name for p in owner.pets])
    with fcol2:
        priority_filter = st.selectbox(
            "Filter by priority", ["all", "urgent (high only)", "high", "medium", "low"]
        )
    with fcol3:
        hide_done = st.checkbox("Hide completed", value=False)

    sort_mode = st.radio(
        "Sort by",
        ["As entered", "Priority (sort_tasks)", "Time (sort_by_time)"],
        horizontal=True,
    )

    # Filtering — each branch delegates to a Scheduler method.
    shown = all_tasks
    if pet_filter != "All pets":
        shown = sched.filter_by_pet(shown, pet_filter)
    if priority_filter == "urgent (high only)":
        shown = sched.filter_by_urgency(shown)
    elif priority_filter in PRIORITY_BY_LABEL:
        shown = sched.filter_by_priority(shown, PRIORITY_BY_LABEL[priority_filter])
    if hide_done:
        shown = sched.filter_by_status(shown, completed=False)

    # Sorting — reuse the same orderings the scheduler applies internally.
    if sort_mode.startswith("Priority"):
        shown = sched.sort_tasks(shown)
    elif sort_mode.startswith("Time"):
        shown = sched.sort_by_time(shown)

    if shown:
        pending = sched.filter_by_status(shown, completed=False)
        st.success(
            f"Showing {len(shown)} task(s) — {len(pending)} to do, "
            f"{len(shown) - len(pending)} done."
        )
        # One row per task, so the owner can tick it off or delete it. id(task) is
        # a unique widget key that survives filtering and sorting.
        for task in shown:
            label, tick, remove = st.columns([7, 1, 1])
            label.write(
                f"**{task.description}** — {task.pet_name}, {task.duration} min, "
                f"{task.priority.name.title()}"
                + (f", {task.location}" if task.location else "")
            )
            task.completed = tick.checkbox(
                "Done", value=task.completed, key=f"done-{id(task)}"
            )
            if remove.button("🗑", key=f"del-task-{id(task)}"):
                pet = next(p for p in owner.pets if p.name == task.pet_name)
                pet.tasks = [t for t in pet.tasks if t is not task]
                st.rerun()
    else:
        st.warning("No tasks match the current filters.")
else:
    st.info("No tasks yet.")

st.divider()

# ---------------------------------------------------------------------------
# The agentic planner: suggest -> auto-check -> your review -> final plan
# ---------------------------------------------------------------------------

st.subheader("✨ Let the AI plan your day")
st.caption(
    "Gemini proposes a timed plan, an automatic checker holds it to your day "
    "window, your minutes and your pinned times, and nothing touches your "
    "tasks until you approve it."
)

# The proposal being reviewed, and the plan once approved. Both live in session
# state so they survive Streamlit's rerun on every click.
st.session_state.setdefault("agent_run", None)
st.session_state.setdefault("approved_plan", None)

env_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""

with st.expander("Gemini settings", expanded=not env_key):
    api_key = st.text_input(
        "Gemini API key",
        value=env_key,
        type="password",
        help="Get one from Google AI Studio. Set GEMINI_API_KEY to skip this box.",
    )
    model_name = st.selectbox(
        "Model", [DEFAULT_MODEL, "gemini-2.5-pro", "gemini-2.0-flash"]
    )
    max_attempts = st.slider(
        "Tries before giving up", min_value=1, max_value=5, value=3,
        help="Each rejected plan is sent back with the checker's exact objections.",
    )

preferences = st.text_area(
    "Anything the planner should know? (optional)",
    placeholder="Rex hates the midday heat. I'm out of the house 09:00-12:00.",
)


def build_agent() -> PlannerAgent:
    """Wire a planner to Gemini using the settings above."""
    return PlannerAgent(
        client=GeminiClient(api_key=api_key, model=model_name),
        day_start=day_start,
        day_end=day_end,
        max_attempts=int(max_attempts),
    )


if st.button("✨ Suggest a schedule", disabled=not owner.all_tasks()):
    try:
        agent = build_agent()
        with st.spinner("Planning the day, then checking the plan…"):
            st.session_state.agent_run = agent.suggest(
                owner, preferences=preferences
            )
        st.session_state.approved_plan = None
    except AgentUnavailable as error:
        st.error(f"{error}")
    except AgentError as error:
        st.error(f"Couldn't reach the planner: {error}")

if not owner.all_tasks():
    st.caption("Add a pet and a task first — the agent plans what you already have.")

run = st.session_state.agent_run
if run is not None:
    # Show the work: every call, and what the checker said about it.
    if run.attempts:
        label = f"How it got here — {len(run.attempts)} model call(s)"
        with st.expander(label):
            for attempt in run.attempts:
                head = f"**Call {attempt.number}** ({attempt.kind})"
                if attempt.error:
                    st.write(f"{head} — couldn't be used: {attempt.error}")
                    continue
                rejections = [
                    v for v in attempt.violations if v.severity == "error"
                ]
                if rejections:
                    st.write(f"{head} — rejected by the checker:")
                    for violation in rejections:
                        st.write(f"  - `{violation.code}` {violation.message}")
                else:
                    st.write(f"{head} — passed every check ✅")

    if run.used_fallback:
        st.error(
            "The AI couldn't produce a plan that passed the checks, so here's "
            "the rule-based plan instead — your day is still covered."
        )
        render_schedule(run.fallback)

    elif run.ok and run.plan is not None:
        st.markdown(f"**The plan:** {run.plan.reasoning}")

        rows = run.rows()
        if rows:
            st.table(rows)
            total = sum(row["Duration (min)"] for row in rows)
            st.caption(f"Total: {len(rows)} task(s), {total} min")

        skipped = run.skipped_rows()
        if skipped:
            st.info("Left out of today:")
            st.table(skipped)

        for violation in run.warnings():
            st.warning(violation.message)

        if run.plan.tips:
            st.markdown("**Tips from the planner**")
            for tip in run.plan.tips:
                st.write(f"- {tip}")

        # Human review. This is the only path from a suggestion to a real plan.
        st.markdown("**Your call** — nothing is saved to your tasks until you approve.")
        if st.button("✅ Approve this plan"):
            try:
                st.session_state.approved_plan = run.approve()
                st.session_state.agent_run = None
                st.rerun()
            except AgentError as error:
                st.error(str(error))

        feedback = st.text_input(
            "Or tell the planner what to change",
            placeholder="Walk Rex in the evening, and put the vet visit last.",
        )
        if st.button("🔁 Ask for changes", disabled=not feedback.strip()):
            try:
                agent = build_agent()
                with st.spinner("Revising the plan…"):
                    st.session_state.agent_run = agent.revise(
                        owner, run, feedback=feedback
                    )
                st.rerun()
            except AgentError as error:
                st.error(f"Couldn't reach the planner: {error}")

if st.session_state.approved_plan is not None:
    st.success("Approved — this is your day.")
    render_schedule(st.session_state.approved_plan)
