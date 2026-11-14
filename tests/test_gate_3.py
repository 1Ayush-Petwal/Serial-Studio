"""Gate 2 -> Screenplay agent -> validators and revise loop -> gate 3, at the graph-runner seam.

Writer answers are canned per test (built from the episode brief the agent sends), so every
validator rule gets a failing and a passing case without a model call.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from typing import Any

import pytest

from serial_studio import db, screenplay, story_architect
from serial_studio.schemas import Script
from serial_studio.screenplay import MAX_REVISIONS

from .conftest import App, FakeNetwork
from .test_gate_2 import answer, at_gate_2, critic_of, decide, is_screenplay, panel, recorded_plan

FILLER = "The fog lay thick on Baker Street and the lamps burned low while the clock ticked on."
NOTES = "Open on the knock at the bedroom door."


def brief(body: dict[str, Any]) -> dict[str, Any]:
    user = body["messages"][1]["content"]
    out: dict[str, Any] = json.loads(user.split("Episode brief:\n", 1)[1].split("\n", 1)[0])
    return out


def good_draft(b: dict[str, Any], words: int = 250) -> dict[str, Any]:
    """A script that passes every rule: recap and seam, each planned clue with its keywords, cast speakers."""
    cast = b["cast"]
    prev = b["previous_cliffhanger"]
    opening = (
        f"{b['recap']} Then came the {' '.join(prev['keywords'])}."
        if prev
        else "[bed:rain] A knock at dawn, and a veiled woman trembling at the door."
    )
    lines = [{"speaker": "narrator", "text": opening}]
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
    end = b["cliffhanger"]
    closing = f"[sting] Then, in the dark: {' '.join(end['keywords'])}." if end else "[sting] And so it ended."
    lines.append({"speaker": "narrator", "text": closing})
    return {"title": b["title"], "blurb": "A frightened client brings Holmes a deadly puzzle.", "lines": lines}


# (episode brief, take) -> writer answer, or None to replay the recorded one
Make = Callable[[dict[str, Any], int], dict[str, Any] | None]


def good(b: dict[str, Any], take: int) -> dict[str, Any]:
    return good_draft(b)


def then_good(bad: Callable[[dict[str, Any]], dict[str, Any]]) -> Make:
    return lambda b, take: bad(b) if take == 0 else good_draft(b)


def record_answer(body: dict[str, Any]) -> dict[str, Any]:
    """The Story Architect's record of an approved script: it ended where the plan said."""
    user = body["messages"][1]["content"]
    plan = json.loads(user.split("Plan:\n", 1)[1].split("\n", 1)[0])
    return {"ending": plan["cliffhanger"], "established": ["Holmes has taken the case."], "differs_from_plan": []}


def is_record(body: dict[str, Any]) -> bool:
    return bool(body["messages"][0]["content"] == story_architect.RECORD_SYSTEM)


def writer(
    drafts: dict[int, Make] | None = None,
    record: Callable[[dict[str, Any]], dict[str, Any]] = record_answer,
    critics: Callable[[dict[str, Any]], dict[str, Any] | None] = panel,
) -> Callable[[dict[str, Any]], dict[str, Any] | None]:
    """Answer each episode's screenplay calls by take, and the Story Architect's records; the rest replays.

    Episodes draft in parallel, so answers are keyed by episode, never by call order.
    """
    takes: dict[int, int] = {}
    lock = threading.Lock()

    def respond(body: dict[str, Any]) -> dict[str, Any] | None:
        if is_record(body):
            return answer(record(body))
        if critic_of(body):
            return critics(body)
        if not is_screenplay(body):
            return None
        b = brief(body)
        with lock:
            take = takes.get(b["episode"], 0)
            takes[b["episode"]] = take + 1
        out = (drafts or {}).get(b["episode"], good)(b, take)
        return None if out is None else answer(out)

    return respond


def screenplay_calls(network: FakeNetwork, episode: int = 1) -> list[dict[str, Any]]:
    return [c for c in network.model_calls() if is_screenplay(c) and brief(c)["episode"] == episode]


def at_gate_3(app: App) -> Any:
    return decide(app, at_gate_2(app), "approve")


