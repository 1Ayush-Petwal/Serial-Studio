"""Screenplay agent and the code validators that gate its scripts (gate 3).

The writer marks clues and sound cues inline; code parses the markers into word
indices, fixes trivial slips (a misspelled name) itself, and turns every other
broken rule into a targeted note for a revision.
"""

from __future__ import annotations

import difflib
import json
import re
from collections.abc import Callable

from pydantic import ValidationError

from serial_studio.beat_planner import _names
from serial_studio.gateway import Gateway, role_model, strict_schema
from serial_studio.schemas import (
    BeatSheet,
    Cliffhanger,
    ClueSpan,
    CritiqueNotes,
    CueMarker,
    Drafted,
    Message,
    ModelRequest,
    ScreenplayInput,
    Script,
    ScriptDraft,
    ScriptLine,
    Violation,
)
from serial_studio.story_architect import _norm

PROMPT_VERSION = "screenplay-v1"
TARGET_WORDS = 260
MAX_WORDS = 300
MAX_SECONDS = 110.0
MAX_FOLEY = 3
MAX_REVISIONS = 2
OPENING_WORDS = 60  # episode 2 on: the previous ending's keywords must land this early
# ponytail: one rate for every voice until per-voice wpm is measured on Kokoro/Chatterbox renders.
WPM = 150.0
# Seconds; before the Performance Director labels pauses, every line break is a "short" pause.
PAUSE = {"none": 0.0, "short": 0.3, "beat": 0.7, "dramatic": 1.5}
STING_TAIL = 3.0  # the series sting rings out after the last word
NARRATOR = "narrator"

MARKERS = "[clue:ID], [/clue], [sting], [sfx:ID], [bed:ID]"
MARKER = re.compile(r"\[([^\[\]]*)\]")
FOLEY = re.compile(r"(sfx|bed):([a-z0-9][a-z0-9_-]*)")

SYSTEM = f"""You are the Screenplay writer for an audio serial adapted from a mystery short story.
Write one episode from its beat sheet: about {TARGET_WORDS} spoken words, never more than {MAX_WORDS}.

- Write for the ear: narration in the third person with light dialogue. No visual-only cues; the
  listener hears everything they need.
- Each line has a speaker: "{NARRATOR}" or the exact name of a cast character.
- Follow the beats in order: hook in the first two lines, then the turns, then end on the
  cliffhanger event (the last episode ends on the resolution).
- Clues: wrap the words where the listener first hears each planned clue in
  [clue:ID] ... [/clue], and say every one of its keywords inside that span. Mark only the clues
  listed for this episode, each once.
- Sound: put [sting] once where the music sting should hit (usually just before the cliffhanger
  line), and at most {MAX_FOLEY} Foley cues: [sfx:ID] for a one-off sound and [bed:ID] for a sound
  under speech, each just before the word it lands on. IDs are short lowercase-hyphen names
  (door-knock, rain). Use no other brackets."""

SCHEMA = strict_schema(ScriptDraft)


def _sheet(inp: ScreenplayInput) -> BeatSheet:
    return inp.plan.episodes[inp.episode - 1]


def source_text(inp: ScreenplayInput) -> str:
    """The story passage this episode adapts."""
    eps = inp.plan.episodes
    end = eps[inp.episode].start if inp.episode < len(eps) else len(inp.story.text)
    return inp.story.text[_sheet(inp).start : end]


def seam(inp: ScreenplayInput) -> Cliffhanger | None:
    """The ending this episode must pick up: what the approved previous episode ended on, else the plan's."""
    record = next((r for r in inp.bible.episodes if r.episode == inp.episode - 1), None)
    return record.ending if record else _sheet(inp).previous_cliffhanger


def user_prompt(inp: ScreenplayInput) -> str:
    sheet = _sheet(inp)
    previous = seam(inp)
    planned = {cid for b in sheet.beats for cid in b.clue_ids}
    brief = {
        "episode": sheet.episode,
        "of": len(inp.plan.episodes),
        "title": sheet.title,
        "listener_knows": sheet.listener_knows,
        "recap": sheet.recap,
        "previous_cliffhanger": previous.model_dump() if previous else None,
        "beats": [b.model_dump() for b in sheet.beats],
        "cliffhanger": sheet.cliffhanger.model_dump() if sheet.cliffhanger else None,
        "clues_to_plant": [
            {"id": c.id, "text": c.text, "kind": c.kind, "keywords": c.keywords}
            for c in inp.bible.clues
            if c.id in planned
        ],
        "cast": [c.name for c in inp.bible.characters if c.name in inp.plan.casting],
        "characters": [{"name": c.name, "description": c.description} for c in inp.bible.characters],
    }
    notes = f"\nEditor notes from the last review; apply them:\n{inp.notes}\n" if inp.notes else ""
    opening = (
        f"\nOpen with the recap as one narrator line, then pick up the previous episode's ending, saying "
        f"{', '.join(map(repr, previous.keywords))} within the first {OPENING_WORDS} words.\n"
        if previous
        else ""
    )
    return (
        f"Story: {inp.story.title} by {inp.story.author}\n"
        f"Episode brief:\n{json.dumps(brief, ensure_ascii=False)}\n{opening}{notes}\n"
        f"Source passage:\n<<<\n{source_text(inp)}\n>>>"
    )


