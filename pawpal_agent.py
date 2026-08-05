"""PawPal+ AI planner: Gemini suggests the day, code checks it, the owner approves.

Follows diagrams/architecture.mmd:

    candidate_tasks()  - B: pre-filter (unfinished + due today).
    PlannerAgent       - C: the model proposes a timed plan.
    Evaluator          - D: auto-checks it against the hard rules.
    PlannerAgent._loop - D fail -> C: send the objections back, retry.
    AgentRun.approve() - E/F: only now is the plan written onto the tasks.

Nothing here trusts the model, and a failed run falls back to Scheduler.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from pawpal_system import (
    Owner,
    Scheduler,
    Task,
    format_hhmm,
    parse_hhmm,
)

PROMPT_DIR = Path(__file__).parent / "prompts"

# Gemini's fast general model. Good enough for a one-day plan and cheap enough
# to re-run through the repair loop a few times.
DEFAULT_MODEL = "gemini-2.5-flash"

# The reply shape we require. Passed to the model as a response schema so the
# JSON comes back well-formed instead of being coaxed out of prose.
# Type names are uppercase because that's the form Gemini's schema dialect
# documents; lowercase JSON-Schema spellings are rejected by the SDK.
PLAN_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "schedule": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "id": {"type": "STRING"},
                    "start": {"type": "STRING"},
                    "why": {"type": "STRING"},
                },
                "required": ["id", "start", "why"],
            },
        },
        "skipped": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "id": {"type": "STRING"},
                    "why": {"type": "STRING"},
                },
                "required": ["id", "why"],
            },
        },
        "reasoning": {"type": "STRING"},
        "tips": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": ["schedule", "skipped", "reasoning"],
}


class AgentError(RuntimeError):
    """Base class for anything that goes wrong in the agentic layer."""


class AgentUnavailable(AgentError):
    """The model can't be reached at all (no SDK installed, no API key)."""


class AgentReplyError(AgentError):
    """The model replied, but not with a plan we can read."""


# ---------------------------------------------------------------------------
# The model client
# ---------------------------------------------------------------------------

class LLMClient(Protocol):
    """Anything that turns a prompt into a JSON reply, real or faked."""

    def complete(self, system: str, user: str, schema: dict) -> str:
        """Return the model's raw reply text."""
        ...


@dataclass
class GeminiClient:
    """Calls Gemini. Imports the SDK lazily so PawPal+ runs without it."""

    api_key: str
    model: str = DEFAULT_MODEL
    temperature: float = 0.2   # planning wants consistency, not creativity

    def __post_init__(self) -> None:
        if not self.api_key:
            raise AgentUnavailable(
                "No Gemini API key. Set GEMINI_API_KEY or paste a key in the app."
            )
        try:
            from google import genai
        except ImportError as error:   # pragma: no cover - depends on the env
            raise AgentUnavailable(
                "google-genai isn't installed. Run: pip install google-genai"
            ) from error
        self._client = genai.Client(api_key=self.api_key)

    def complete(self, system: str, user: str, schema: dict) -> str:
        """Ask Gemini for one JSON reply."""
        from google.genai import types

        try:
            reply = self._client.models.generate_content(
                model=self.model,
                contents=user,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    temperature=self.temperature,
                    response_mime_type="application/json",
                    response_schema=schema,
                ),
            )
        except Exception as error:   # network, quota, bad key, safety block...
            raise AgentError(f"Gemini call failed: {error}") from error
        return reply.text or ""


@dataclass
class ScriptedClient:
    """Test double: hands back canned replies in order, no network."""

    replies: list[str]
    calls: list[tuple[str, str]] = field(default_factory=list)

    def complete(self, system: str, user: str, schema: dict) -> str:
        self.calls.append((system, user))
        if not self.replies:
            raise AgentError("ScriptedClient ran out of replies.")
        return self.replies.pop(0)


