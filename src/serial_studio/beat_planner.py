"""Beat Planner: season plan, beat sheets, clue placement and casting (gate 2).

One writer-model call plans the whole season from the full story and the
approved bible. Code checks the hard rules; a plan that breaks one goes back to
the model with the problems listed, up to MAX_REPAIRS times, then fails loudly.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import get_args

from pydantic import ValidationError

from serial_studio.gateway import Gateway, role_model, strict_schema
from serial_studio.schemas import (
    BeatSheet,
    Bible,
    Message,
    ModelRequest,
    PlanDraft,
    PlannerInput,
    SeasonPlan,
    VoiceId,
)
from serial_studio.story_architect import _norm, find_quote

PROMPT_VERSION = "beat-planner-v1"
MAX_REPAIRS = 2
RECAP_MAX_WORDS = 20
# A seam keyword must be a word that only the cliffhanger event would put in the next opening.
STOPWORDS = frozenset(
    [
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "of",
        "to",
        "in",
        "on",
        "at",
        "by",
        "for",
        "with",
        "from",
        "is",
        "was",
        "are",
        "were",
        "be",
        "it",
        "its",
        "he",
        "she",
        "they",
        "his",
        "her",
    ]
)

SYSTEM = f"""You are the Beat Planner for an audio serial adapted from a mystery short story.
Split the story into a season of 5-7 episodes (target 6), each at most 2 minutes (about 260
spoken words), write a beat sheet for each, place every clue, and cast the voices.

Season:
- Cut only at real turns in the plot: a discovery, an arrival, a threat, a decision. Never cut
  mid-scene; a cliffhanger has to land on a genuine moment or the listener feels cheated.
  Episodes cover the story in order with no gaps; episode 1 starts where the story starts.
- starts_at: copy the first 6-12 words of the story passage where the episode begins, character
  for character, so code can find it in the text.
- 2 minutes holds 3-5 beats: a hook first (stakes inside the first 10 seconds), then 1-3 turns,
  then a cliffhanger. The last episode ends on a resolution beat instead.
- cliffhanger (every episode but the last; null for the last): a concrete event the listener hears
  happen or be said - a scream, a knock, a name, a discovery - never a question or a mood, because
  the next episode must open by picking it up. keywords: 2-4 lowercase words from that event that
  the next episode's opening will say.
- recap (episode 2 on; null for episode 1): one narrator line of at most {RECAP_MAX_WORDS} words that
  orients a listener arriving cold.
- listener_knows: short statements of what the listener already knows when the episode starts
  (empty for episode 1): who is who, what has happened, which clues they have heard.

Clues (fair play: the listener must hear every clue before the solution explains it):
- Put every clue id from the ledger in clue_ids of exactly one beat: the beat where the listener
  first hears it, normally in the episode that adapts the clue's quoted source passage.
- Put every clue id in reveals of exactly one episode: the one where the solution explains what it
  meant. A clue is planted in its reveal episode or earlier, never later.
- Use only clue ids from the ledger.

Casting:
- Voices are Kokoro voices: {", ".join(get_args(VoiceId))}.
  Prefix a = American, b = British; then f = female, m = male. Prefer British voices for a story
  set in England, and match each voice to the character.
- Cast every character who speaks a line of dialogue in the adaptation, by canonical bible name;
  leave out characters who never speak.
- Every voice is distinct, and the narrator's voice differs from every character's: narration is
  third person, so a character who narrates the original (such as Watson) gets a separate voice.
