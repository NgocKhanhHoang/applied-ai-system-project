# PawPal+ Project Reflection

## 1. System Design

**a. Initial design**
In the app, user can add a pet (name, origin), add daily tasks (duration + priority at minimum), generate a daily plan/ schedule based on the daily task (schedule a walk, feeding, enrichment, gromming with time availability, priority, owner preferences and reasoning for it).  

The system is made up of 4 classes and 1 enum:
1. Pet: responsible for storing pet info (name, species, food, tasks) 
   and determining what type of care the pet needs.
2. Task responsible for storing the details of a single care activity: description, duration, priority, location, frequency, completed status, and specific notes.
3. Owner: takes a pet, a list of tasks, and available time, then generates a plan by sorting and filtering tasks based  on priority and time constraints.
4. Scheduler: responsible for the generated daily plan: an ordered set of tasks with total duration and task count.
5. Priority (enum): helps the owner know the urgency of tasks by replacing plain numbers with readable labels (HIGH, MEDIUM, LOW).

**b. Design changes**

My design changed in these ways:

1. Priority: I changed values from strings to integers because with string values I can't sort directly. Alphabetically it would give high < low < medium, which is wrong. I'd have to build a separate ranking table just to sort. However, numbers give me that ranking for free.
2. priority_label(): I changed the return type from bool to str because the output is displayed to the owner in the daily plan. A human reading a schedule understands "Priority: High" immediately, but would have to question what True/False means. I also renamed it from is_urgent() to priority_label() because the is_ prefix implies a yes/no boolean, which no longer matches what it returns. The label is built from the Priority enum's own name so it stays in sync automatically.
---

## 2. Scheduling Logic and Tradeoffs

**a. Constraints and priorities**

My scheduler considers four constraints:
1. **Priority**: how important/urgent a task is (High, Medium, Low).
2. **Time budget**: the total minutes the owner has available that day. A task is only added if it still fits in the remaining time.
3. **Fixed appointment times**: a task can be pinned to a specific time (e.g. a vet visit at 14:00); the scheduler keeps that time instead of moving it.
4. **Recurrence and status**: tasks that are already completed, or not due that day (e.g. a weekly task on a non-scheduled day), are left out of the plan.

In this app, priority mattered the most. I sort tasks by priority first, and use duration only as a tie-breaker (shorter tasks first when the priority is equal). So if a high-priority task has a long duration, the scheduler still fits it before a shorter, lower-priority task. I made this choice because a pet owner cares most about getting the important, urgent tasks done and the quick, less-important ones can wait or be skipped if time runs out.


**b. Tradeoffs**

1. **Flat, priority-ordered list vs. grouping by pet.**:
Grouping by pet would show each pet's full checklist separately, but it hides the "what should I do first?" answer across all pets. I chose a single flat list ordered by priority (then displayed as a timeline) so the owner immediately knows what to do first, no matter which pet it's for.

2. **Detecting conflicts but not resolving them.**:
When flexible tasks (like walking or brushing) overlap a fixed task (like a vet appointment), the app only detects and flags the conflict, but it doesn't automatically fix it. The owner has to resolve it manually. This is reasonable because auto-rescheduling adds a lot of complexity, and the owner usually knows best how to shuffle their own day. Flagging the problem is enough to prevent a double-booking.

3. **No end-of-day boundary.**:
The scheduler limits tasks by total minutes available, but not by a wall-clock end time, so the timeline could technically run past bedtime. I accepted this because using one constraint (minutes) is simpler than tracking both a minute budget and a fixed daily window, and for a daily planner the minute budget already keeps the plan realistic.

4. **Only two recurrence options (daily and weekly).**:
I didn't add bi-weekly, monthly, or yearly frequencies. I kept it to daily and weekly so I could keep the recurrence logic simple and spend more time building the other features (sorting, filtering, and conflict detection). My design stores each frequency as a number of days, so adding more options later would be easy.

---

## 3. AI Collaboration

**a. How you used AI**

- How did you use AI tools during this project (for example: design brainstorming, debugging, refactoring)?
- What kinds of prompts or questions were most helpful?

**b. Judgment and verification**

- Describe one moment where you did not accept an AI suggestion as-is.
- How did you evaluate or verify what the AI suggested?

---

## 4. Testing and Verification

**a. What you tested**

- What behaviors did you test?
- Why were these tests important?

**b. Confidence**

- How confident are you that your scheduler works correctly?
- What edge cases would you test next if you had more time?

---

## 5. Reflection

**a. What went well**

- What part of this project are you most satisfied with?

**b. What you would improve**

- If you had another iteration, what would you improve or redesign?

**c. Key takeaway**

- What is one important thing you learned about designing systems or working with AI on this project?