def gemini_from_env(model: str = DEFAULT_MODEL) -> GeminiClient:
    """Build a GeminiClient from GEMINI_API_KEY (or GOOGLE_API_KEY)."""
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
    return GeminiClient(api_key=key, model=model)


# ---------------------------------------------------------------------------
# B: the data the agent is allowed to plan over
# ---------------------------------------------------------------------------

def candidate_tasks(owner: Owner, day_index: int = 0) -> dict[str, Task]:
    """Tasks the agent may plan (unfinished + due today), keyed "t1", "t2", ...

    Ids stay fixed for the whole run so the model, the checker and the owner
    all mean the same task.
    """
    scheduler = Scheduler()
    pending = scheduler.filter_by_status(scheduler.retrieve_tasks(owner), completed=False)
    due = scheduler.filter_due(pending, day_index)
    return {f"t{i}": task for i, task in enumerate(due, start=1)}


def build_context(
    owner: Owner,
    candidates: dict[str, Task],
    day_index: int = 0,
    day_start: int = 8 * 60,
    day_end: int = 21 * 60,
) -> dict:
    """Serialize the owner, pets and candidate tasks for the prompt."""
    return {
        "owner": owner.name or "the owner",
        "day_index": day_index,
        "day_start": format_hhmm(day_start),
        "day_end": format_hhmm(day_end),
        "available_minutes": owner.remaining_minutes(day_index),
        "pets": [
            {"name": pet.name, "species": pet.species, "food": pet.food}
            for pet in owner.pets
        ],
        "candidate_tasks": [
            {
                "id": task_id,
                "pet": task.pet_name or "unassigned",
                "description": task.description,
                "duration_minutes": task.duration,
                "priority": task.priority.name.title(),
                "repeats": task.frequency.name.title(),
                "fixed_start": format_hhmm(task.start_time) or None,
                "location": task.location or None,
                "note": task.specific_note or None,
            }
            for task_id, task in candidates.items()
        ],
    }


def _or_none(text: str) -> str:
    """Return trimmed text, or a placeholder so a prompt slot is never blank."""
    return text.strip() or "None given."


# ---------------------------------------------------------------------------
# The model's proposal
# ---------------------------------------------------------------------------

@dataclass
class ProposedSlot:
    """One line of the model's schedule: put task `task_id` at `start`."""

    task_id: str
    start: int | None      # minutes since midnight; None if unreadable
    why: str = ""
    raw_start: str = ""    # what the model actually wrote, for error messages


@dataclass
class AgentPlan:
    """A plan the model proposed. Not yet checked, not yet approved."""

    slots: list[ProposedSlot] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (task_id, why)
    reasoning: str = ""
    tips: list[str] = field(default_factory=list)
    raw: str = ""          # the raw reply, kept so the owner can inspect it

    def scheduled_ids(self) -> list[str]:
        return [slot.task_id for slot in self.slots]

    def to_json(self) -> str:
        """Re-serialize the plan, for feeding back into a repair prompt."""
        return json.dumps(
            {
                "schedule": [
                    {
                        "id": slot.task_id,
                        "start": slot.raw_start or format_hhmm(slot.start),
                        "why": slot.why,
                    }
                    for slot in self.slots
                ],
                "skipped": [{"id": task_id, "why": why} for task_id, why in self.skipped],
                "reasoning": self.reasoning,
                "tips": self.tips,
            },
            indent=2,
        )


