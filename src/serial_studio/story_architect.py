"""Story Architect: scene-by-scene extraction of the bible and clue ledger.

Each call gets one scene plus the current bible and returns a BibleDelta.
Code merges and dedupes; the model never writes the bible directly.
"""

from __future__ import annotations

import json
import re

from serial_studio.gateway import Gateway, role_model, strict_schema
from serial_studio.schemas import (
    ArchitectInput,
    BeatSheet,
    Bible,
    BibleDelta,
    Character,
    Cliffhanger,
    Clue,
    EpisodeRecord,
    EpisodeRecordDraft,
    Message,
    ModelRequest,
    OpenThread,
    Scene,
    Script,
    SeasonPlan,
    SourcePosition,
)

PROMPT_VERSION = "story-architect-v4"

SYSTEM = """You are the Story Architect for an audio adaptation of a mystery short story.
You read the story one scene at a time and record what this scene adds to the story bible.
Everything later in the pipeline is checked against your bible, so be exact and never invent.

Return only what THIS scene adds or changes:
- characters: canonical full name; aliases = every other name or title the text uses for them
  ("Dr. Roylott", "Miss Stoner"), never pronouns or relations like "my stepfather";
  description = who they are as of this scene, never what happens to them later;
  facts = short statements about them established in this scene.
  To add to an existing character, repeat their canonical name exactly.
- places: named locations, one-line description.
- facts: story-world facts not tied to one character (dates, money, layout of a house).
- pronunciations: proper names a text-to-speech voice could misread, respelled with the stressed
  syllable in capitals (e.g. "Roylott" -> "ROY-lot").
- clues: details the solution depends on, which a listener must hear for the mystery to play fair:
  physical evidence, sounds, odd behaviour, telling objects, and absences (something that should have
  happened but did not; kind="absence"). Skip atmosphere that the solution does not need.
  Record a clue in the scene where the listener first meets the detail, even when its meaning is only
  explained later; a scene that explains the solution normally cites clues already recorded, so any
  detail it cites that is not yet in the bible was missed earlier and must be added now.
  Each distinct sound, object, mark or utterance is its own clue: two sounds in one sentence are two
  clues. A victim's last or dying words are always a clue. Anything the detective examines, picks up,
  taps, measures or asks a pointed question about is a clue, however trivial it looks; so is any
  object noticed while a room is searched, even if nobody comments on it.
  Before answering, re-read the scene for every sound, object, mark and quoted last words, and check
  each against the rules above.
  id: short snake_case, stable; reuse an existing id only if this scene adds nothing new to it, so
  normally omit clues already in the bible.
  quote: copy 5-25 consecutive words character for character from the scene text, never a paraphrase.
  keywords: 2-4 lowercase words the listener must hear for the clue to land; prefer words in the quote;
  for an absence clue, words that encode the absence (e.g. "dog", "did not bark").
- opened_threads: questions this scene leaves the listener asking (id snake_case).
- closed_threads: ids of existing open threads this scene answers.
Use empty lists when the scene adds nothing to a field."""


DELTA_SCHEMA = strict_schema(BibleDelta)


def user_prompt(inp: ArchitectInput, scene_count: int) -> str:
    # Only what the model needs to avoid repeating itself; facts and descriptions are deduped in
    # merge(). Keeps the request under Groq's free-tier 8K TPM (input + max_completion_tokens).
    b = inp.bible
    known = {
        "characters": [{"name": c.name, "aliases": c.aliases} for c in b.characters],
        "places": [p.name for p in b.places],
        "pronunciations": [p.term for p in b.pronunciations],
        "clues": [{"id": c.id, "text": c.text} for c in b.clues],
        "open_threads": [{"id": t.id, "question": t.question} for t in b.open_threads if not t.closed],
    }
    notes = f"\nEditor notes from the last review; apply them:\n{inp.notes}\n" if inp.notes else ""
    return (
        f"Scene {inp.scene.index + 1} of {scene_count}.\n"
        f"Already in the bible:\n{json.dumps(known, ensure_ascii=False)}\n{notes}\n"
        f"Scene text:\n<<<\n{inp.scene.text}\n>>>"
    )


