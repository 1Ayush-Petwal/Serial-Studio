"""Critique panel inside the revise loop, at the graph-runner seam with replayed judge answers.

The crew runs once per episode in parallel, so canned answers are keyed by what each prompt says:
the tone critic tags its note with the episode and take it read, and the lead critic sees that tag
in its context.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

import pytest

from serial_studio.screenplay import MAX_REVISIONS

from .conftest import App, FakeNetwork
from .test_gate_2 import critic_of, panel
from .test_gate_3 import at_gate_3, good_draft, screenplay_calls, writer

VISUAL = "Line 3 relies on a visual cue."
MODERN = "A touch modern in places."


def take_draft(b: dict[str, Any], take: int) -> dict[str, Any]:
    d = good_draft(b)
    d["lines"].insert(2, {"speaker": "narrator", "text": f"Take {take}."})
    return d


def panel_for(must_fix_on: set[str], scores: int = 4) -> Callable[[dict[str, Any]], dict[str, Any] | None]:
    """Critics that score `scores` and, for the drafts tagged in `must_fix_on`, flag one must-fix note."""

    def respond(body: dict[str, Any]) -> dict[str, Any] | None:
        role = critic_of(body)
        user = body["messages"][1]["content"]
        if role == "Tone critic":
            ep = re.search(r"Episode (\d+) script", user)
            take = re.search(r"Take (\d+)\.", user)
            tag = f"ep{ep.group(1) if ep else '?'} take{take.group(1) if take else 0}"
            return panel(body, {role: {"score": scores, "notes": [tag]}})
        if role == "Character critic":
            cast = user.split("Cast: ", 1)[1].split("\n", 1)[0].split(", ")
            # good_draft gives the train line to the first cast member and the reply to the last.
            guesses = [
                {"line": int(n), "speaker": cast[0] if "train" in text else cast[-1]}
                for n, text in re.findall(r"^(\d+)\. (.*)$", user, re.M)
            ]
            return panel(body, {role: {"score": scores, "notes": ["Distinct."], "guesses": guesses}})
        if role == "Lead critic":
            must = any(tag in user for tag in must_fix_on)
            notes = [
                {"critic": "ear", "note": VISUAL, "must_fix": must, "rank": 1},
                {"critic": "tone", "note": MODERN, "must_fix": False, "rank": 2},
            ]
            return panel(body, {role: {"notes": notes}})
        return panel(body, {role: {"score": scores, "notes": ["Fine."]}}) if role else None

    return respond


def test_a_must_fix_note_sends_the_script_back_and_the_report_card_says_why(
    make_app: Callable[..., App], network: FakeNetwork
) -> None:
    network.override = writer({1: take_draft}, critics=panel_for({"ep1 take0"}))
    status = at_gate_3(make_app())

    first, revision = screenplay_calls(network)
    feedback = revision["messages"][-1]["content"]
    assert f"{VISUAL} (critic: must fix)" in feedback
    assert MODERN not in feedback, "only must-fix notes go back to the writer"
    card = status.gate.payload["report_card"]
    assert card["revisions"] == [f"revision 1: {VISUAL} (critic: must fix)"]
    assert card["scores"] == {"tone": 4, "character": 4, "structure": 4, "ear": 4, "speaker_accuracy": 1.0}


def test_notes_that_are_not_must_fix_do_not_send_the_script_back(
    make_app: Callable[..., App], network: FakeNetwork
) -> None:
    network.override = writer({1: take_draft}, critics=panel_for(set()))
    status = at_gate_3(make_app())

    assert len(screenplay_calls(network)) == 1
    p = status.gate.payload
    assert p["report_card"]["revisions"] == []
    assert [n["note"] for n in p["critique"]["notes"]] == [VISUAL, MODERN]


def test_low_scores_never_block_a_script_while_the_critics_are_uncalibrated(
    make_app: Callable[..., App], network: FakeNetwork
) -> None:
    network.override = writer({1: take_draft}, critics=panel_for(set(), scores=1))
    status = at_gate_3(make_app())

    assert len(screenplay_calls(network)) == 1
    assert status.gate.payload["report_card"]["scores"]["tone"] == 1
    assert status.gate.payload["violations"] == []


def test_validators_and_critics_share_one_budget_of_2_revisions(
    make_app: Callable[..., App], network: FakeNetwork
) -> None:
    def clue_missing_then_fine(b: dict[str, Any], take: int) -> dict[str, Any]:
        d = take_draft(b, take)
        if take == 0:
            d["lines"].pop(1)
        return d

    # Take 0 breaks a validator; takes 1 and 2 pass them but the lead critic flags each.
    network.override = writer({1: clue_missing_then_fine}, critics=panel_for({"ep1 take1", "ep1 take2"}))
    status = at_gate_3(make_app())

    assert len(screenplay_calls(network)) == 1 + MAX_REVISIONS
    card = status.gate.payload["report_card"]
    assert len(card["revisions"]) == MAX_REVISIONS
    assert "is never planted" in card["revisions"][0] and VISUAL in card["revisions"][1]
    assert status.gate.payload["critique"]["notes"][0]["must_fix"], "the unfixed note still shows at gate 3"


def test_the_character_critic_reads_the_lines_without_speaker_names(
    make_app: Callable[..., App], network: FakeNetwork
) -> None:
    network.override = writer({1: take_draft}, critics=panel_for(set()))
    at_gate_3(make_app())

    prompts = [c["messages"][1]["content"] for c in network.model_calls() if critic_of(c) == "Character critic"]
    assert prompts
    blind = prompts[0].split("speaker removed:\n", 1)[1]
    assert "Helen Stoner:" not in blind and "Sherlock Holmes:" not in blind
    assert "You have come in by train this morning" in blind


def test_malformed_crew_output_fails_loudly(make_app: Callable[..., App], network: FakeNetwork) -> None:
    def broken(body: dict[str, Any]) -> dict[str, Any] | None:
        if critic_of(body) == "Ear critic":
            return panel(body, {"Ear critic": {"score": 9, "notes": []}})
        return panel(body)

    network.override = writer({1: take_draft}, critics=broken)
    with pytest.raises(ValueError, match="critique panel returned malformed output"):
        at_gate_3(make_app())
