"""Single-prompt baseline season, at the runner seam, for the A/B test and the gold set."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from serial_studio import baseline, db

from .conftest import App, FakeNetwork
from .test_gate_1 import SPECKLED_BAND
from .test_gate_2 import answer


def is_baseline(body: dict[str, Any]) -> bool:
    return bool(body["messages"][0]["content"] == baseline.SYSTEM)


def baseline_calls(network: FakeNetwork) -> list[dict[str, Any]]:
    return [c for c in network.model_calls() if is_baseline(c)]


def recorded_season(network: FakeNetwork) -> dict[str, Any]:
    row = next(r for r in network.rows if r["kind"] == "model" and is_baseline(r["request"]["body"]))
    season: dict[str, Any] = json.loads(row["response"]["choices"][0]["message"]["content"])
    return season


def test_baseline_stores_a_season_of_scripts_labelled_baseline(make_app: Callable[..., App]) -> None:
    app = make_app()
    run_id = app.runner.baseline(SPECKLED_BAND)

    season = db.scripts(app.conn, "the-speckled-band", "baseline")
    assert 5 <= len(season) <= 7
    assert [s.episode for s in season] == list(range(1, len(season) + 1))
    for s in season:
        assert s.bible_version is None, "the baseline reads no bible"
        assert s.lines and all(line.speaker and line.text for line in s.lines)
        assert "baseline" not in json.dumps(s.model_dump()), "the label must stay out of what a blind judge reads"
    assert db.scripts(app.conn, "the-speckled-band", "pipeline") == []

    [line] = [x for x in db.cost_lines(app.conn, run_id) if x.node == "baseline"]
    assert (line.stage, line.provider, line.cache_hit) == ("text", "gemini", False)


def test_baseline_rerun_is_served_from_the_cache(make_app: Callable[..., App], network: FakeNetwork) -> None:
    app = make_app()
    first = app.runner.baseline(SPECKLED_BAND)
    sent = len(network.requests)

    again = app.runner.baseline(SPECKLED_BAND)

    assert len(network.requests) == sent, "nothing goes to the network on a re-run"
    [line] = [x for x in db.cost_lines(app.conn, again) if x.node == "baseline"]
    assert line.cache_hit and again != first
    assert len(db.scripts(app.conn, "the-speckled-band", "baseline")) >= 5


def test_malformed_baseline_json_goes_back_with_the_errors(make_app: Callable[..., App], network: FakeNetwork) -> None:
    good = recorded_season(network)
    bad = {"episodes": good["episodes"][:2]}
    answers = [bad, good]
    network.override = lambda body: answer(answers.pop(0)) if is_baseline(body) else None

    make_app().runner.baseline(SPECKLED_BAND)

    first, repair = baseline_calls(network)
    assert repair["messages"][:2] == first["messages"]
    assert "episodes" in repair["messages"][-1]["content"]