def write(gateway: Gateway, run_id: str, messages: list[Message]) -> str:
    response = gateway.complete(
        ModelRequest(
            run_id=run_id,
            stage="text",
            node="screenplay",
            model=role_model("writer"),
            messages=messages,
            prompt_version=PROMPT_VERSION,
            response_schema=SCHEMA,
        )
    )
    return response.text


def first_messages(inp: ScreenplayInput) -> list[Message]:
    return [Message(role="system", content=SYSTEM), Message(role="user", content=user_prompt(inp))]


def revision_messages(inp: ScreenplayInput, previous: str, problems: list[str]) -> list[Message]:
    notes = "\n- ".join(problems)
    return [
        *first_messages(inp),
        Message(role="assistant", content=previous),
        Message(role="user", content=f"Revise the episode to fix these problems; return it whole:\n- {notes}"),
    ]


# --- parsing and validation (code) ---


def parse(draft: ScriptDraft, inp: ScreenplayInput) -> tuple[Script, list[Violation]]:
    """Strip markers into word-indexed clue spans and cues; malformed markers become violations."""
    out: list[Violation] = []
    lines: list[ScriptLine] = []
    spans: list[ClueSpan] = []
    cues: list[CueMarker] = []
    n = 0  # words so far
    open_clue: tuple[str, int, int] | None = None
    for i, line in enumerate(draft.lines, 1):
        spoken: list[str] = []
        pos = 0
        for m in [*MARKER.finditer(line.text), None]:
            chunk = line.text[pos : m.start() if m else len(line.text)].split()
            if pos and chunk and spoken and not re.search(r"\w", chunk[0]):
                spoken[-1] += chunk.pop(0)  # "glove[/clue]." - punctuation after a marker is not a word
            spoken += chunk
            n += len(chunk)
            if m is None:
                break
            pos = m.end()
            tag = m.group(1).strip()
            if tag.startswith("clue:"):
                if open_clue:
                    out.append(
                        Violation(rule="cue_marker", message=f"line {i}: close [clue:{open_clue[0]}] first", line=i)
                    )
                open_clue = (tag[5:].strip(), n, i)
            elif tag == "/clue":
                if open_clue is None:
                    out.append(Violation(rule="cue_marker", message=f"line {i}: [/clue] without [clue:ID]", line=i))
                else:
                    spans.append(ClueSpan(clue_id=open_clue[0], start=open_clue[1], end=n))
                    open_clue = None
            elif tag == "sting":
                cues.append(CueMarker(id="sting", kind="sting", anchor_word=n, role="sting"))
            elif f := FOLEY.fullmatch(tag):
                cues.append(
                    CueMarker(id=f.group(2), kind="foley", anchor_word=n, role="hit" if f.group(1) == "sfx" else "bed")
                )
            else:
                out.append(
                    Violation(
                        rule="cue_marker",
                        message=f"line {i}: unknown marker [{tag}]; use only {MARKERS}",
                        line=i,
                    )
                )
        if any(c in w for w in spoken for c in "[]"):
            out.append(Violation(rule="cue_marker", message=f"line {i}: unbalanced square bracket", line=i))
        if spoken:
            lines.append(ScriptLine(speaker=line.speaker, text=" ".join(spoken)))
        else:
            out.append(Violation(rule="cue_marker", message=f"line {i}: has markers but no spoken words", line=i))
    if open_clue:
        out.append(
            Violation(
                rule="cue_marker",
                message=f"line {open_clue[2]}: [clue:{open_clue[0]}] is never closed",
                line=open_clue[2],
            )
        )
    # A cue after the last word snaps to it (the cliffhanger sting).
    cues = [c.model_copy(update={"anchor_word": min(c.anchor_word, max(n - 1, 0))}) for c in cues]
    script = Script(
        story_id=inp.bible.story_id,
        episode=inp.episode,
        bible_version=inp.bible.version,
        title=draft.title,
        blurb=draft.blurb,
        lines=lines,
        clue_spans=spans,
        cues=cues,
    )
    return script, out