def script_of(status: Any) -> Script:
    return Script.model_validate(status.gate.payload["script"])


def test_approved_plan_leads_to_an_episode_1_script_at_gate_3(
    make_app: Callable[..., App], network: FakeNetwork
) -> None:
    network.override = writer()
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

    after = decide(app, status, "approve")
    assert after.gate.target == "script:the-speckled-band:ep2:v1"
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

    network.override = writer({1: then_good(bad)})
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

    network.override = writer({1: then_good(unvoiced)})
    at_gate_3(make_app())

    assert "has no voice" in screenplay_calls(network)[1]["messages"][-1]["content"]


def test_a_misspelled_name_is_fixed_without_a_revision(make_app: Callable[..., App], network: FakeNetwork) -> None:
    def typos(b: dict[str, Any]) -> dict[str, Any]:
        d = good_draft(b)
        d["lines"][-3]["speaker"] = "Helen Stonr"
        d["lines"][0]["text"] += " Holms looks up."
        return d

    network.override = writer({1: lambda b, take: typos(b)})
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
    # Each take differs: an identical revision request would be answered from the cache.
    network.override = writer({1: lambda b, take: good_draft(b, words=295) | {"title": f"Take {take}"}})
    status = at_gate_3(make_app())

    assert len(screenplay_calls(network)) == 1 + MAX_REVISIONS
    p = status.gate.payload
    assert p["revisions"] == 2
    assert [v["rule"] for v in p["violations"]] == ["runtime"]
    assert p["predicted_seconds"] > screenplay.MAX_SECONDS


def test_gate_3_reject_reruns_the_screenplay_agent_with_the_notes(
    make_app: Callable[..., App], network: FakeNetwork
) -> None:
    network.override = writer()
    app = make_app()
    first = at_gate_3(app)

    second = decide(app, first, "reject", NOTES)

    assert second.gate.target == "script:the-speckled-band:ep1:v2"
    [_, rerun] = screenplay_calls(network)
    assert NOTES in rerun["messages"][1]["content"] and len(rerun["messages"]) == 2


def test_a_writer_that_never_returns_a_parseable_script_fails_loudly(
    make_app: Callable[..., App], network: FakeNetwork
) -> None:
    network.override = writer({1: lambda b, take: {"title": "Take", "blurb": str(take), "lines": []}})

    with pytest.raises(ValueError, match="unparseable"):
        at_gate_3(make_app())
    assert len(screenplay_calls(network)) == 1 + MAX_REVISIONS


def test_punctuation_after_a_marker_stays_on_its_word(make_app: Callable[..., App], network: FakeNetwork) -> None:
    def tight(b: dict[str, Any]) -> dict[str, Any]:
        d = good_draft(b)
        c = b["clues_to_plant"][0]
        d["lines"][1]["text"] = f"Holmes notes the [clue:{c['id']}]{' '.join(c['keywords'])}[/clue]."
        return d

    network.override = writer({1: lambda b, take: tight(b)})
    status = at_gate_3(make_app())

    line = script_of(status).lines[1].text
    assert line.endswith(".") and " ." not in line
    span = script_of(status).clue_spans[0]
    assert span.end - span.start == len(b_keywords(network))


def b_keywords(network: FakeNetwork) -> list[str]:
    first = brief(screenplay_calls(network)[0])["clues_to_plant"][0]
    return " ".join(first["keywords"]).split()


def test_the_recorded_writer_answer_reaches_gate_3_clean(make_app: Callable[..., App], network: FakeNetwork) -> None:
    """A real Gemini episode 1 (replayed): it passes the validators, at most after one revision."""
    network.override = writer({1: lambda b, take: None})  # episode 1 replays; the others are canned
    app = make_app()
    status = at_gate_3(app)

    p = status.gate.payload
    assert p["violations"] == [] and p["revisions"] <= 1
    assert p["predicted_seconds"] <= screenplay.MAX_SECONDS
    script = script_of(status)
    assert {s.clue_id for s in script.clue_spans} == {
        cid for b in recorded_plan(network)["episodes"][0]["beats"] for cid in b["clue_ids"]
    }
    assert [line.speaker for line in script.lines if line.speaker != "narrator"]
