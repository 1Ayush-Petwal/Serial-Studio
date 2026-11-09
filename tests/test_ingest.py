"""Demo stories cut from Gutenberg anthologies, duplicates linked as lineage, each to gate 1."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from serial_studio import db
from serial_studio.schemas import Bible, StartRun

from .conftest import App

# (story, anthology, opening words, closing words, title of the story that follows it in the book)
DEMO = [
    (
        StartRun(title="The Speckled Band", book_id=1661),
        "On glancing over my notes of the seventy odd cases",
        "likely to weigh very heavily upon my conscience.”",
        "ENGINEER",
    ),
    (
        StartRun(title="The Red-Headed League", book_id=1661),
        "I had called upon my friend, Mr. Sherlock Holmes, one day in the autumn",
        "as Gustave Flaubert wrote to George Sand.”",
        "A CASE OF IDENTITY",
    ),
    (
        # 834 itself drops the opening quote mark of the first line.
        StartRun(title="Silver Blaze", book_id=834),
        "I am afraid, Watson, that I shall have to go,” said Holmes",
        "any other details which might interest you.”",
        "Cardboard Box",
    ),
]


@pytest.mark.parametrize(("start", "opening", "closing", "next_story"), DEMO, ids=lambda x: getattr(x, "title", ""))
def test_demo_story_is_cut_from_its_anthology_and_reaches_gate_1(
    make_app: Callable[..., App], start: StartRun, opening: str, closing: str, next_story: str
) -> None:
    app = make_app()
    status = app.runner.start(start)

    story = db.story(app.conn, status.gate.payload["bible"]["story_id"])
    assert story.text.startswith(opening)
    assert story.text.endswith(closing)
    assert next_story.lower() not in story.text.lower()
    assert status.state == "paused" and status.gate.gate == 1
    bible = Bible.model_validate(status.gate.payload["bible"])
    assert bible.characters and bible.clues


@pytest.mark.parametrize("start", [d[0] for d in DEMO[:2]], ids=lambda s: s.title)
def test_duplicate_copy_is_linked_as_lineage_and_the_cleanest_is_canonical(
    make_app: Callable[..., App], start: StartRun
) -> None:
    app = make_app()
    status = app.runner.start(start)
    story = db.story(app.conn, status.gate.payload["bible"]["story_id"])

    # 1661 (plain text) and 48320 (illustrated edition) are two Gutenberg books holding the story.
    assert [c.book_id for c in story.lineage] == [1661, 48320]
    assert all(c.similarity >= 0.8 for c in story.lineage)
    assert story.lineage[0].noise < story.lineage[1].noise, "[Illustration] blocks make 48320 noisier"
    assert (story.book_id, story.source_url) == (story.lineage[0].book_id, story.lineage[0].source_url)
    # Audiobook releases of the same anthology list only a readme, so they never become copies.
    assert not {28733, 9551, 8624} & {c.book_id for c in story.lineage}


def test_canonical_choice_is_deterministic(make_app: Callable[..., App]) -> None:
    app = make_app()
    start = DEMO[0][0]
    first = db.story(app.conn, app.runner.start(start).gate.payload["bible"]["story_id"])

    again = db.story(app.conn, app.runner.start(start).gate.payload["bible"]["story_id"])

    assert again.lineage == first.lineage
    assert again.text == first.text


def test_silver_blaze_has_no_second_plain_text_copy(make_app: Callable[..., App]) -> None:
    """Gutenberg holds Silver Blaze only in 834; 9555 is an audiobook with a readme."""
    app = make_app()
    app.runner.start(DEMO[2][0])

    story = db.story(app.conn, "silver-blaze")
    assert [c.book_id for c in story.lineage] == [834]


def test_silver_blaze_ledger_has_the_dog_that_did_not_bark(make_app: Callable[..., App]) -> None:
    app = make_app()
    status = app.runner.start(DEMO[2][0])

    bible = Bible.model_validate(status.gate.payload["bible"])
    dog = [c for c in bible.clues if c.kind == "absence" and any("dog" in k for k in c.keywords)]
    assert dog, [(c.id, c.kind, c.keywords) for c in bible.clues]
    assert 2 <= len(dog[0].keywords) <= 4
