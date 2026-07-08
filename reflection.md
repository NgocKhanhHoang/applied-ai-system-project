# PawPal+ Project Reflection

## 1. System Design

**a. Initial design**
In the app, user can add a pet (name, origin), add daily tasks (duration + priority at minimum), generate a daily plan/ schedule based on the daily task (schedule a walk, feeding, enrichment, grooming with time availability, priority, owner preferences and reasoning for it).  

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
I used AI mainly for 3 things: design brainstorming, debugging, and refactoring.
1. Design brainstorming: Early on I described the app in plain English and asked how it would recommend splitting it into classes. This helped me land on the 4-class structure plus the Priority enum, and it pushed me to keep scheduling logic in Owner/ Scheduler instead of piling it into Pet. 
2. Debugging: When my sorting gave the wrong order, I pasted the actual output alongside what I expected and asked why it differed, rather than just asking for a fix. That's how I traced the bug back to sorting priorities as strings. 
3. Refactoring: I asked AI to review method names and return types for readability once the logic worked. 

The most helpful prompts were specific and included context. "Here's my code, here's the wrong result, why?" got far better answers than "make a scheduler."

**b. Judgment and verification**

I did not accept the AI suggestion for the Priority value. The initial approach used string values ("high", "medium", "low"). I rejected that because I realized that string sorting is alphabetical, which is wrong for my scheduler. I switched Priority to integers so sorting by urgency works for free without a separate ranking table. 

I verified the AI suggestions by tracing the logic myself and testing against expected output rather than trusting the code looked right. For the priority bug, I reasoned through what alphabetical ordering would actually produce, then confirmed it by running the scheduler and checking the printed plan order. 

---

## 4. Testing and Verification

**a. What you tested**

I picked 5 behaviors that would quietly ruin the schedule if they were wrong: 
1. The basic changes: making a task done actually changes its status, and adding a task to a pet makes its task list longer. 
2. Sorting: tasks come out in the right order. The timeline is sorted by time, and the plan is sorted by priority first then by duration. I also checked that two tasks with the same priority and duration always sorted the same way, so the plan never randomly changes. 
3. Recurrence: a daily task disappears once it's done today, then comes back the next day after I reset. A weekly task shows up on day 0 and day 7, but not on the days in between. 
4. Conflicts: 2 tasks set at the same time get flagged, but 2 tasks back-to-back do not get flagged. The second case is the tricky one, so I wanted a test to prove I got the boundary right.
5. Time budget: a task that exactly fills the available time still gets included, and a task that's too big gets skipped without blocking a smaller task that still fits. 

These tests mattered because they lock in the exact rules I decided on. If I change the code later and accidentally break one of these, the test fails right away instead of the app just handing back a wrong schedule.

**b. Confidence**

I'm fairly confident the scheduler works for the cases it's meant to handle. The main steps all pass their tests, and I tested the tricky boundary cases on purpose, not just the easy ones.

However, I'm not sure about the cases that I didn't test yet. With more time, I'd check:
1. A task that gets pushed so late it runs past midnight, since I don't have an end-of-day cutoff.
2. A fixed appointment (like a vet visit) that gets skipped just because earlier tasks used up all the time.
3. Longer stretches of days (day 14, 21, and so on) and a task added in the middle of the week.

---

## 5. Reflection

**a. What went well**
I'm happiest with how the scheduling logic broke down into small, simple methods that fit together. Getting the conflict check to tell the difference between a real overlap and two harmless back-to-back tasks was the moment it started to feel like a real planner.

**b. What you would improve**
If I did another version, I'd have the app actually fix conflicts instead of just pointing them out. Right now it flags an overlap and leaves the owner to sort it out. I'd also add a real end-of-day time so the schedule can't run past bedtime.

**c. Key takeaway**
The biggest thing I learned is that small choices like naming and data types are real design decisions, not just details. Switching priority from words to numbers made sorting work automatically, and renaming is_urgent() to priority_label() kept the name honest about what the method really does.  The most useful habit was asking why something worked and then proving it with a test, so I actually understood the code instead of just trusting it.