def extract(gateway: Gateway, run_id: str, inp: ArchitectInput, scene_count: int) -> BibleDelta:
    response = gateway.complete(
        ModelRequest(
            run_id=run_id,
            stage="judge",
            node="story_architect",
            model=role_model("judge"),
            messages=[
                Message(role="system", content=SYSTEM),
                Message(role="user", content=user_prompt(inp, scene_count)),
            ],
            # ponytail: low reasoning keeps input + output cap under Groq free-tier 8K TPM and the
            # 200K/day budget; raise it (and the cap) on a paid tier if clue recall suffers.
            params={"temperature": 0, "max_completion_tokens": 4000, "reasoning_effort": "low"},
            prompt_version=PROMPT_VERSION,
            response_schema=DELTA_SCHEMA,
        )
    )
    return BibleDelta.model_validate_json(response.text)  # malformed output fails loudly


# --- merge (code, not model) ---


def _norm(s: str) -> str:
    return re.sub(r"\W+", " ", s.lower()).strip()


def _union(old: list[str], new: list[str], exclude: str = "") -> list[str]:
    seen = {_norm(x) for x in old} | {_norm(exclude)}
    out = list(old)
    for x in new:
        if _norm(x) not in seen:
            seen.add(_norm(x))
            out.append(x)
    return out


def find_quote(quote: str, text: str) -> re.Match[str] | None:
    """First match of the quote's words in text, tolerant of quote marks and punctuation."""
    words = re.findall(r"\w+", quote)
    return re.search(r"\W+".join(map(re.escape, words)), text, re.I) if words else None


def locate(quote: str, scene: Scene) -> SourcePosition:
    """Offset of the quote in the story."""
    m = find_quote(quote, scene.text)
    if m is None:
        return SourcePosition(scene=scene.index, offset=scene.start, quote=quote, exact=False)
    return SourcePosition(scene=scene.index, offset=scene.start + m.start(), quote=m.group(), exact=True)


def merge(bible: Bible, delta: BibleDelta, scene: Scene) -> Bible:
    b = bible.model_copy(deep=True)

    for c in delta.characters:
        names = {_norm(c.name), *map(_norm, c.aliases)}
        match = next((x for x in b.characters if names & {_norm(x.name), *map(_norm, x.aliases)}), None)
        if match is None:
            b.characters.append(Character(**c.model_dump()))
        else:
            match.aliases = _union(match.aliases, [c.name, *c.aliases], exclude=match.name)
            match.facts = _union(match.facts, c.facts)
            match.description = match.description or c.description

    for p in delta.places:
        place = next((x for x in b.places if _norm(x.name) == _norm(p.name)), None)
        if place is None:
            b.places.append(p)
        elif not place.description:
            place.description = p.description

    b.facts = _union(b.facts, delta.facts)
    terms = {_norm(p.term) for p in b.pronunciations}
    for pr in delta.pronunciations:
        if _norm(pr.term) not in terms:
            terms.add(_norm(pr.term))
            b.pronunciations.append(pr)

    # First appearance wins: that is where the listener first hears the clue.
    known = {c.id for c in b.clues} | {_norm(c.text) for c in b.clues}
    for d in delta.clues:
        if d.id in known or _norm(d.text) in known:
            continue
        known |= {d.id, _norm(d.text)}
        b.clues.append(
            Clue(
                id=d.id,
                text=d.text,
                kind=d.kind,
                keywords=list(dict.fromkeys(d.keywords))[:4],
                position=locate(d.quote, scene),
            )
        )

    thread_ids = {t.id for t in b.open_threads}
    for t in delta.opened_threads:
        if t.id not in thread_ids:
            thread_ids.add(t.id)
            b.open_threads.append(OpenThread(**t.model_dump()))
    for t in b.open_threads:
        if t.id in delta.closed_threads:
            t.closed = True
    return b


PLACEHOLDER = re.compile(r"^(unnamed|unknown|the)\b", re.I)


