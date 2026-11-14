"""Gold-set calibration: critic thresholds and critic-human agreement (decision 26).

The editor scores a blind, shuffled gold set; each critic's pass threshold is the cut on its
score that best separates the editor's >= 4 from <= 2, and agreement is Spearman plus the share
of items within one point.
"""

from __future__ import annotations

import random
import statistics
from collections.abc import Callable
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from serial_studio import critique, db
from serial_studio.gateway import Gateway
from serial_studio.schemas import (
    HUMAN_DIMENSIONS,
    Bible,
    Calibration,
    CritiqueInput,
    CritiqueNote,
    CritiqueNotes,
    GoldItem,
    Script,
    ScriptSource,
)

HIGH, LOW = 4, 2  # the editor's "good" and "bad"; 3 is left out of the threshold fit
PER_SOURCE = 6  # 6 finals, 6 first drafts, 6 baseline, plus the references (decision 26)
CRITICS = ("tone", "character", "structure", "ear")  # critics with a human dimension of the same name


def threshold(critic: list[float], human: list[float]) -> float:
    """The critic score t that best separates human >= HIGH (critic >= t) from human <= LOW (critic < t).

    Ties go to the lowest t: the most lenient cut that is as accurate as any stricter one.
    """
    pairs = [(c, h) for c, h in zip(critic, human, strict=True) if h >= HIGH or h <= LOW]
    if not pairs:
        raise ValueError("no gold items scored >= 4 or <= 2; the gold set has no spread to calibrate on")
    best_t, best_right = 0.0, -1
    for t in sorted({c for c, _ in pairs}):
        right = sum((c >= t) == (h >= HIGH) for c, h in pairs)
        if right > best_right:
            best_t, best_right = t, right
    return best_t


def agreement(critic: list[float], human: list[float]) -> tuple[float, float]:
    """(Spearman rank correlation, share of items where critic and editor are within one point)."""
    flat = len(set(critic)) < 2 or len(set(human)) < 2  # a constant series has no rank order to agree with
    rho = 0.0 if flat else statistics.correlation(critic, human, method="ranked")
    within = sum(abs(c - h) <= 1 for c, h in zip(critic, human, strict=True)) / len(critic)
    return round(rho, 3), round(within, 3)


# --- the gold set ---


def build(conn: psycopg.Connection[Any], story_id: str, references: list[Script], seed: int = 0) -> list[GoldItem]:
    """Gather finals, first drafts and baseline episodes plus the editor's references, shuffled."""
    items: list[tuple[ScriptSource, Script]] = []
    for source in ("pipeline", "draft", "baseline"):
        items += [(source, sc) for sc in db.scripts(conn, story_id, source)[:PER_SOURCE]]
    for ref in references:
        db.save_script(conn, "reference", ref)
        items.append(("reference", ref))
    random.Random(seed).shuffle(items)
    gold = [GoldItem(position=i, source=src, episode=sc.episode, script=sc) for i, (src, sc) in enumerate(items, 1)]
    with conn.transaction():
        conn.execute("DELETE FROM gold WHERE story_id = %s", (story_id,))
        conn.execute("DELETE FROM gold_scores WHERE story_id = %s", (story_id,))
        for g in gold:
            conn.execute(
                "INSERT INTO gold (story_id, position, item) VALUES (%s, %s, %s)",
                (story_id, g.position, Jsonb(g.model_dump())),
            )
    return gold


def gold(conn: psycopg.Connection[Any], story_id: str) -> list[GoldItem]:
    rows = conn.execute("SELECT item FROM gold WHERE story_id = %s ORDER BY position", (story_id,))
    return [GoldItem.model_validate(r["item"]) for r in rows]


def human_scores(conn: psycopg.Connection[Any], story_id: str) -> dict[tuple[int, str], int]:
    rows = conn.execute("SELECT position, dimension, score FROM gold_scores WHERE story_id = %s", (story_id,))
    return {(r["position"], r["dimension"]): r["score"] for r in rows}


def blind(item: GoldItem) -> str:
    """The item as the editor reads it: position, title and lines; nothing about where it came from."""
    lines = "\n".join(f"  {line.speaker}: {line.text}" for line in item.script.lines)
    return f"ITEM {item.position}: {item.script.title}\n{lines}"