def parse_plan(reply: str) -> AgentPlan:
    """Read the model's reply into an AgentPlan.

    Forgives a markdown fence. Anything else raises AgentReplyError and the
    planner retries.
    """
    text = reply.strip()
    if text.startswith("```"):
        # Drop the opening fence (with any language tag) and the closing fence.
        text = text.split("\n", 1)[-1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0].strip()

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError) as error:
        raise AgentReplyError(f"Reply wasn't valid JSON: {error}") from error
    if not isinstance(data, dict):
        raise AgentReplyError("Reply was JSON, but not an object.")

    slots: list[ProposedSlot] = []
    for entry in data.get("schedule") or []:
        if not isinstance(entry, dict):
            raise AgentReplyError("A schedule entry wasn't an object.")
        raw_start = str(entry.get("start", ""))
        slots.append(
            ProposedSlot(
                task_id=str(entry.get("id", "")),
                start=parse_hhmm(raw_start),
                why=str(entry.get("why", "")),
                raw_start=raw_start,
            )
        )

    skipped: list[tuple[str, str]] = []
    for entry in data.get("skipped") or []:
        if not isinstance(entry, dict):
            raise AgentReplyError("A skipped entry wasn't an object.")
        skipped.append((str(entry.get("id", "")), str(entry.get("why", ""))))

    tips = [str(tip) for tip in (data.get("tips") or [])]
    return AgentPlan(
        slots=slots,
        skipped=skipped,
        reasoning=str(data.get("reasoning", "")),
        tips=tips,
        raw=reply,
    )


# ---------------------------------------------------------------------------
# D: the evaluator
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Violation:
    """One thing wrong with a plan.

    "error" rejects the plan and sends it back. "warning" is shown to the owner.
    """

    code: str
    message: str
    severity: str = "error"
    task_id: str = ""

    def __str__(self) -> str:
        return self.message


