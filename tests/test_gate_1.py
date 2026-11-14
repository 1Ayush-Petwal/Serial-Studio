"""Speckled Band -> bible and clue ledger -> gate 1, at the graph-runner seam."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError

from serial_studio import db, story_architect
from serial_studio.gateway import Gateway
from serial_studio.schemas import Bible, Decision, ModelRequest, ModelResponse, StartRun

from .conftest import App, FakeNetwork

SPECKLED_BAND = StartRun(title="The Speckled Band", book_id=1661)
TARGET_V1 = "bible:the-speckled-band:v1"
SCENES = 8  # 9.8k words packed into ~1,200-word scenes
# Gate-1 notes, as given when the fixture was recorded (each recorded re-run is keyed on them).
NOTES_V1 = (
    "Missed clues: Julia Stoner's dying words about the speckled band, and the saucer of milk "
    "on top of Roylott's safe. Add pronunciations for Roylott and Stoke Moran."
)
NOTES_V2 = (
    "Also missed: the clanging sound, as if a mass of metal had fallen, "
    "that Helen heard after the whistle on the night her sister died."
)


def bible_of(status: Any) -> Bible:
    return Bible.model_validate(status.gate.payload["bible"])


def clue_with(bible: Bible, word: str) -> Any:
    return next(c for c in bible.clues if any(word in k for k in c.keywords))


def assert_fair_play_clue(bible: Bible, text: str, word: str) -> None:
    clue = clue_with(bible, word)
    assert 2 <= len(clue.keywords) <= 4
    assert clue.position.exact
    assert text[clue.position.offset :].startswith(clue.position.quote)


def approve(app: App, run_id: str, target: str) -> Any:
    return app.runner.decide(Decision(run_id=run_id, gate=1, target=target, verdict="approve"))


def test_run_pauses_at_gate_1_with_versioned_bible_and_fair_play_clues(make_app: Callable[..., App]) -> None:
    app = make_app()
    status = app.runner.start(SPECKLED_BAND)

    assert status.state == "paused"
    assert status.gate is not None
    assert (status.gate.gate, status.gate.target) == (1, TARGET_V1)
    bible = bible_of(status)
    assert [b.version for b in db.bible_versions(app.conn, "the-speckled-band")] == [1]
    assert {"Sherlock Holmes", "Helen Stoner"} <= {c.name for c in bible.characters}

    story = db.story(app.conn, "the-speckled-band")
    assert "gutenberg" not in story.text.lower()
    assert "licen" not in story.text.lower()
    assert not re.search(r"[^\n]\n[^\n]", story.text), "hard line-wrap left inside a paragraph"
    assert story.text.startswith("On glancing over my notes")

    for word in ("whistle", "clang"):
        assert_fair_play_clue(bible, story.text, word)


def test_reject_with_notes_reruns_story_architect_with_those_notes(
    make_app: Callable[..., App], network: FakeNetwork
) -> None:
    app = make_app()
    run_id = app.runner.start(SPECKLED_BAND).run_id

    def reject(version: int, notes: str) -> Any:
        target = f"bible:the-speckled-band:v{version}"
        return app.runner.decide(Decision(run_id=run_id, gate=1, target=target, verdict="reject", notes=notes))

    v2 = reject(1, NOTES_V1)
    assert v2.gate is not None and v2.gate.target == "bible:the-speckled-band:v2"
    calls = network.model_calls()
    assert len(calls) == 2 * SCENES
    assert all(NOTES_V1 in c["messages"][-1]["content"] for c in calls[SCENES:])

    # Extraction is sampled: the recorded v1 missed the milk, v2 the clang. A second reject
    # keeps the first notes, so v3 has every fair-play clue the reviewer asked for.
    v3 = reject(2, NOTES_V2)
    assert v3.gate is not None and v3.gate.target == "bible:the-speckled-band:v3"
    calls = network.model_calls()[2 * SCENES :]
    assert len(calls) == SCENES
    assert all(NOTES_V1 in c["messages"][-1]["content"] and NOTES_V2 in c["messages"][-1]["content"] for c in calls)
    text = db.story(app.conn, "the-speckled-band").text
    for word in ("whistle", "clang", "milk"):
        assert_fair_play_clue(bible_of(v3), text, word)
    assert [b.version for b in db.bible_versions(app.conn, "the-speckled-band")] == [1, 2, 3]
    # Approval hands bible v3 to the Beat Planner (its plan for v3 is not recorded, so the call stops there).
    with pytest.raises(Exception, match="network disabled"):
        approve(app, run_id, "bible:the-speckled-band:v3")
    planner = network.model_calls()[-1]
    assert planner["model"].startswith("gemini")
    assert "milk" in planner["messages"][1]["content"], "planner was not given the approved v3 bible"


def test_decision_for_a_stale_target_is_refused(make_app: Callable[..., App]) -> None:
    app = make_app()
    run_id = app.runner.start(SPECKLED_BAND).run_id

    with pytest.raises(ValueError, match="not waiting on"):
        approve(app, run_id, "bible:the-speckled-band:v9")
    assert app.runner.status(run_id).state == "paused"


def test_killed_run_resumes_from_last_completed_node(make_app: Callable[..., App], network: FakeNetwork) -> None:
    class KilledOnFourthCall(Gateway):
        calls = 0

        def complete(self, req: ModelRequest) -> ModelResponse:
            KilledOnFourthCall.calls += 1
            if KilledOnFourthCall.calls == 4:
                raise KeyboardInterrupt("process killed")
            return super().complete(req)

    first = make_app(KilledOnFourthCall)
    with pytest.raises(KeyboardInterrupt):
        first.runner.start(SPECKLED_BAND)
    run_id = first.conn.execute("SELECT DISTINCT run_id FROM cost_lines").fetchone()["run_id"]
    assert first.runner.status(run_id).state == "stopped"

    restarted = make_app()
    status = restarted.runner.resume(run_id)

    assert status.gate is not None and status.gate.target == TARGET_V1
    assert len(db.cost_lines(restarted.conn, run_id)) == SCENES, "a completed scene was re-run"
    assert len(network.model_calls()) == SCENES


def test_every_model_call_writes_a_cost_line_and_a_trace(make_app: Callable[..., App]) -> None:
    app = make_app()
    run_id = app.runner.start(SPECKLED_BAND).run_id

    lines = db.cost_lines(app.conn, run_id)
    assert len(lines) == SCENES
    for line in lines:
        assert (line.stage, line.node, line.provider) == ("judge", "story_architect", "groq")
        assert line.input_tokens > 0 and line.output_tokens > 0 and line.list_price_usd > 0
        assert not line.cache_hit
    generations = app.generations()
    assert len(generations) == SCENES
    assert all(g["session.id"] == run_id for g in generations)


def test_second_identical_run_makes_zero_network_calls(make_app: Callable[..., App], network: FakeNetwork) -> None:
    app = make_app()
    first = app.runner.start(SPECKLED_BAND)
    sent = len(network.requests)

    second = app.runner.start(SPECKLED_BAND)

    assert len(network.requests) == sent
    assert bible_of(second).clues == bible_of(first).clues
    assert all(line.cache_hit for line in db.cost_lines(app.conn, second.run_id))
    assert len(app.generations()) == 2 * SCENES


def test_prompt_version_bump_reruns_the_model(
    make_app: Callable[..., App], network: FakeNetwork, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = make_app()
    app.runner.start(SPECKLED_BAND)
    monkeypatch.setattr(story_architect, "PROMPT_VERSION", story_architect.PROMPT_VERSION + "-bumped")

    app.runner.start(SPECKLED_BAND)

    assert len(network.model_calls()) == 2 * SCENES


def test_judge_model_is_swapped_by_configuration_only(
    make_app: Callable[..., App], network: FakeNetwork, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JUDGE_MODEL", "groq:llama-3.3-70b-versatile")
    app = make_app()

    with pytest.raises(Exception, match="network disabled"):
        app.runner.start(SPECKLED_BAND)

    [call] = network.model_calls()
    assert call["model"] == "llama-3.3-70b-versatile"


def test_malformed_stage_input_fails_loudly(make_app: Callable[..., App], network: FakeNetwork) -> None:
    with pytest.raises(ValidationError):
        StartRun(title="", book_id=1661)

    one_keyword_clue = {
        "characters": [],
        "places": [],
        "facts": [],
        "pronunciations": [],
        "opened_threads": [],
        "closed_threads": [],
        "clues": [{"id": "x", "text": "x", "kind": "presence", "quote": "x", "keywords": ["only"]}],
    }
    network.override = lambda body: {
        "choices": [{"message": {"content": json.dumps(one_keyword_clue)}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }
    app = make_app()

    with pytest.raises(ValidationError, match="keywords"):
        app.runner.start(SPECKLED_BAND)
