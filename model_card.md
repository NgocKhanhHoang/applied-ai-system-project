# Model Card — PawPal+


## 1. Limitations and biases
a. The model's output is only checked where I had a clear right answer
- The system double-checks 8 hard rules in code (no fake tasks, no double-booking, no moved appointments, no going over budget).
But the AI also writes three things we can't check: care tips, its explanation for the plan, and its reason for skipping a task.
A skipped task can even show up with a blank reason — even though that's the one thing an owner most wants explained.

b. Warnings can be approved, and repairs can quietly make things worse
- Errors reject a plan and warnings only inform. That split is the design decision I'd defend hardest, but it means a plan carrying.
- When a plan goes over budget, the system's easiest fix is to drop the single longest task, often the most important one (like a walk), and the revised plan then passes with just a warning.

### Biases
- Task timing rules assume a typical daytime schedule (morning/evening walks, meals at "normal" times). This doesn't fit night-shift owners, different climates, or different routines.
- English only. For prompts, output, and the app itself.
- Better with dogs and cats than less common pets (rabbits, reptiles, birds).
- If the owner mislabels a task, that mistake carries through.
- The basic scheduling logic favors short tasks and front-loads the day starting at 8am, rather than spreading tasks realistically.

---

## 2. Could this be misused, and how would I prevent that?

### Risk: Being read as veterinary advice
- If the app schedules "Give medicine" at a certain time, an owner might think that time is medically correct, but it isn't. The app has no idea what the medicine is.
- **What I already prevent:** the app never invents or changes medicine times, those come from the owner.
- **What I'd add:** a clear disclaimer on health-related tasks, and either verify or remove the "tips" feature, since there's no way to check if tips are accurate.

### Risk: Skipping a health task with one click
- A busy day could result in "Give medicine" being dropped, with only a single warning shown alongside other minor warnings.
- **What I'd add:** a stronger alert type specifically for health-related tasks (medicine, vet, injection, etc.) that requires the owner to actively confirm before approving

### Risk: users trying to talk the AI out of its rules
- Users could type things like "ignore the time budget" to manipulate the plan.
- **What I already prevent:** even if the AI is influenced, the final plan is still checked against hard rules in code — so a manipulated plan gets caught and fixed.
**Remaining risk:** the tips and explanation text aren't checked, so that's still an opening for bad influence.
---

## 3. What surprised me while testing reliability
- Bad plans often look reasonable. One plan scheduled a walk right before medicine time to avoid heat — sensible reasoning, but it caused a scheduling conflict. Only checking the actual numbers caught it.

- Sometimes the AI was right and our rule was wrong. In one case, dropping a long walk to fit two smaller tasks (including medicine) was actually the better call — so we changed that rule from a hard error to a warning the owner decides on.
---

## 4. Collaboration with AI

Planning the design — describing the app idea and asking how to structure it into parts. This shaped the core structure of the system.
Debugging — showing the AI the actual output vs. the expected output and asking why they differed (more effective than just asking for a fix).
Cleanup — a final pass to improve naming and consistency.

Key takeaway: specific prompts with real context worked far better than vague ones. "Here's my code, here's the wrong result, why?" solved real bugs. "Build me a scheduler" produced code that looked fine but wasn't well understood.

### A helpful suggestion I accepted
Suggestion: build the AI connection as a swappable component, so tests can use a fake version instead of the real AI service.

Why it helped: this let me test how the system handles bad AI responses (fake task IDs, conflicts, broken data) instantly, without needing real API calls. More than half of all tests exist because of this one decision.


### A flawed suggestion I rejected
- Suggestion: store task priority as text ("high", "medium", "low").
- The problem: sorting text alphabetically puts them in the wrong order — "high" < "low" < "medium" — so low priority tasks would rank above medium ones. The code would run with no errors, but produce wrong schedules silently.
- What I did instead: stored priority as ranked numbers (High = 1, Medium = 2, Low = 3), so sorting is always correct, and the readable label is generated from that.
- How I caught it: I manually worked out what the sort order would actually look like before trusting it, then confirmed it by running the code and checking the real output.