@dataclass
class Evaluator:
    """Re-checks a proposed plan in code. The model can sound right and be wrong."""

    day_start: int = 8 * 60
    day_end: int = 21 * 60
    available_minutes: int = 0

    def check(self, plan: AgentPlan, candidates: dict[str, Task]) -> list[Violation]:
        """Return every violation found, errors and warnings together."""
        placed, violations = self._resolve(plan, candidates)
        violations += self._check_coverage(plan, candidates)
        violations += self._check_window(placed)
        violations += self._check_overlaps(placed)
        violations += self._check_budget(plan, placed, candidates)
        violations += self._check_quality(plan, placed, candidates)
        return violations

    @staticmethod
    def errors(violations: list[Violation]) -> list[Violation]:
        """Only the violations that reject a plan."""
        return [v for v in violations if v.severity == "error"]

    @staticmethod
    def warnings(violations: list[Violation]) -> list[Violation]:
        """Only the advisory violations."""
        return [v for v in violations if v.severity == "warning"]

    def _resolve(
        self, plan: AgentPlan, candidates: dict[str, Task]
    ) -> tuple[list[tuple[str, Task, int]], list[Violation]]:
        """Match slots to real Tasks, dropping unusable ones.

        Later checks run on the survivors, so one bad line can't hide the rest.
        """
        placed: list[tuple[str, Task, int]] = []
        violations: list[Violation] = []
        seen: set[str] = set()

        for slot in plan.slots:
            task = candidates.get(slot.task_id)
            if task is None:
                violations.append(Violation(
                    "unknown_task",
                    f"Scheduled {slot.task_id!r}, which isn't one of today's tasks.",
                    task_id=slot.task_id,
                ))
                continue
            if slot.task_id in seen:
                violations.append(Violation(
                    "duplicate_task",
                    f"{task.description!r} is scheduled more than once.",
                    task_id=slot.task_id,
                ))
                continue
            seen.add(slot.task_id)
            if slot.start is None:
                violations.append(Violation(
                    "bad_time",
                    f"{task.description!r} has an unreadable start time "
                    f"({slot.raw_start!r}). Use HH:MM, e.g. 08:30.",
                    task_id=slot.task_id,
                ))
                continue
            placed.append((slot.task_id, task, slot.start))

        return placed, violations

    def _check_coverage(
        self, plan: AgentPlan, candidates: dict[str, Task]
    ) -> list[Violation]:
        """Every candidate must be either scheduled or explicitly skipped."""
        violations: list[Violation] = []
        scheduled = set(plan.scheduled_ids())
        skipped = {task_id for task_id, _ in plan.skipped}

        for task_id in skipped - candidates.keys():
            violations.append(Violation(
                "unknown_task",
                f"Skipped {task_id!r}, which isn't one of today's tasks.",
                task_id=task_id,
            ))
        for task_id in scheduled & skipped:
            violations.append(Violation(
                "contradiction",
                f"{candidates[task_id].description!r} is both scheduled and skipped."
                if task_id in candidates else
                f"{task_id!r} is both scheduled and skipped.",
                task_id=task_id,
            ))
        for task_id, task in candidates.items():
            if task_id not in scheduled and task_id not in skipped:
                violations.append(Violation(
                    "missing_task",
                    f"{task.description!r} was dropped without being scheduled "
                    "or listed as skipped.",
                    task_id=task_id,
                ))
        return violations

    def _check_window(self, placed: list[tuple[str, Task, int]]) -> list[Violation]:
        """Flexible tasks must fit the day; pinned ones keep their time."""
        violations: list[Violation] = []
        window = f"{format_hhmm(self.day_start)}-{format_hhmm(self.day_end)}"

        for task_id, task, start in placed:
            label = f"{format_hhmm(start)}-{format_hhmm(start + task.duration)}"
            if task.start_time is not None and start != task.start_time:
                violations.append(Violation(
                    "moved_appointment",
                    f"{task.description!r} is pinned to "
                    f"{format_hhmm(task.start_time)} but was moved to "
                    f"{format_hhmm(start)}.",
                    task_id=task_id,
                ))
                continue
            outside = start < self.day_start or start + task.duration > self.day_end
            if not outside:
                continue
            if task.start_time is not None:
                # The owner pinned it there themselves - warn, don't reject.
                violations.append(Violation(
                    "appointment_outside_day",
                    f"{task.description!r} ({label}) is outside your {window} day, "
                    "but you pinned it there.",
                    severity="warning",
                    task_id=task_id,
                ))
            else:
                violations.append(Violation(
                    "outside_day",
                    f"{task.description!r} ({label}) falls outside your {window} day.",
                    task_id=task_id,
                ))
        return violations

    def _check_overlaps(self, placed: list[tuple[str, Task, int]]) -> list[Violation]:
        """No two scheduled tasks may share a minute (touching is fine)."""
        violations: list[Violation] = []
        for i, (_, first, first_start) in enumerate(placed):
            for _, second, second_start in placed[i + 1:]:
                if first_start < second_start + second.duration and \
                        second_start < first_start + first.duration:
                    same_pet = (
                        " (same pet - can't be in two places!)"
                        if first.pet_name and first.pet_name == second.pet_name
                        else ""
                    )
                    violations.append(Violation(
                        "overlap",
                        f"{first.description!r} at {format_hhmm(first_start)} overlaps "
                        f"{second.description!r} at {format_hhmm(second_start)}"
                        f"{same_pet}.",
                    ))
        return violations

    def _check_budget(
        self,
        plan: AgentPlan,
        placed: list[tuple[str, Task, int]],
        candidates: dict[str, Task],
    ) -> list[Violation]:
        """The plan must fit the owner's minutes, and shouldn't waste them."""
        violations: list[Violation] = []
        used = sum(task.duration for _, task, _ in placed)
        if used > self.available_minutes:
            violations.append(Violation(
                "over_budget",
                f"The plan needs {used} min but you only have "
                f"{self.available_minutes} min today.",
            ))
            return violations

        # Room left over that a skipped task would have fit into. Advisory: the
        # gap may genuinely have been too fragmented to use.
        leftover = self.available_minutes - used
        skipped_durations = [
            candidates[task_id].duration
            for task_id, _ in plan.skipped
            if task_id in candidates
        ]
        if skipped_durations and min(skipped_durations) <= leftover:
            violations.append(Violation(
                "unused_time",
                f"{leftover} min went unused, and a skipped task would have fit.",
                severity="warning",
            ))
        return violations

    def _check_quality(
        self,
        plan: AgentPlan,
        placed: list[tuple[str, Task, int]],
        candidates: dict[str, Task],
    ) -> list[Violation]:
        """Catch a plan that obeys the letter of the rules but is still poor."""
        violations: list[Violation] = []

        # An empty plan when there was time and work to do is a non-answer.
        if not placed and candidates:
            cheapest = min(task.duration for task in candidates.values())
            if cheapest <= self.available_minutes:
                violations.append(Violation(
                    "empty_plan",
                    "Nothing was scheduled even though there was time for at "
                    "least one task.",
                ))

        # Skipping something important while doing something less important.
        # Pinned tasks are exempt: an appointment outranks priority by design.
        flexible_placed = [
            task for _, task, _ in placed if task.start_time is None
        ]
        for task_id, _ in plan.skipped:
            skipped_task = candidates.get(task_id)
            if skipped_task is None:
                continue
            outranked = [
                task for task in flexible_placed
                if task.priority.value > skipped_task.priority.value
            ]
            if outranked:
                violations.append(Violation(
                    "priority_inversion",
                    f"{skipped_task.description!r} "
                    f"({skipped_task.priority.name.title()}) was skipped while "
                    f"{outranked[0].description!r} "
                    f"({outranked[0].priority.name.title()}) was kept.",
                    severity="warning",
                    task_id=task_id,
                ))

        if not plan.reasoning.strip():
            violations.append(Violation(
                "no_reasoning",
                "The plan came back with no explanation.",
                severity="warning",
            ))
        return violations