def words(script: Script) -> list[str]:
    return [w for line in script.lines for w in line.text.split()]


def autofix(script: Script, inp: ScreenplayInput) -> tuple[Script, list[str]]:
    """Fix misspelled character names: speakers, and words found nowhere in the story that are a letter off a name."""
    names = _names(inp.bible)
    fixes: list[str] = []
    lines: list[ScriptLine] = []
    for line in script.lines:
        speaker = line.speaker
        key = _norm(speaker)
        if key != NARRATOR and key not in names:
            close = difflib.get_close_matches(key, names, n=1, cutoff=0.85)
            if close:
                speaker = names[close[0]]
                fixes.append(f"speaker {line.speaker!r} -> {speaker!r}")
        elif key in names:
            speaker = names[key]  # alias -> canonical name, which is what casting is keyed on
        lines.append(ScriptLine(speaker=speaker, text=line.text))

    story_words = set(re.findall(r"\w+", inp.story.text.lower()))
    parts = {p for c in inp.bible.characters for x in (c.name, *c.aliases) for p in re.findall(r"[A-Z]\w{3,}", x)}

    def fix_word(m: re.Match[str]) -> str:
        w = m.group(0)
        if w in parts or w.lower() in story_words:
            return w
        close: list[str] = difflib.get_close_matches(w, parts, n=1, cutoff=0.85)
        if not close:
            return w
        fixes.append(f"{w!r} -> {close[0]!r}")
        return close[0]

    lines = [ScriptLine(speaker=x.speaker, text=re.sub(r"\b[A-Z][a-z]{3,}\b", fix_word, x.text)) for x in lines]
    return script.model_copy(update={"lines": lines}), fixes


def predicted_seconds(script: Script) -> float:
    spoken = sum(len(line.text.split()) for line in script.lines) / WPM * 60
    pauses = PAUSE["short"] * max(len(script.lines) - 1, 0)
    return round(spoken + pauses + STING_TAIL, 1)


def validate(script: Script, inp: ScreenplayInput) -> list[Violation]:
    out: list[Violation] = []
    ws = words(script)
    previous = seam(inp)
    if previous:
        if _norm(script.lines[0].speaker) != NARRATOR:
            out.append(Violation(rule="recap", message="open with the recap as one narrator line", line=1))
        opening = " ".join(ws[:OPENING_WORDS]).lower()
        missing = [k for k in previous.keywords if not re.search(r"\b" + re.escape(k), opening)]
        if missing:
            out.append(
                Violation(
                    rule="seam",
                    message=f"the opening must pick up the last episode's ending ({previous.event}): say "
                    f"{', '.join(map(repr, missing))} within the first {OPENING_WORDS} words",
                )
            )
    if len(ws) > MAX_WORDS:
        out.append(
            Violation(
                rule="word_count",
                message=f"{len(ws)} words; cut {len(ws) - MAX_WORDS} or more to stay at or under {MAX_WORDS}",
            )
        )
    seconds = predicted_seconds(script)
    if seconds > MAX_SECONDS:
        over = int((seconds - MAX_SECONDS) / 60 * WPM) + 1
        out.append(
            Violation(
                rule="runtime", message=f"predicted {seconds:.0f} s, over {MAX_SECONDS:.0f} s; cut about {over} words"
            )
        )

    clues = {c.id: c for c in inp.bible.clues}
    planned = {cid for b in _sheet(inp).beats for cid in b.clue_ids}
    marked: dict[str, int] = {}
    for span in script.clue_spans:
        marked[span.clue_id] = marked.get(span.clue_id, 0) + 1
        clue = clues.get(span.clue_id)
        if clue is None:
            out.append(Violation(rule="clue_unknown", message=f"[clue:{span.clue_id}] is not in the clue ledger"))
            continue
        if clue.assigned_episode is not None and clue.assigned_episode > inp.episode:
            out.append(
                Violation(
                    rule="clue_early",
                    message=f"clue {clue.id} is planned for episode {clue.assigned_episode}; do not plant it here",
                )
            )
            continue
        text = " ".join(ws[span.start : span.end]).lower()
        missing = [k for k in clue.keywords if not re.search(r"\b" + re.escape(k), text)]
        if missing:
            out.append(
                Violation(
                    rule="clue_keywords",
                    message=f"clue {clue.id}: say {', '.join(map(repr, missing))} inside its [clue:{clue.id}] span",
                )
            )
    for cid in sorted(planned):
        if cid not in marked:
            text = clues[cid].text if cid in clues else cid
            out.append(
                Violation(
                    rule="clue_missing",
                    message=f"clue {cid} is never planted: the listener must hear that {text}; "
                    f"wrap it in [clue:{cid}] ... [/clue]",
                )
            )
        elif marked[cid] > 1:
            out.append(Violation(rule="clue_twice", message=f"clue {cid} is marked {marked[cid]} times; mark it once"))

    names = _names(inp.bible)
    for i, line in enumerate(script.lines, 1):
        key = _norm(line.speaker)
        if key == NARRATOR:
            continue
        if key not in names:
            out.append(
                Violation(rule="name", message=f"line {i}: speaker {line.speaker!r} is not a bible character", line=i)
            )
        elif names[key] not in inp.plan.casting:
            out.append(
                Violation(
                    rule="name",
                    message=f"line {i}: {names[key]} has no voice; give the line to a cast character or the narrator",
                    line=i,
                )
            )

    stings = [c for c in script.cues if c.kind == "sting"]
    foley = [c for c in script.cues if c.kind == "foley"]
    if len(stings) > 1:
        out.append(Violation(rule="cue_marker", message=f"{len(stings)} [sting] markers; use one"))
    if len(foley) > MAX_FOLEY:
        out.append(Violation(rule="cue_marker", message=f"{len(foley)} Foley cues; use at most {MAX_FOLEY}"))
    return out


