"""Approved bible -> Beat Planner season plan and casting -> gate 2, at the graph-runner seam."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest

from serial_studio import db, screenplay
from serial_studio.schemas import Decision, SeasonPlan

from .conftest import App, FakeNetwork
from .test_gate_1 import SPECKLED_BAND, TARGET_V1, approve

TARGET_PLAN_V1 = "season-plan:the-speckled-band:v1"
PLAN_NOTES = "Use a female narrator voice."
SPEAKERS = {"Sherlock Holmes", "Dr. John H. Watson", "Helen Stoner", "Dr. Roylott"}
# Gate 3's tests cover scripts; here any answer will do to show the run moves on.
TINY_SCRIPT = {"title": "t", "blurb": "b", "lines": [{"speaker": "narrator", "text": "Fog."}]}


def is_screenplay(body: dict[str, Any]) -> bool:
    return bool(body["messages"][0]["content"].startswith(screenplay.SYSTEM))


def at_gate_2(app: App) -> Any:
    run_id = app.runner.start(SPECKLED_BAND).run_id
    return approve(app, run_id, TARGET_V1)


def plan_of(status: Any) -> SeasonPlan:
    return SeasonPlan.model_validate(status.gate.payload["plan"])


def decide(app: App, status: Any, verdict: str, notes: str = "") -> Any:
    gate = status.gate
    return app.runner.decide(
        Decision(run_id=status.run_id, gate=gate.gate, target=gate.target, verdict=verdict, notes=notes)  # type: ignore[arg-type]
    )


def planner_calls(network: FakeNetwork) -> list[dict[str, Any]]:
    return [c for c in network.model_calls() if c["model"].startswith("gemini")]


def answer(plan: dict[str, Any] | str) -> dict[str, Any]:
    content = plan if isinstance(plan, str) else json.dumps(plan)
    return {"choices": [{"message": {"content": content}}], "usage": {"prompt_tokens": 1, "completion_tokens": 1}}


CRITICS = ("Tone critic", "Character critic", "Structure critic", "Ear critic", "Lead critic")
PASSING_PANEL: dict[str, dict[str, Any]] = {
    "Character critic": {"score": 4, "notes": ["The voices are distinct."], "guesses": []},
    "Lead critic": {"notes": [{"critic": "tone", "note": "Keep the period voice.", "must_fix": False, "rank": 1}]},
}


def critic_of(body: dict[str, Any]) -> str | None:
    """Which crew member a judge call comes from (CrewAI opens each system prompt with the role)."""
    system = body["messages"][0]["content"]
    return next((r for r in CRITICS if system.startswith(f"You are {r}.")), None)


def panel(body: dict[str, Any], answers: dict[str, dict[str, Any]] | None = None) -> dict[str, Any] | None:
    """A critic's final answer in CrewAI's format; scores 4, nothing must be fixed unless `answers` says so."""
    role = critic_of(body)
    if role is None:
        return None
    out = (answers or {}).get(role) or PASSING_PANEL.get(role) or {"score": 4, "notes": ["Works."]}
    return answer(f"Thought: I now can give a great answer\nFinal Answer: {json.dumps(out)}")


def recorded_plan(network: FakeNetwork) -> dict[str, Any]:
    """The first recorded Beat Planner answer for the v1 bible."""
    row = next(r for r in network.rows if r["kind"] == "model" and r["request"]["provider"] == "gemini")
    plan: dict[str, Any] = json.loads(row["response"]["choices"][0]["message"]["content"])
    return plan


def test_approved_bible_leads_to_a_fair_play_season_plan_at_gate_2(make_app: Callable[..., App]) -> None:
    app = make_app()
    status = at_gate_2(app)

    assert status.state == "paused"
    assert (status.gate.gate, status.gate.target) == (2, TARGET_PLAN_V1)
    plan = plan_of(status)
    bible = db.bible_versions(app.conn, "the-speckled-band")[0]
    assert plan.bible_version == bible.version == 1
    assert 5 <= len(plan.episodes) <= 7
    assert [e.episode for e in plan.episodes] == list(range(1, len(plan.episodes) + 1))
    assert all(3 <= len(e.beats) <= 5 for e in plan.episodes)
    starts = [e.start for e in plan.episodes]
    assert starts == sorted(set(starts)), "episodes must cover the story in order"

    planted = {cid: e.episode for e in plan.episodes for b in e.beats for cid in b.clue_ids}
    revealed = {cid: e.episode for e in plan.episodes for cid in e.reveals}
    for clue in bible.clues:
        assert planted[clue.id] <= revealed[clue.id], clue.id

    *middle, last = plan.episodes
    for e in middle:
        assert e.cliffhanger is not None and 2 <= len(e.cliffhanger.keywords) <= 4
        assert "the" not in e.cliffhanger.keywords, "a stopword makes the seam check trivially true"
    assert last.cliffhanger is None
    assert plan.episodes[0].recap is None and all(e.recap for e in plan.episodes[1:])
    for prev, nxt in zip(plan.episodes, plan.episodes[1:], strict=False):
        assert nxt.previous_cliffhanger == prev.cliffhanger, "seam not handed to the next episode"

    assert plan.casting.keys() >= SPEAKERS
    assert plan.casting["narrator"] != plan.casting["Dr. John H. Watson"]
    assert len(set(plan.casting.values())) == len(plan.casting)

    planner_lines = [line for line in db.cost_lines(app.conn, status.run_id) if line.node == "beat_planner"]
    assert planner_lines and all((x.stage, x.provider) == ("text", "gemini") for x in planner_lines)


def test_gate_2_approve_writes_casting_and_clue_episodes_into_a_new_bible_version(
    make_app: Callable[..., App], network: FakeNetwork
) -> None:
    app = make_app()
    status = at_gate_2(app)
    plan = plan_of(status)

    network.override = lambda body: answer(TINY_SCRIPT) if is_screenplay(body) else panel(body)
    done = decide(app, status, "approve")

    assert done.gate.gate == 3, "an approved plan goes on to the Screenplay agent"
    v1, v2 = db.bible_versions(app.conn, "the-speckled-band")
    assert v2.version == 2
    assert v2.narrator_voice_id == plan.casting["narrator"]
    for c in v2.characters:
        assert c.voice_id == plan.casting.get(c.name)
    for clue in v2.clues:
        assert clue.assigned_episode is not None and clue.reveal_episode is not None
        assert clue.assigned_episode <= clue.reveal_episode
    assert [c.id for c in v2.clues] == [c.id for c in v1.clues]


def test_gate_2_reject_reruns_the_beat_planner_with_the_notes(
    make_app: Callable[..., App], network: FakeNetwork
) -> None:
    app = make_app()
    first = at_gate_2(app)
    sent = len(planner_calls(network))
    # One free-tier Gemini plan takes hours to come back, so the re-run replays the recorded plan.
    recorded = recorded_plan(network)

    def respond(body: dict[str, Any]) -> dict[str, Any] | None:
        if is_screenplay(body):
            return answer(TINY_SCRIPT)
        if critic_of(body):
            return panel(body)
        return answer(recorded) if PLAN_NOTES in json.dumps(body) else None

    network.override = respond

    second = decide(app, first, "reject", PLAN_NOTES)

    assert second.gate is not None and second.gate.target == "season-plan:the-speckled-band:v2"
    [rerun] = planner_calls(network)[sent:]
    assert PLAN_NOTES in rerun["messages"][1]["content"]
    assert decide(app, second, "approve").gate.gate == 3


def test_a_plan_breaking_the_rules_goes_back_to_the_planner_with_the_problems(
    make_app: Callable[..., App], network: FakeNetwork
) -> None:
    good = recorded_plan(network)
    bad = json.loads(json.dumps(good))
    bad["episodes"][0]["cliffhanger"] = None
    bad["narrator_voice"] = good["casting"][0]["voice_id"]
    answers = [bad, good]

    network.override = lambda body: answer(answers.pop(0)) if body["model"].startswith("gemini") else None
    status = at_gate_2(make_app())

    assert status.gate.target == TARGET_PLAN_V1
    first, repair = planner_calls(network)
    assert repair["messages"][:2] == first["messages"]
    feedback = repair["messages"][-1]["content"]
    assert "episode 1: needs a cliffhanger" in feedback
    assert "distinct voices" in feedback


def test_a_plan_still_breaking_the_rules_after_repairs_fails_loudly(
    make_app: Callable[..., App], network: FakeNetwork
) -> None:
    bad = recorded_plan(network)
    bad["episodes"][-1]["reveals"] = []
    bad["episodes"][0]["reveals"] = []

    network.override = lambda body: answer(bad) if body["model"].startswith("gemini") else None

    with pytest.raises(ValueError, match="broke the rules"):
        at_gate_2(make_app())
    assert len(planner_calls(network)) == 3