- why: one line on the fit."""

PLAN_SCHEMA = strict_schema(PlanDraft)


def user_prompt(inp: PlannerInput) -> str:
    b = inp.bible
    bible = {
        "characters": [{"name": c.name, "aliases": c.aliases, "description": c.description} for c in b.characters],
        "clue_ledger": [
            {"id": c.id, "text": c.text, "kind": c.kind, "keywords": c.keywords, "quote": c.position.quote}
            for c in b.clues
        ],
        "open_threads": [t.question for t in b.open_threads],
    }
    notes = f"\nEditor notes from the last review; apply them:\n{inp.notes}\n" if inp.notes else ""
    return (
        f"Story: {inp.story.title} by {inp.story.author}\n"
        f"Bible:\n{json.dumps(bible, ensure_ascii=False)}\n{notes}\n"
        f"Story text:\n<<<\n{inp.story.text}\n>>>"
    )


def _starts(draft: PlanDraft, text: str) -> list[int | None]:
    """Offset of each episode's starts_at, searched after the previous episode's start."""
    out: list[int | None] = []
    pos = -1
    for e in draft.episodes:
        m = find_quote(e.starts_at, text[pos + 1 :])
        if m is not None:
            pos += 1 + m.start()
        out.append(None if m is None else pos)
    return out


def _content(keywords: list[str]) -> list[str]:
    return [k for k in keywords if k not in STOPWORDS]


def _names(bible: Bible) -> dict[str, str]:
    return {_norm(x): c.name for c in bible.characters for x in (c.name, *c.aliases)}


def problems(draft: PlanDraft, inp: PlannerInput) -> list[str]:
    """Hard rules from the brief that the schema cannot express."""
    out: list[str] = []
    n = len(draft.episodes)
    if [e.episode for e in draft.episodes] != list(range(1, n + 1)):
        out.append(f"episodes must be numbered 1 to {n} in order")

    planted: dict[str, list[int]] = defaultdict(list)
    revealed: dict[str, list[int]] = defaultdict(list)
    for i, (e, start) in enumerate(zip(draft.episodes, _starts(draft, inp.story.text), strict=True), 1):
        last = i == n
        kinds = [b.kind for b in e.beats]
        end = "resolution" if last else "cliffhanger"
        if kinds[0] != "hook" or kinds[-1] != end or any(k != "turn" for k in kinds[1:-1]):
            out.append(f"episode {i}: beats must be hook, turn(s), {end}; got {', '.join(kinds)}")
        if last and e.cliffhanger is not None:
            out.append(f"episode {i}: the last episode has no cliffhanger (null)")
        if not last and e.cliffhanger is None:
            out.append(f"episode {i}: needs a cliffhanger event with keywords")
        if e.cliffhanger and len(_content(e.cliffhanger.keywords)) < 2:
            out.append(f"episode {i}: cliffhanger needs 2-4 content keywords, not words like 'the'")
        if i == 1 and e.recap:
            out.append("episode 1: recap must be null")
        if i > 1 and not (e.recap and e.recap.strip()):
            out.append(f"episode {i}: needs a one-line recap")
        elif i > 1 and e.recap and len(e.recap.split()) > RECAP_MAX_WORDS:
            out.append(f"episode {i}: recap is over {RECAP_MAX_WORDS} words")
        if start is None:
            out.append(f"episode {i}: starts_at {e.starts_at!r} is not in the story text after episode {i - 1}")
        for cid in (cid for b in e.beats for cid in b.clue_ids):
            planted[cid].append(i)
        for cid in e.reveals:
            revealed[cid].append(i)

    ledger = [c.id for c in inp.bible.clues]
    for cid in sorted((planted.keys() | revealed.keys()) - set(ledger)):
        out.append(f"clue {cid!r} is not in the ledger")
    for cid in ledger:
        p, r = planted[cid], revealed[cid]
        if len(p) != 1:
            out.append(f"clue {cid!r} must be planted in exactly one beat; planted in episodes {p or 'none'}")
        if len(r) != 1:
            out.append(f"clue {cid!r} must be revealed in exactly one episode; revealed in {r or 'none'}")
        if len(p) == 1 and len(r) == 1 and p[0] > r[0]:
            out.append(f"clue {cid!r} is planted in episode {p[0]}, after its reveal in episode {r[0]}")

    names = _names(inp.bible)
    cast: dict[str, str] = {}
    for choice in draft.casting:
        canon = names.get(_norm(choice.character))
        if canon is None:
            out.append(f"casting: {choice.character!r} is not a bible character")
        elif canon in cast:
            out.append(f"casting: {canon!r} is cast twice")
        else:
            cast[canon] = choice.voice_id
    if not cast:
        out.append("casting: cast every speaking character")
    voices = [draft.narrator_voice, *cast.values()]
    if len(set(voices)) != len(voices):
        out.append("casting: the narrator and every character need distinct voices")
    return out


def season_plan(draft: PlanDraft, inp: PlannerInput, version: int) -> SeasonPlan:
    """Resolve offsets, canonical names and seams; assumes problems() is empty."""
    names = _names(inp.bible)
    episodes: list[BeatSheet] = []
    for e, start in zip(draft.episodes, _starts(draft, inp.story.text), strict=True):
        assert start is not None
        sheet = BeatSheet(**e.model_dump(), start=start)
        if sheet.cliffhanger:
            sheet.cliffhanger.keywords = _content(sheet.cliffhanger.keywords)
        sheet.previous_cliffhanger = episodes[-1].cliffhanger if episodes else None
        episodes.append(sheet)
    casting = {"narrator": draft.narrator_voice} | {names[_norm(c.character)]: c.voice_id for c in draft.casting}
    return SeasonPlan(
        story_id=inp.bible.story_id,
        bible_version=inp.bible.version,
        version=version,
        episodes=episodes,
        casting=casting,
    )


def plan(gateway: Gateway, run_id: str, inp: PlannerInput, version: int) -> SeasonPlan:
    messages = [Message(role="system", content=SYSTEM), Message(role="user", content=user_prompt(inp))]
    for _ in range(MAX_REPAIRS + 1):
        response = gateway.complete(
            ModelRequest(
                run_id=run_id,
                stage="text",
                node="beat_planner",
                model=role_model("writer"),
                messages=messages,
                # Planning is the highest-leverage call per story, so it gets more thinking than extraction.
                params={"reasoning_effort": "medium"},
                prompt_version=PROMPT_VERSION,
                response_schema=PLAN_SCHEMA,
            )
        )
        try:
            draft = PlanDraft.model_validate_json(response.text)
        except ValidationError as e:  # JSON mode does not enforce the schema, so shape errors get repaired too
            found = [f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()]
        else:
            found = problems(draft, inp)
            if not found:
                return season_plan(draft, inp, version)
        messages += [
            Message(role="assistant", content=response.text),
            Message(
                role="user", content="Fix these problems and return the whole plan again:\n- " + "\n- ".join(found)
            ),
        ]
    raise ValueError(f"beat planner broke the rules after {MAX_REPAIRS} repairs: {found}")
