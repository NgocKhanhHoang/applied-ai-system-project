# PawPal+

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

Run the tests from the project root:

```bash
python -m pytest
```

**What the tests cover:**

- **Sorting** — tasks come back in chronological (earliest-first) order.
- **Recurrence** — a daily task marked done comes back to-do the next day.
- **Conflicts** — tasks at the same time are flagged as a conflict.
- Plus edge cases: budget limits, tie-breaks, and back-to-back tasks.

**Successful run:**

```
============================= test session starts =============================
platform win32 -- Python 3.14.5, pytest-9.1.1, pluggy-1.6.0
collected 12 items

tests\test_pawpal.py ............                                        [100%]

============================= 12 passed in 0.18s ==============================
```

**Confidence Level: ★★★★☆ (4/5)** — All 12 tests pass and cover the core scheduling logic. One star held back because the Streamlit UI (`app.py`) isn't tested yet.

## 📐 System Design (UML)

![PawPal+ UML class diagram](diagrams/uml.png)

The class diagram above reflects the final implementation in `pawpal_system.py`.
Source: [`diagrams/uml.mmd`](diagrams/uml.mmd).

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

## ✨ Features

**Planning**
- Builds a daily plan that fits your available minutes, most important tasks first.
- Handles fixed-time tasks (e.g. 12:00) and fills flexible ones around them.
- Explains each plan and lists anything that didn't fit the time budget.

**Organizing**
- Filter tasks by pet, priority, or done/to-do.
- Sort by priority or by time.

**Staying on track**
- Warns when two tasks are booked at the same time.
- Repeats tasks daily or weekly, resetting them each new day.

**Interactive UI (Streamlit)**
- Add owners, pets, and tasks through forms, then generate the day's plan with one click.

## 📸 Demo Walkthrough

### What you can do in the app

Run it with `streamlit run app.py`. The page has four simple parts:

1. **Owner** — enter your name and how many minutes you have today.
2. **Add a Pet** — add a pet (name, species, food).
3. **Add a Task** — pick a pet, then set the task, how long it takes, and its priority. Optionally pin a time (like `12:00`) or make it repeat daily/weekly.
4. **Build Schedule** — one click turns your tasks into a timed plan for the day.

You can also **filter** the task list (by pet, by priority, or hide finished tasks) and **sort** it (by priority or by time).

### Try it in 5 steps

1. Set the owner to **Jordan** with **200** minutes.
2. Add a dog named **Ice Cream**.
3. Add three tasks: **Morning walk** (60 min, High), **Feed dinner** (10 min, Medium), and **Give medicine** pinned to **12:00** (10 min, High).
4. In **Current tasks**, set *Sort by → Priority* and watch High tasks jump to the top.
5. Click **Generate schedule** to see the timed plan.

### What to notice

- **Sorting** — important tasks come first; the final plan reads top to bottom by clock time.
- **Fixed times** — the 12:00 task keeps its slot; everything else fills in around it.
- **Conflict warnings** — two tasks at the same time get a ⚠️ warning (and a note if they're for the same pet).
- **Time budget** — anything that doesn't fit your minutes is listed as "didn't fit."

### Sample output (no UI needed)

Run the demo script to see the same logic in the terminal:

```bash
python main.py
```

```text
=== Sorted by priority (sort_tasks) ===
  - [Priority: High] Give medicine (10 min, Daily) - todo
  - [Priority: High] Clean litter (15 min, Daily) - todo
  - [Priority: High] Morning walk (60 min, Daily) - todo
  - [Priority: Medium] Feed dinner (10 min, Daily) - todo
  - [Priority: Low] Brushing (15 min, Daily) - todo

=== Today's Schedule (do these in order) ===
#  Time         Pet        Priority  Task           Duration  Frequency  Status
-------------------------------------------------------------------------------
1  12:00-12:20  Meo        Medium    Feed lunch     20 min    Daily      todo
2  12:00-12:10  Ice Cream  High      Give medicine  10 min    Daily      todo
3  12:10-12:25  Meo        High      Clean litter   15 min    Daily      todo
4  12:25-13:25  Ice Cream  High      Morning walk   60 min    Daily      todo
   ... (3 more rows) ...

Total: 7 task(s), 150 min
Why: Scheduled 7 task(s) using 150/200 min, chosen by priority and laid out from 08:00. 0 didn't fit; 2 time conflict(s).

Conflicts:
  - 12:00-12:20 Feed lunch overlaps 12:00-12:10 Give medicine
  - 12:00-12:20 Feed lunch overlaps 12:10-12:25 Clean litter (same pet - can't be in two places!)
```