# ---------------------------------------------------------------------------
# C: the planner, and the repair loop around it
# ---------------------------------------------------------------------------

@dataclass
class Attempt:
    """One trip to the model: what came back and what the evaluator said."""

    number: int
    kind: str                     # "plan", "repair" or "revise"
    plan: AgentPlan | None = None
    violations: list[Violation] = field(default_factory=list)
    error: str = ""               # set when the reply couldn't even be parsed

    @property
    def passed(self) -> bool:
        return (
            self.plan is not None
            and not self.error
            and not Evaluator.errors(self.violations)
        )


@dataclass
class AgentRun:
    """The result of one planning run, plus the trail of how it got there."""

    candidates: dict[str, Task]
    attempts: list[Attempt] = field(default_factory=list)
    plan: AgentPlan | None = None            # the plan that passed, if any
    violations: list[Violation] = field(default_factory=list)
    day_start: int = 8 * 60
    day_end: int = 21 * 60
    fallback: Scheduler | None = None        # rule-based plan, if the agent failed
    preferences: str = ""

    @property
    def ok(self) -> bool:
        """True when a proposal passed the evaluator and is ready for review."""
        return self.plan is not None and not Evaluator.errors(self.violations)

    @property
    def used_fallback(self) -> bool:
        return self.fallback is not None

    def warnings(self) -> list[Violation]:
        """Advisory notes the owner should read before approving."""
        return Evaluator.warnings(self.violations)

    def errors(self) -> list[Violation]:
        """Reasons the last proposal was rejected."""
        return Evaluator.errors(self.violations)

    def rows(self) -> list[dict]:
        """Preview the proposed day, earliest first.

        Read-only on purpose: an unapproved suggestion must not change the
        owner's tasks (see approve()).
        """
        if self.plan is None:
            return []
        rows = []
        for slot in self.plan.slots:
            task = self.candidates.get(slot.task_id)
            if task is None or slot.start is None:
                continue
            rows.append({
                "Time": f"{format_hhmm(slot.start)}-"
                        f"{format_hhmm(slot.start + task.duration)}",
                "Pet": task.pet_name or "Unassigned",
                "Priority": task.priority.name.title(),
                "Task": task.description,
                "Duration (min)": task.duration,
                "Why": slot.why,
                "_start": slot.start,
            })
        rows.sort(key=lambda row: row["_start"])
        for row in rows:
            row.pop("_start")
        return [{"#": i, **row} for i, row in enumerate(rows, start=1)]

    def skipped_rows(self) -> list[dict]:
        """The tasks the agent left out, with its reason for each."""
        if self.plan is None:
            return []
        rows = []
        for task_id, why in self.plan.skipped:
            task = self.candidates.get(task_id)
            if task is None:
                continue
            rows.append({
                "Task": task.description,
                "Pet": task.pet_name or "Unassigned",
                "Priority": task.priority.name.title(),
                "Duration (min)": task.duration,
                "Why skipped": why,
            })
        return rows

    def approve(self) -> Scheduler:
        """E -> F: accept the plan and write it onto the owner's tasks.

        The only place the agent changes real state, and only after the checker
        passed and the owner said yes. Returns a Scheduler so the app can show
        an AI plan exactly like a rule-based one.
        """
        if not self.ok or self.plan is None:
            raise AgentError("This plan didn't pass the checks, so it can't be approved.")

        # Clear every candidate first, so a task the agent dropped can't keep a
        # stale time from an earlier plan (same guarantee generate_plan gives).
        for task in self.candidates.values():
            task.scheduled_start = None

        placed: list[Task] = []
        for slot in self.plan.slots:
            task = self.candidates.get(slot.task_id)
            if task is None or slot.start is None:
                continue
            task.scheduled_start = slot.start
            placed.append(task)

        scheduler = Scheduler(day_start=self.day_start, day_end=self.day_end)
        scheduler.tasks = scheduler.sort_by_time(placed)
        scheduler.skipped_tasks = [
            self.candidates[task_id]
            for task_id, _ in self.plan.skipped
            if task_id in self.candidates
        ]
        scheduler.conflicts = scheduler.detect_conflicts(scheduler.tasks)
        scheduler.warnings = [v.message for v in self.warnings()]
        used = sum(task.duration for task in placed)
        attempts = len(self.attempts)
        scheduler.reasoning = (
            f"{self.plan.reasoning.strip()} "
            f"(AI plan: {len(placed)} task(s), {used} min, "
            f"{len(scheduler.skipped_tasks)} skipped, approved after "
            f"{attempts} model call{'s' if attempts != 1 else ''}.)"
        ).strip()
        return scheduler


