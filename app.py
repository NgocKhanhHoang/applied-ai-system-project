import streamlit as st
from pawpal_system import Pet, Owner, Task, Scheduler, Priority, Frequency, parse_hhmm

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")

st.title("🐾 PawPal+")

st.markdown(
    """
Welcome to the PawPal+ starter app.

This file is intentionally thin. It gives you a working Streamlit app so you can start quickly,
but **it does not implement the project logic**. Your job is to design the system and build it.

Use this app as your interactive demo once your backend classes/functions exist.
"""
)

with st.expander("Scenario", expanded=True):
    st.markdown(
        """
**PawPal+** is a pet care planning assistant. It helps a pet owner plan care tasks
for their pet(s) based on constraints like time, priority, and preferences.

You will design and implement the scheduling logic and connect it to this Streamlit UI.
"""
    )

with st.expander("What you need to build", expanded=True):
    st.markdown(
        """
At minimum, your system should:
- Represent pet care tasks (what needs to happen, how long it takes, priority)
- Represent the pet and the owner (basic info and preferences)
- Build a plan/schedule for a day that chooses and orders tasks based on constraints
- Explain the plan (why each task was chosen and when it happens)
"""
    )

st.divider()

# Map the friendly dropdown labels to the Priority enum from the backend.
PRIORITY_BY_LABEL = {"high": Priority.HIGH, "medium": Priority.MEDIUM, "low": Priority.LOW}
FREQUENCY_BY_LABEL = {"daily": Frequency.DAILY, "weekly": Frequency.WEEKLY}

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

st.divider()

st.subheader("Add a Pet")
with st.form("add_pet_form", clear_on_submit=True):
    pet_name = st.text_input("Pet name", value="Mochi")
    species = st.selectbox("Species", ["dog", "cat", "other"])
    food = st.text_input("Food", value="kibble")
    if st.form_submit_button("Add pet"):
        owner.add_pet(Pet(name=pet_name, species=species, food=food))
        st.success(f"Added {pet_name} the {species}.")

if owner.pets:
    st.write("Current pets:")
    for pet in owner.pets:
        st.write(f"- {pet.pet_info()}")
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
        start_str = st.text_input(
            "Preferred start (HH:MM, optional)",
            value="",
            help="Pin a fixed time like 14:00. Leave blank to let the scheduler place it.",
        )
        frequency_label = st.selectbox("Repeats", ["daily", "weekly"])

        if st.form_submit_button("Add task"):
            start_time = parse_hhmm(start_str)
            if start_str.strip() and start_time is None:
                st.error("Couldn't read the start time. Use HH:MM, e.g. 14:00.")
            else:
                # Find the Pet object the user picked, then let it own the new Task.
                pet = next(p for p in owner.pets if p.name == chosen_pet_name)
                pet.add_task(
                    Task(
                        description=task_title,
                        duration=int(duration),
                        priority=PRIORITY_BY_LABEL[priority_label],
                        location=location,
                        start_time=start_time,
                        frequency=FREQUENCY_BY_LABEL[frequency_label],
                    )
                )
                st.success(f"Added '{task_title}' for {chosen_pet_name}.")

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
        st.table(
            [
                {
                    "Pet": t.pet_name,
                    "Task": t.description,
                    "Duration (min)": t.duration,
                    "Priority": t.priority.name.title(),
                    "Location": t.location,
                    "Status": "✅ done" if t.completed else "⏳ todo",
                }
                for t in shown
            ]
        )
    else:
        st.warning("No tasks match the current filters.")
else:
    st.info("No tasks yet.")

st.divider()

st.subheader("Build Schedule")
st.caption("Runs your Scheduler over the owner's pets and time budget.")

if st.button("Generate schedule"):
    scheduler = Scheduler().generate_plan(owner)
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
                    "Frequency": t.frequency.name.title(),
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

    # Flag overlapping time windows (e.g. a pinned appointment colliding with
    # an auto-placed task) so the owner can resolve them.
    if scheduler.conflicts:
        st.error("⚠️ Scheduling conflicts detected:")
        for line in scheduler.describe_conflicts():
            st.write(f"- {line}")

    # Tasks that couldn't fit the time budget, so nothing silently disappears.
    if scheduler.skipped_tasks:
        st.info("These tasks didn't fit today's time budget:")
        for t in scheduler.skipped_tasks:
            st.write(f"- {t.description} ({t.duration} min, {t.priority.name.title()})")
