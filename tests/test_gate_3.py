"""Gate 2 -> Screenplay agent -> validators and revise loop -> gate 3, at the graph-runner seam.

Writer answers are canned per test (built from the episode brief the agent sends), so every
validator rule gets a failing and a passing case without a model call.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest

from serial_studio import db, screenplay
from serial_studio.graph import MAX_REVISIONS
from serial_studio.schemas import Script

from .conftest import App, FakeNetwork
from .test_gate_2 import answer, at_gate_2, decide, is_screenplay, recorded_plan

FILLER = "The fog lay thick on Baker Street and the lamps burned low while the clock ticked on."
NOTES = "Open on the knock at the bedroom door."


def brief(body: dict[str, Any]) -> dict[str, Any]:
    user = body["messages"][1]["content"]
    out: dict[str, Any] = json.loads(user.split("Episode brief:\n", 1)[1].split("\n", 1)[0])
    return out


def good_draft(b: dict[str, Any], words: int = 250) -> dict[str, Any]:
    """A script that passes every rule: each planned clue marked with its keywords, cast speakers only."""
    cast = b["cast"]
    lines = [{"speaker": "narrator", "text": "[bed:rain] A knock at dawn, and a veiled woman trembling at the door."}]
    lines += [
        {"speaker": "narrator", "text": f"[clue:{c['id']}] Holmes notes the {' '.join(c['keywords'])} at once. [/clue]"}
        for c in b["clues_to_plant"]
    ]
    lines.append({"speaker": cast[0], "text": "You have come in by train this morning, I see."})
    lines.append({"speaker": cast[-1], "text": "I am afraid, sir, of what waits for me at home."})
    count = sum(len(x["text"].split()) for x in lines)
    while count + len(FILLER.split()) <= words - 10:
        lines.insert(-2, {"speaker": "narrator", "text": FILLER})
        count += len(FILLER.split())
    lines.append({"speaker": "narrator", "text": "[sting] Then, in the dark, a low clear whistle."})
    return {"title": b["title"], "blurb": "A frightened client brings Holmes a deadly puzzle.", "lines": lines}


def writer(*drafts: Callable[[dict[str, Any]], dict[str, Any]]) -> Callable[[dict[str, Any]], dict[str, Any] | None]:
    """Answer screenplay calls in turn (the last one repeats); leave every other call to the recordings."""
    queue = list(drafts)

    def respond(body: dict[str, Any]) -> dict[str, Any] | None:
        if not is_screenplay(body):
            return None
        make = queue.pop(0) if len(queue) > 1 else queue[0]
        return answer(make(brief(body)))

    return respond


def screenplay_calls(network: FakeNetwork) -> list[dict[str, Any]]:
    return [c for c in network.model_calls() if is_screenplay(c)]


def at_gate_3(app: App) -> Any:
    return decide(app, at_gate_2(app), "approve")


def script_of(status: Any) -> Script:
    return Script.model_validate(status.gate.payload["script"])


def test_approved_plan_leads_to_an_episode_1_script_at_gate_3(
    make_app: Callable[..., App], network: FakeNetwork
) -> None:
    network.override = writer(good_draft)
    app = make_app()

    status = at_gate_3(app)

    assert (status.gate.gate, status.gate.target) == (3, "script:the-speckled-band:ep1:v1")
    script = script_of(status)
    bible = db.bible_versions(app.conn, "the-speckled-band")[-1]
    assert script.episode == 1 and script.bible_version == bible.version == 2
    p = status.gate.payload
    assert p["violations"] == [] and p["revisions"] == 0
    assert 0 < p["predicted_seconds"] <= screenplay.MAX_SECONDS
    planned = {cid for b in recorded_plan(network)["episodes"][0]["beats"] for cid in b["clue_ids"]}
    assert {s.clue_id for s in script.clue_spans} == planned
    assert not any("[" in line.text for line in script.lines), "markers are stripped from spoken text"
    assert [c.kind for c in script.cues] == ["foley", "sting"]
    assert any("[clue:" in line for line in p["markup"])

    done = decide(app, status, "approve")
    assert done.state == "done"
    assert db.scripts(app.conn, "the-speckled-band", "pipeline") == [script]


def _drop_first_clue(d: dict[str, Any]) -> None:
    d["lines"].pop(1)


def _drop_a_keyword(d: dict[str, Any]) -> None:
    line = d["lines"][1]
    head, tail = line["text"].split(" notes the ", 1)
    line["text"] = f"{head} notes the it {tail.split(' ', 1)[1]}"


def _later_clue(network: FakeNetwork) -> str:
    later = recorded_plan(network)["episodes"][1:]
    return str(next(cid for e in later for b in e["beats"] for cid in b["clue_ids"]))


RULES: list[tuple[str, Callable[[dict[str, Any], FakeNetwork], None], str]] = [
    ("word_count", lambda d, _: d["lines"].insert(2, {"speaker": "narrator", "text": "word " * 120}), "cut"),
    ("runtime", lambda d, _: d["lines"].insert(2, {"speaker": "narrator", "text": "word " * 50}), "predicted"),
    ("clue_missing", lambda d, _: _drop_first_clue(d), "is never planted"),
    ("clue_keywords", lambda d, _: _drop_a_keyword(d), "inside its [clue:"),
    (
        "clue_early",
        lambda d, n: d["lines"].insert(2, {"speaker": "narrator", "text": f"[clue:{_later_clue(n)}] soon [/clue]"}),
        "do not plant it here",
    ),
    (
        "clue_unknown",
        lambda d, _: d["lines"].insert(2, {"speaker": "narrator", "text": "[clue:ghost] a ghost [/clue]"}),
        "not in the clue ledger",
    ),
    (
        "name",
        lambda d, _: d["lines"].insert(2, {"speaker": "Inspector Lestrade", "text": "Indeed."}),
        "not a bible character",
    ),
    (
        "unknown_marker",
        lambda d, _: d["lines"].insert(2, {"speaker": "narrator", "text": "[music] Indeed."}),
        "unknown marker",
    ),
    (
        "unclosed_clue",
        lambda d, _: d["lines"].append({"speaker": "narrator", "text": "[clue:x] Indeed."}),
        "never closed",
    ),
    (
        "two_stings",
        lambda d, _: d["lines"].insert(2, {"speaker": "narrator", "text": "[sting] Indeed."}),
        "[sting] markers",
    ),
    (
        "too_much_foley",
        lambda d, _: d["lines"].insert(2, {"speaker": "narrator", "text": "[sfx:a] One [sfx:b] two [sfx:c] three."}),
        "Foley cues",
    ),
]


@pytest.mark.parametrize(("rule", "breaks", "note"), RULES, ids=[r[0] for r in RULES])
def test_each_rule_sends_a_breaking_script_back_with_a_targeted_note_and_passes_when_fixed(
    make_app: Callable[..., App],
    network: FakeNetwork,
    rule: str,
    breaks: Callable[[dict[str, Any], FakeNetwork], None],
    note: str,
) -> None:
    def bad(b: dict[str, Any]) -> dict[str, Any]:
        d = good_draft(b)
        breaks(d, network)
        return d

    network.override = writer(bad, good_draft)
    status = at_gate_3(make_app())

    first, revision = screenplay_calls(network)
    assert revision["messages"][:2] == first["messages"]
    assert note in revision["messages"][-1]["content"], revision["messages"][-1]["content"]
    assert status.gate.payload["violations"] == [] and status.gate.payload["revisions"] == 1


def test_a_speaker_without_a_voice_goes_back(make_app: Callable[..., App], network: FakeNetwork) -> None:
    def unvoiced(b: dict[str, Any]) -> dict[str, Any]:
        silent = [c["name"] for c in b["characters"] if c["name"] not in b["cast"]]
        d = good_draft(b)
        d["lines"].insert(2, {"speaker": silent[0], "text": "Indeed."})
        return d

    network.override = writer(unvoiced, good_draft)
    at_gate_3(make_app())

    assert "has no voice" in screenplay_calls(network)[1]["messages"][-1]["content"]


def test_a_misspelled_name_is_fixed_without_a_revision(make_app: Callable[..., App], network: FakeNetwork) -> None:
    def typos(b: dict[str, Any]) -> dict[str, Any]:
        d = good_draft(b)
        d["lines"][-3]["speaker"] = "Helen Stonr"
        d["lines"][0]["text"] += " Holms looks up."
        return d

    network.override = writer(typos)
    status = at_gate_3(make_app())

    assert len(screenplay_calls(network)) == 1
    p = status.gate.payload
    assert p["violations"] == [] and p["revisions"] == 0
    assert "'Holms' -> 'Holmes'" in p["fixes"] and "speaker 'Helen Stonr' -> 'Helen Stoner'" in p["fixes"]
    script = script_of(status)
    assert "Holmes looks up." in script.lines[0].text and script.lines[-3].speaker == "Helen Stoner"


def test_a_script_still_over_110_seconds_after_2_revisions_reaches_gate_3_flagged(
    make_app: Callable[..., App], network: FakeNetwork
) -> None:
    # Three different over-long drafts: an identical revision request would be answered from the cache.
    def long(take: int) -> Callable[[dict[str, Any]], dict[str, Any]]:
        return lambda b: good_draft(b, words=295) | {"title": f"Take {take}"}

    network.override = writer(long(1), long(2), long(3))
    status = at_gate_3(make_app())

    assert len(screenplay_calls(network)) == 1 + MAX_REVISIONS
    p = status.gate.payload
    assert p["revisions"] == 2
    assert [v["rule"] for v in p["violations"]] == ["runtime"]
    assert p["predicted_seconds"] > screenplay.MAX_SECONDS


def test_gate_3_reject_reruns_the_screenplay_agent_with_the_notes(
    make_app: Callable[..., App], network: FakeNetwork
) -> None:
    network.override = writer(good_draft)
    app = make_app()
    first = at_gate_3(app)

    second = decide(app, first, "reject", NOTES)

    assert second.gate.target == "script:the-speckled-band:ep1:v2"
    [_, rerun] = screenplay_calls(network)
    assert NOTES in rerun["messages"][1]["content"] and len(rerun["messages"]) == 2