def draft(raw: str, inp: ScreenplayInput) -> tuple[Script | None, list[Violation], list[str]]:
    """Parse, auto-fix and validate one writer answer."""
    try:
        d = ScriptDraft.model_validate_json(raw)
    except ValidationError as e:
        errors = [f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()]
        return None, [Violation(rule="schema", message=f"invalid JSON for the schema: {err}") for err in errors], []
    script, malformed = parse(d, inp)
    script, fixes = autofix(script, inp)
    return script, malformed + validate(script, inp), fixes


Critic = Callable[[Script], CritiqueNotes]


def write_episode(
    gateway: Gateway,
    run_id: str,
    inp: ScreenplayInput,
    previous: Drafted | None = None,
    critic: Critic | None = None,
) -> Drafted:
    """Draft an episode (or re-check `previous` against the current bible), revising up to MAX_REVISIONS times.

    Validator violations and the critics' must-fix notes share the revision budget. Critics read only a
    script that is about to reach the editor; their scores never send it back while uncalibrated.
    """
    raw = previous.raw if previous else write(gateway, run_id, first_messages(inp))
    history = list(previous.history) if previous else []
    notes = previous.critique if previous else None
    first = previous.first_draft if previous else None
    revisions = 0
    while True:
        script, violations, fixes = draft(raw, inp)
        if first is None and previous is None and revisions == 0:
            first = script
        if script is None:
            if revisions == MAX_REVISIONS:
                raise ValueError(f"episode {inp.episode}: writer returned unparseable scripts: {violations}")
            problems = [v.message for v in violations]
        elif previous is not None and revisions == 0 and not violations:
            # Still passes against the new bible: keep the draft the critics already read.
            return previous.model_copy(update={"script": script, "fixes": fixes})
        else:
            must: list[str] = []
            if critic is not None and (not violations or revisions == MAX_REVISIONS):
                notes = critic(script)
                must = [n.note for n in notes.notes if n.must_fix]
            if revisions == MAX_REVISIONS or not (violations or must):
                return Drafted(
                    episode=inp.episode,
                    raw=raw,
                    script=script,
                    violations=violations,
                    fixes=fixes,
                    revisions=revisions,
                    critique=notes,
                    history=history,
                    first_draft=first,
                )
            problems = [v.message for v in violations] + [f"{m} (critic: must fix)" for m in must]
        history.append(f"revision {len(history) + 1}: " + "; ".join(problems))
        raw = write(gateway, run_id, revision_messages(inp, raw, problems))
        revisions += 1


def markup(script: Script) -> list[str]:
    """Lines with the markers put back, for review."""
    starts: dict[int, list[str]] = {}
    ends: dict[int, list[str]] = {}
    for s in script.clue_spans:
        starts.setdefault(s.start, []).append(f"[clue:{s.clue_id}]")
        ends.setdefault(s.end, []).append("[/clue]")
    for c in script.cues:
        tag = "[sting]" if c.kind == "sting" else f"[{'sfx' if c.role == 'hit' else 'bed'}:{c.id}]"
        starts.setdefault(c.anchor_word, []).append(tag)
    out: list[str] = []
    n = 0
    for line in script.lines:
        ws = []
        for w in line.text.split():
            ws += ends.pop(n, []) + starts.pop(n, []) + [w]
            n += 1
        out.append(f"{line.speaker}: {' '.join(ws + ends.pop(n, []) if line is script.lines[-1] else ws)}")
    return out
