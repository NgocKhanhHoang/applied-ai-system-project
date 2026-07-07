# PawPal+ (Module 2 Project)

You are building **PawPal+**, a Streamlit app that helps a pet owner plan care tasks for their pet.

## Scenario

A busy pet owner needs help staying consistent with pet care. They want an assistant that can:

- Track pet care tasks (walks, feeding, meds, enrichment, grooming, etc.)
- Consider constraints (time available, priority, owner preferences)
- Produce a daily plan and explain why it chose that plan

Your job is to design the system first (UML), then implement the logic in Python, then connect it to the Streamlit UI.

## What you will build

Your final app should:

- Let a user enter basic owner + pet info
- Let a user add/edit tasks (duration + priority at minimum)
- Generate a daily schedule/plan based on constraints and priorities
- Display the plan clearly (and ideally explain the reasoning)
- Include tests for the most important scheduling behaviors

## Getting started

### Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Suggested workflow

1. Read the scenario carefully and identify requirements and edge cases.
2. Draft a UML diagram (classes, attributes, methods, relationships).
3. Convert UML into Python class stubs (no logic yet).
4. Implement scheduling logic in small increments.
5. Add tests to verify key behaviors.
6. Connect your logic to the Streamlit UI in `app.py`.
7. Refine UML so it matches what you actually built.

## 🖥️ Sample Output

```text
=== Today's Schedule (do these in order) ===
#  Pet        Priority  Task          Duration  Frequency  Status
-----------------------------------------------------------------
1  Ice Cream  High      Morning walk  60 min    daily      todo  
2  Ice Cream  Medium    Feed dinner   10 min    daily      todo  
3  Meo        Low       Brushing      15 min    daily      todo  

Total: 3 task(s), 85 min
Why: Scheduled 3 task(s) using 85/120 min, ordered by priority. 0 task(s) didn't fit.
```

## 🧪 Testing PawPal+

```bash
# Run the full test suite:
pytest

# Run with coverage:
pytest --cov
```

Sample test output:

```
# Paste your pytest output here
```

## 📐 Smarter Scheduling

All logic is in `pawpal_system.py`. `Scheduler.generate_plan()` ties it together:
it filters tasks, sorts them, puts them on a clock, and checks for conflicts.

**Sorting**
- `Scheduler.sort_tasks()` — by priority (High → Low), shorter task first on a tie.
- `Scheduler.sort_by_time()` — earliest time first (the timeline you see in the plan).

**Filtering**
- `Scheduler.filter_by_pet()` — show only one pet's tasks.
- `Scheduler.filter_by_status()` — done vs. to-do (the plan hides completed tasks).
- `Scheduler.filter_by_priority()` — any priority level (`filter_by_urgency()` = High only).
- `Scheduler.filter_due()` — keep only tasks due that day.

**Conflict detection**
- `Task.overlaps()` — true when two tasks' time windows overlap.
- `Scheduler.detect_conflicts()` — finds every overlapping pair in the plan.
- `Scheduler.describe_conflicts()` — prints a warning line for each conflict.

**Recurring tasks**
- `Frequency` enum — `DAILY` (every day) or `WEEKLY` (every 7 days).
- `Task.is_due(day_index)` — decides if a task runs on a given day.
- `Task.reset_for_new_day()` / `Owner.reset_day()` — reset tasks so they can be done again tomorrow.

## 📸 Demo Walkthrough

Describe your app in numbered steps so a reader can follow along without watching a video:

1. <!-- Describe this step -->
2. <!-- Describe this step -->
3. <!-- Describe this step -->
4. <!-- Describe this step -->
5. <!-- Add more steps as needed -->

**Screenshot or video** *(optional)*: <!-- Insert a screenshot or link to a demo video here -->
