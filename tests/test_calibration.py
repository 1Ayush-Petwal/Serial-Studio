"""Gold-set calibration: blind scoring, thresholds and agreement, then critics that gate."""

from __future__ import annotations

import re
import statistics
from collections.abc import Callable
from typing import Any

import pytest

from serial_studio import calibration, critique, db
from serial_studio.schemas import HUMAN_DIMENSIONS, Calibration, Script, ScriptLine, Story

from .conftest import App, FakeNetwork
from .test_critique import take_draft
from .test_gate_2 import critic_of, panel
from .test_gate_3 import at_gate_3, screenplay_calls, writer

STORY = "the-speckled-band"


def test_threshold_is_the_cut_that_best_separates_good_from_bad() -> None:
    critic = [5.0, 4, 4, 2, 1, 3]
    human = [5.0, 5, 4, 1, 2, 3]
    assert calibration.threshold(critic, human) == 4
    assert calibration.threshold([3.0, 3], [5.0, 1]) == 3, "ties go to the most lenient cut"
    with pytest.raises(ValueError, match="no spread"):
        calibration.threshold([3.0, 3], [3.0, 3])


def test_agreement_is_spearman_and_share_within_one_point() -> None:
    critic = [5.0, 4, 2, 1]
    human = [4.0, 5, 1, 3]
    rho, within = calibration.agreement(critic, human)
    assert rho == round(statistics.correlation(critic, human, method="ranked"), 3)
    assert within == 0.75
    assert calibration.agreement([3.0, 3], [1.0, 5]) == (0.0, 0.0)


def quality(n: int) -> int:
    """Synthetic gold items: item quality 1-5 spelled out in the text for the canned critics."""
    return 1 + n % 5


def script(source_n: int, episode: int) -> Script:
    q = quality(source_n)
    return Script(
        story_id=STORY,
        episode=episode,
        bible_version=None,
        title=f"Episode {episode}",
        blurb="b",
        lines=[
            ScriptLine(speaker="narrator", text=f"Quality {q} prose."),
            ScriptLine(speaker="Helen", text=f"Quality {q}, I say."),
        ],
        clue_spans=[],
        cues=[],
    )


def seed_gold(app: App) -> list[Any]:
    db.save_story(app.conn, Story(id=STORY, title="The Speckled Band", author="A", book_id=1, source_url="u", text="t"))
    n = 0
    for source in ("pipeline", "draft", "baseline"):
        for ep in range(1, 7):
            db.save_script(app.conn, source, script(n, ep))
            n += 1
    refs = [script(n + i, i + 1) for i in range(2)]
    return calibration.build(app.conn, STORY, refs, seed=1)


def test_the_gold_set_is_mixed_shuffled_and_blind(make_app: Callable[..., App]) -> None:
    app = make_app()
    items = seed_gold(app)

    assert len(items) == 20 and [i.position for i in items] == list(range(1, 21))
    sources = [i.source for i in items]
    assert {s: sources.count(s) for s in set(sources)} == {"pipeline": 6, "draft": 6, "baseline": 6, "reference": 2}
    assert sources != sorted(sources), "shuffled, not grouped by source"
    assert calibration.gold(app.conn, STORY) == items

    shown: list[str] = []
    answers = iter(["9", "4"] + ["4"] * 200)  # a bad answer is asked again
    stored = calibration.score(app.conn, STORY, ask=lambda q: next(answers), say=shown.append)

    assert stored == 20 * len(HUMAN_DIMENSIONS)
    text = "\n".join(shown)
    assert not re.search(r"pipeline|draft|baseline|reference", text), "the editor never sees where an item came from"
    assert "a whole number from 1 to 5" in text
    assert calibration.score(app.conn, STORY, ask=lambda q: "1", say=shown.append) == 0, "resumable, nothing left"


def gold_critics(shift: int = 0) -> Callable[[dict[str, Any]], dict[str, Any] | None]:
    """Critics that score an item by the quality written into it (plus `shift`), so they track the editor."""

    def respond(body: dict[str, Any]) -> dict[str, Any] | None:
        role = critic_of(body)
        if role is None or role == "Lead critic":
            return panel(body) if role else None
        q = re.search(r"Quality (\d)", body["messages"][1]["content"])
        s = max(1, min(5, int(q.group(1)) + shift)) if q else 3
        out: dict[str, Any] = {"score": s, "notes": ["ok"]}
        if role == "Character critic":
            out["guesses"] = []
        return panel(body, {role: out})

    return respond


def test_calibration_sets_thresholds_and_agreement_and_reruns_per_prompt_version(
    make_app: Callable[..., App], network: FakeNetwork, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = make_app()
    items = seed_gold(app)
    for item in items:
        q = int(re.findall(r"Quality (\d)", item.script.lines[0].text)[0])
        for d in HUMAN_DIMENSIONS:
            app.conn.execute(
                "INSERT INTO gold_scores (story_id, position, dimension, score) VALUES (%s, %s, %s, %s)",
                (STORY, item.position, d, q),
            )
    network.override = gold_critics()

    cal = calibration.calibrate(app.runner.gateway, app.conn, "cal-1", STORY)

    assert cal.items == 20 and cal.prompt_version == critique.PROMPT_VERSION
    assert set(cal.thresholds) == {"tone", "character", "structure", "ear"}
    assert all(t == 4 for t in cal.thresholds.values()), "critic == editor: the cut is the editor's 'good'"
    assert all(r == 1.0 for r in cal.spearman.values()) and all(w == 1.0 for w in cal.within_one.values())

    # A new critique prompt is re-run on the same gold set and lands beside the old one.
    monkeypatch.setattr(critique, "PROMPT_VERSION", "critique-v2")
    network.override = gold_critics(shift=2)
    again = calibration.calibrate(app.runner.gateway, app.conn, "cal-2", STORY)

    assert [c.prompt_version for c in calibration.history(app.conn)] == ["critique-v1", "critique-v2"]
    assert again.within_one["tone"] < cal.within_one["tone"], "the comparison shows the drift"
    assert calibration.latest(app.conn) == again


def test_after_calibration_a_score_under_the_pass_mark_sends_the_script_back(
    make_app: Callable[..., App], network: FakeNetwork
) -> None:
    app = make_app()
    cal = Calibration(
        story_id=STORY,
        prompt_version="critique-v1",
        items=20,
        thresholds={"tone": 3.0},
        spearman={"tone": 0.8},
        within_one={"tone": 0.9},
    )
    app.conn.execute(
        "INSERT INTO calibrations (story_id, prompt_version, calibration) VALUES (%s, %s, %s::jsonb)",
        (STORY, cal.prompt_version, cal.model_dump_json()),
    )

    def tone(body: dict[str, Any]) -> dict[str, Any] | None:
        if critic_of(body) == "Tone critic":
            low = "Take 0." in body["messages"][1]["content"]
            return panel(body, {"Tone critic": {"score": 2 if low else 4, "notes": ["ok"]}})
        return panel(body)

    network.override = writer({1: take_draft}, critics=tone)
    status = at_gate_3(app)

    first, revision = screenplay_calls(network)
    assert "tone scored 2, under the calibrated pass mark 3 (critic: must fix)" in revision["messages"][-1]["content"]
    assert status.gate.payload["report_card"]["scores"]["tone"] == 4
    drafts = db.scripts(app.conn, STORY, "draft")
    assert drafts and drafts[0].episode == 1 and "Take 0." in drafts[0].lines[2].text, "first takes are kept"
