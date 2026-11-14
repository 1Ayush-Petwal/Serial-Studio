"""The whole season at gate 3: parallel drafts, seams, in-order approval, reconciliation."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

import pytest

from serial_studio import db
from serial_studio.schemas import Decision, Script

from .conftest import App, FakeNetwork
from .test_gate_2 import decide
from .test_gate_3 import at_gate_3, brief, good_draft, record_answer, screenplay_calls, then_good, writer

NEW_ENDING = "End on her scream instead of the whistle."


def test_the_season_drafts_in_parallel_and_every_episode_reaches_gate_3(
    make_app: Callable[..., App], network: FakeNetwork
) -> None:
    # Episodes 1 and 2 each wait for the other: drafted one after another, the barrier times out.
    both = threading.Barrier(2, timeout=10)

    def together(b: dict[str, Any], take: int) -> dict[str, Any]:
        both.wait()
        return good_draft(b)

    network.override = writer({1: together, 2: together})
    status = at_gate_3(make_app())

    season = status.gate.payload["season"]
    assert [x["episode"] for x in season] == list(range(1, len(season) + 1)) and 5 <= len(season) <= 7
    assert all(x["violations"] == [] and not x["approved"] for x in season)
    assert status.gate.target == "script:the-speckled-band:ep1:v1"


@pytest.mark.parametrize(
    ("breaks", "note"),
    [
        (lambda d: d["lines"].__setitem__(0, {"speaker": "narrator", "text": "Morning came grey."}), "pick up"),
        (lambda d: d["lines"][0].__setitem__("speaker", "Sherlock Holmes"), "recap as one narrator line"),
    ],
    ids=["seam", "recap"],
)
def test_an_opening_that_misses_the_previous_ending_goes_back(
    make_app: Callable[..., App], network: FakeNetwork, breaks: Callable[[dict[str, Any]], None], note: str
) -> None:
    def bad(b: dict[str, Any]) -> dict[str, Any]:
        d = good_draft(b)
        breaks(d)
        return d

    network.override = writer({2: then_good(bad)})
    status = at_gate_3(make_app())

    first, revision = screenplay_calls(network, episode=2)
    assert note in revision["messages"][-1]["content"]
    ep2 = status.gate.payload["season"][1]
    assert ep2["violations"] == [] and ep2["revisions"] == 1


def test_approving_episode_2_before_episode_1_is_refused(make_app: Callable[..., App], network: FakeNetwork) -> None:
    network.override = writer()
    app = make_app()
    status = at_gate_3(app)

    early = Decision(run_id=status.run_id, gate=3, target="script:the-speckled-band:ep2:v1", verdict="approve")
    with pytest.raises(ValueError, match="not waiting on"):
        app.runner.decide(early)
    assert app.runner.status(status.run_id).gate.target == "script:the-speckled-band:ep1:v1"


def test_a_new_ending_for_episode_1_sends_episode_2_back_before_the_editor_sees_it(
    make_app: Callable[..., App], network: FakeNetwork
) -> None:
    def rewritten(b: dict[str, Any], take: int) -> dict[str, Any]:
        d = good_draft(b)
        if take:  # the editor's rewrite ends somewhere new
            d["lines"][-1]["text"] = "[sting] Then a terrible scream rang out."
        return d

    def recorded(body: dict[str, Any]) -> dict[str, Any]:
        if "terrible scream" in body["messages"][1]["content"]:
            ending = {"event": "Helen screams in the night.", "keywords": ["terrible", "scream"]}
            return {"ending": ending, "established": ["Helen screamed."], "differs_from_plan": ["new ending"]}
        return record_answer(body)

    network.override = writer({1: rewritten}, record=recorded)
    app = make_app()
    edited = decide(app, at_gate_3(app), "reject", NEW_ENDING)
    assert edited.gate.target == "script:the-speckled-band:ep1:v2"

    nxt = decide(app, edited, "approve")

    assert nxt.gate.target == "script:the-speckled-band:ep2:v1"
    first, revision = screenplay_calls(network, episode=2)
    assert "'terrible', 'scream'" in revision["messages"][-1]["content"], "the seam note names the new ending"
    assert brief(revision)["previous_cliffhanger"]["keywords"] == ["terrible", "scream"]
    ep2 = nxt.gate.payload
    assert ep2["episode"] == 2 and ep2["violations"] == [] and ep2["revisions"] == 1
    assert "terrible scream" in ep2["markup"][0], "episode 2 now opens on the new ending"


def test_each_approval_writes_a_new_bible_version_until_the_season_is_done(
    make_app: Callable[..., App], network: FakeNetwork
) -> None:
    network.override = writer()
    app = make_app()
    status = at_gate_3(app)
    cast_version = db.bible_versions(app.conn, "the-speckled-band")[-1].version
    episodes = len(status.gate.payload["season"])

    for n in range(1, episodes + 1):
        assert status.gate.target == f"script:the-speckled-band:ep{n}:v1"
        status = decide(app, status, "approve")
        bible = db.bible_versions(app.conn, "the-speckled-band")[-1]
        assert bible.version == cast_version + n
        assert [r.episode for r in bible.episodes] == list(range(1, n + 1))
        assert bible.episodes[-1].planted == sorted({c.id for c in bible.clues if c.assigned_episode == n})

    assert status.state == "done"
    assert bible.episodes[-1].ending is None, "the last episode ends the season, not on a cliffhanger"
    scripts = db.scripts(app.conn, "the-speckled-band", "pipeline")
    assert [s.episode for s in scripts] == list(range(1, episodes + 1))
    assert all(isinstance(s, Script) for s in scripts)