def score(conn: psycopg.Connection[Any], story_id: str, ask: Callable[[str], str], say: Callable[[str], None]) -> int:
    """Ask for every missing (item, dimension) score, 1-5; resumable. Returns how many were stored."""
    have = human_scores(conn, story_id)
    stored = 0
    for item in gold(conn, story_id):
        todo = [d for d in HUMAN_DIMENSIONS if (item.position, d) not in have]
        if not todo:
            continue
        say(blind(item))
        for d in todo:
            while (answer := ask(f"{d} 1-5: ").strip()) not in {"1", "2", "3", "4", "5"}:
                say("  a whole number from 1 to 5")
            conn.execute(
                "INSERT INTO gold_scores (story_id, position, dimension, score) VALUES (%s, %s, %s, %s)",
                (story_id, item.position, d, int(answer)),
            )
            stored += 1
    return stored


# --- calibration ---


def critic_scores(
    gateway: Gateway, conn: psycopg.Connection[Any], run_id: str, story_id: str
) -> dict[int, CritiqueNotes]:
    """The panel on every gold item, under the current critique prompt (cached like any model call)."""
    story = db.story(conn, story_id)
    versions = db.bible_versions(conn, story_id)
    bible = versions[-1] if versions else Bible(story_id=story_id)
    plan = db.plan(conn, story_id)
    out: dict[int, CritiqueNotes] = {}
    for item in gold(conn, story_id):
        beats = plan.episodes[min(item.episode, len(plan.episodes)) - 1].beats if plan else []
        cast = [c.name for c in bible.characters if c.voice_id is not None]
        inp = CritiqueInput(episode=item.episode, title=story.title, script=item.script, beats=beats, cast=cast)
        out[item.position] = critique.critique(gateway, run_id, inp)
    return out


def calibrate(gateway: Gateway, conn: psycopg.Connection[Any], run_id: str, story_id: str) -> Calibration:
    """Thresholds and agreement per critic from the editor's gold scores; saved, newest wins."""
    human = human_scores(conn, story_id)
    panel = critic_scores(gateway, conn, run_id, story_id)
    thresholds: dict[str, float] = {}
    spearman: dict[str, float] = {}
    within: dict[str, float] = {}
    for c in CRITICS:
        scored = [p for p in sorted(panel) if (p, c) in human and c in panel[p].scores]
        if not scored:
            raise ValueError(f"no gold items have both an editor and a {c} critic score")
        crit = [panel[p].scores[c] for p in scored]
        hum = [float(human[(p, c)]) for p in scored]
        thresholds[c] = threshold(crit, hum)
        spearman[c], within[c] = agreement(crit, hum)
    cal = Calibration(
        story_id=story_id,
        prompt_version=critique.PROMPT_VERSION,
        items=len(panel),
        thresholds=thresholds,
        spearman=spearman,
        within_one=within,
    )
    conn.execute(
        "INSERT INTO calibrations (story_id, prompt_version, calibration) VALUES (%s, %s, %s)",
        (story_id, cal.prompt_version, Jsonb(cal.model_dump())),
    )
    return cal


def history(conn: psycopg.Connection[Any]) -> list[Calibration]:
    """Every calibration, oldest first: compare prompt versions on the same gold set."""
    rows = conn.execute("SELECT calibration FROM calibrations ORDER BY id")
    return [Calibration.model_validate(r["calibration"]) for r in rows]


def latest(conn: psycopg.Connection[Any]) -> Calibration | None:
    cals = history(conn)
    return cals[-1] if cals else None


def gate(notes: CritiqueNotes, cal: Calibration | None) -> CritiqueNotes:
    """Once calibrated, a critic score under its pass mark is a must-fix note."""
    if cal is None:
        return notes
    under = [
        CritiqueNote(
            critic=c,  # type: ignore[arg-type]
            note=f"{c} scored {notes.scores[c]:g}, under the calibrated pass mark {t:g}",
            must_fix=True,
            rank=0,
        )
        for c, t in cal.thresholds.items()
        if c in notes.scores and notes.scores[c] < t
    ]
    return notes.model_copy(update={"notes": under + notes.notes})