def finalize(bible: Bible) -> Bible:
    """Promote a real name over a placeholder ("Unnamed Lady") once the story has named them.

    Done at save time, not per scene, so it never changes what the model is shown.
    """
    b = bible.model_copy(deep=True)
    for c in b.characters:
        if not PLACEHOLDER.match(c.name):
            continue
        real = next((a for a in c.aliases if not PLACEHOLDER.match(a) and all(w[0].isupper() for w in a.split())), None)
        if real:
            c.aliases = _union([c.name], [a for a in c.aliases if a != real], exclude=real)
            c.name = real
    return b


def cast(bible: Bible, plan: SeasonPlan) -> Bible:
    """Write the approved season plan's decisions into the bible: voices and clue episodes."""
    b = bible.model_copy(deep=True)
    b.narrator_voice_id = plan.casting["narrator"]
    for c in b.characters:
        c.voice_id = plan.casting.get(c.name)
    clues = {c.id: c for c in b.clues}
    for e in plan.episodes:
        for cid in (cid for beat in e.beats for cid in beat.clue_ids):
            clues[cid].assigned_episode = e.episode
        for cid in e.reveals:
            clues[cid].reveal_episode = e.episode
    return b


# --- reconciliation after each approved script (gate 3) ---

RECORD_SYSTEM = """You are the Story Architect for an audio serial adapted from a mystery short story.
An editor has just approved this episode's script. Record what it established, for the writers of
the episodes after it:
- ending: the concrete event the episode ends on, as the listener hears it, with 2-4 lowercase
  keywords copied from the script's closing lines; null for the last episode.
- established: short statements of what the listener now knows.
- differs_from_plan: each way the script departs from the planned beat sheet (a clue moved, a
  secret told early, a different ending); empty if none."""

RECORD_SCHEMA = strict_schema(EpisodeRecordDraft)
CLOSING_WORDS = 60  # where the ending's keywords must be found


def record(gateway: Gateway, run_id: str, script: Script, sheet: BeatSheet, last: bool) -> EpisodeRecord:
    plan = {
        "beats": [b.summary for b in sheet.beats],
        "cliffhanger": sheet.cliffhanger.model_dump() if sheet.cliffhanger else None,
    }
    text = "\n".join(f"{line.speaker}: {line.text}" for line in script.lines)
    response = gateway.complete(
        ModelRequest(
            run_id=run_id,
            stage="judge",
            node="story_architect",
            model=role_model("judge"),
            messages=[
                Message(role="system", content=RECORD_SYSTEM),
                Message(
                    role="user",
                    content=f"Episode {script.episode}{' (the last)' if last else ''}.\n"
                    f"Plan:\n{json.dumps(plan, ensure_ascii=False)}\nApproved script:\n<<<\n{text}\n>>>",
                ),
            ],
            params={"temperature": 0, "max_completion_tokens": 2000, "reasoning_effort": "low"},
            prompt_version=PROMPT_VERSION,
            response_schema=RECORD_SCHEMA,
        )
    )
    d = EpisodeRecordDraft.model_validate_json(response.text)
    differs = list(d.differs_from_plan)
    ending = None if last else d.ending
    if ending is not None:
        # The next opening is checked against these words, so they must be ones the script really ends on.
        closing = " ".join(w for line in script.lines for w in line.text.split())
        closing = " ".join(closing.split()[-CLOSING_WORDS:]).lower()
        kept = [k for k in ending.keywords if re.search(r"\b" + re.escape(k), closing)]
        if len(kept) >= 2:
            ending = Cliffhanger(event=ending.event, keywords=kept)
        else:
            differs.append(f"ending keywords {ending.keywords} are not in the closing lines; kept the plan's")
            ending = sheet.cliffhanger
    elif not last:
        ending = sheet.cliffhanger
    return EpisodeRecord(
        episode=script.episode,
        ending=ending,
        established=d.established,
        differs_from_plan=differs,
        planted=sorted({s.clue_id for s in script.clue_spans}),
    )