@dataclass
class PlannerAgent:
    """Asks the model for a plan, then checks and repairs it until it holds."""

    client: LLMClient
    day_start: int = 8 * 60
    day_end: int = 21 * 60
    max_attempts: int = 3          # 1 first try + 2 repairs
    prompt_dir: Path = PROMPT_DIR

    def _prompt(self, name: str) -> str:
        """Load a prompt template from the prompts/ folder."""
        path = self.prompt_dir / name
        try:
            return path.read_text(encoding="utf-8")
        except OSError as error:
            raise AgentError(f"Couldn't read prompt {path.name}: {error}") from error

    def suggest(
        self,
        owner: Owner,
        day_index: int = 0,
        preferences: str = "",
    ) -> AgentRun:
        """Plan the owner's day: propose, auto-check, repair, hand to the human."""
        candidates = candidate_tasks(owner, day_index)
        run = AgentRun(
            candidates=candidates,
            day_start=self.day_start,
            day_end=self.day_end,
            preferences=preferences,
        )
        if not candidates:
            # Nothing to ask the model about - don't spend a call on an empty day.
            run.violations = [Violation(
                "no_tasks",
                "Nothing to plan: no unfinished tasks are due on this day.",
                severity="warning",
            )]
            run.plan = AgentPlan(reasoning="No tasks were due, so the day is clear.")
            return run

        context_json, evaluator = self._setup(owner, candidates, day_index)
        first_prompt = (
            self._prompt("planner_user.txt")
            .replace("__CONTEXT__", context_json)
            .replace("__PREFERENCES__", _or_none(preferences))
        )
        return self._loop(run, owner, day_index, context_json, evaluator,
                          first_prompt, kind="plan")

    def revise(
        self,
        owner: Owner,
        run: AgentRun,
        feedback: str,
        day_index: int = 0,
    ) -> AgentRun:
        """E -> C: re-plan with the owner's feedback.

        Reuses the original ids so "move the walk later" means the same task,
        then runs the same check-and-repair loop as a first pass.
        """
        if run.plan is None:
            return self.suggest(owner, day_index, run.preferences)

        context_json, evaluator = self._setup(owner, run.candidates, day_index)
        revised = AgentRun(
            candidates=run.candidates,
            day_start=self.day_start,
            day_end=self.day_end,
            preferences=run.preferences,
        )
        first_prompt = (
            self._prompt("planner_review.txt")
            .replace("__CONTEXT__", context_json)
            .replace("__PREFERENCES__", _or_none(run.preferences))
            .replace("__PREVIOUS__", run.plan.to_json())
            .replace("__FEEDBACK__", feedback.strip() or "Try a different layout.")
        )
        return self._loop(revised, owner, day_index, context_json, evaluator,
                          first_prompt, kind="revise")

    def _setup(
        self, owner: Owner, candidates: dict[str, Task], day_index: int
    ) -> tuple[str, Evaluator]:
        """Build the prompt context and an evaluator that shares its limits."""
        context = build_context(
            owner, candidates, day_index, self.day_start, self.day_end
        )
        evaluator = Evaluator(
            day_start=self.day_start,
            day_end=self.day_end,
            available_minutes=context["available_minutes"],
        )
        return json.dumps(context, indent=2), evaluator

    def _loop(
        self,
        run: AgentRun,
        owner: Owner,
        day_index: int,
        context_json: str,
        evaluator: Evaluator,
        user: str,
        kind: str,
    ) -> AgentRun:
        """Propose -> check -> repair, up to max_attempts, then fall back.

        A first pass and a revision differ only in the opening prompt. Every
        attempt is kept so the owner can see how the plan was reached.
        """
        system = self._prompt("planner_system.txt")
        prefs = _or_none(run.preferences)

        for number in range(1, self.max_attempts + 1):
            attempt = Attempt(number=number, kind=kind)
            run.attempts.append(attempt)
            try:
                plan = parse_plan(self.client.complete(system, user, PLAN_SCHEMA))
            except AgentReplyError as error:
                attempt.error = str(error)     # unreadable - worth another try
            except AgentError as error:
                # A transport failure (bad key, no quota, network) won't fix
                # itself on a retry with the same prompt, so stop and fall back.
                attempt.error = str(error)
                break
            else:
                attempt.plan = plan
                attempt.violations = evaluator.check(plan, run.candidates)
                run.plan = plan
                run.violations = attempt.violations
                if attempt.passed:
                    return run

            if number == self.max_attempts:
                break

            # D fail -> C: hand the model its own plan and the exact objections.
            kind = "repair"
            previous = attempt.plan.to_json() if attempt.plan else "(unreadable reply)"
            problems = attempt.error or self._describe(evaluator.errors(attempt.violations))
            user = (
                self._prompt("planner_repair.txt")
                .replace("__CONTEXT__", context_json)
                .replace("__PREFERENCES__", prefs)
                .replace("__PREVIOUS__", previous)
                .replace("__VIOLATIONS__", problems)
            )

        # Out of attempts: fall back to the rule-based scheduler so the owner
        # always leaves with a usable plan, agent or no agent.
        run.fallback = Scheduler(
            day_start=self.day_start, day_end=self.day_end
        ).generate_plan(owner, day_index=day_index)
        return run

    @staticmethod
    def _describe(violations: list[Violation]) -> str:
        """Format violations as a numbered list for the repair prompt."""
        if not violations:
            return "(no specific problems reported)"
        return "\n".join(
            f"{i}. [{v.code}] {v.message}" for i, v in enumerate(violations, start=1)
        )
