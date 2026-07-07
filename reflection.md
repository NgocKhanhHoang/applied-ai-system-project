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

- What constraints does your scheduler consider (for example: time, priority, preferences)?
- How did you decide which constraints mattered most?

**b. Tradeoffs**

- Describe one tradeoff your scheduler makes.
- Why is that tradeoff reasonable for this scenario?

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
