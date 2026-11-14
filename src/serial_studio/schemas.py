"""Typed hand-offs between every stage (PRD #1, "Schemas").

Every model forbids unknown fields, so a stage handed malformed input fails
loudly with a ValidationError instead of guessing.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Keyword = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=1)]
Keywords = Annotated[list[Keyword], Field(min_length=2, max_length=4)]


# Kokoro-82M English built-ins (decision 27): a/b = American/British, f/m = female/male.
VoiceId = Literal[
    "af_heart", "af_alloy", "af_aoede", "af_bella", "af_jessica", "af_kore", "af_nicole", "af_nova",
    "af_river", "af_sarah", "af_sky", "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam",
    "am_michael", "am_onyx", "am_puck", "am_santa", "bf_alice", "bf_emma", "bf_isabella", "bf_lily",
    "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
]  # fmt: skip


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Run, story and ingestion -------------------------------------------------


class StartRun(Schema):
    title: NonEmpty  # story title, e.g. "The Speckled Band"
    book_id: Annotated[int, Field(gt=0)]  # Gutenberg book that contains the story


class Copy(Schema):
    """One Gutenberg copy of a story."""

    book_id: int
    source_url: str
    similarity: float  # MinHash Jaccard estimate vs the copy in the requested book; >= 0.8 = same story
    noise: float  # markup artefacts per 1,000 words (illustrations, footnotes, stray symbols); lower = cleaner


class Story(Schema):
    id: NonEmpty  # slug of the title
    title: NonEmpty
    author: str
    book_id: int  # the canonical copy's book
    source_url: str
    text: NonEmpty  # cleaned prose, paragraphs separated by one blank line
    lineage: list[Copy] = []  # every copy found, cleanest first (noise, then book id); [0] is canonical


class Scene(Schema):
    """One chunk of the story handed to the Story Architect."""

    index: int
    start: int  # char offset into Story.text
    end: int
    text: NonEmpty


# --- Bible and clue ledger -----------------------------------------------------


class Place(Schema):
    name: NonEmpty
    description: str


class Pronunciation(Schema):
    term: NonEmpty
    say_as: NonEmpty  # respelling, e.g. "ROY-lot"


class ThreadDelta(Schema):
    id: NonEmpty
    question: NonEmpty


class OpenThread(ThreadDelta):
    closed: bool = False


class CharacterDelta(Schema):
    name: NonEmpty
    aliases: list[NonEmpty]
    description: str
    facts: list[NonEmpty]


class Character(CharacterDelta):
    voice_id: VoiceId | None = None  # chosen at gate 2


class ClueDelta(Schema):
    id: NonEmpty  # short snake_case, stable across scenes
    text: NonEmpty  # what the listener must learn
    kind: Literal["presence", "absence"]
    quote: NonEmpty  # verbatim words from the scene that carry the clue
    # Must-hear words; absence clues encode the absence. No max here: Groq rejects (400) rather than
    # constrains an over-long array, so merge() dedupes and keeps the first 4; Clue enforces 2-4.
    keywords: Annotated[list[Keyword], Field(min_length=2)]


class SourcePosition(Schema):
    scene: int
    offset: int  # char offset into Story.text, computed by code from the quote
    quote: str
    exact: bool  # False when the quote was not found verbatim (offset = scene start)


class Clue(Schema):
    id: NonEmpty
    text: NonEmpty
    kind: Literal["presence", "absence"]
    position: SourcePosition
    keywords: Keywords
    assigned_episode: int | None = None  # set by the Beat Planner
    reveal_episode: int | None = None


class BibleDelta(Schema):
    """What one scene adds. Code merges it into the bible."""

    characters: list[CharacterDelta]
    places: list[Place]
    facts: list[NonEmpty]
    pronunciations: list[Pronunciation]
    clues: list[ClueDelta]
    opened_threads: list[ThreadDelta]
    closed_threads: list[NonEmpty]  # ids of threads this scene resolves


class Bible(Schema):
    story_id: NonEmpty
    version: int = 0  # assigned when persisted; 0 = not yet saved
    characters: list[Character] = []
    places: list[Place] = []
    facts: list[str] = []
    pronunciations: list[Pronunciation] = []
    clues: list[Clue] = []
    open_threads: list[OpenThread] = []
    narrator_voice_id: VoiceId | None = None  # chosen at gate 2


class ArchitectInput(Schema):
    story_id: NonEmpty
    scene: Scene
    bible: Bible
    notes: str | None = None  # editor's notes from a gate-1 rejection


# --- Gates ---------------------------------------------------------------------


class Nudge(Schema):
    target: NonEmpty  # e.g. a cue id
    shift_ms: int


class GatePayload(Schema):
    gate: Literal[1, 2, 3, 4]
    run_id: NonEmpty
    target: NonEmpty  # e.g. "bible:the-speckled-band:v1"
    payload: dict[str, Any]


class Decision(Schema):
    run_id: NonEmpty
    gate: Literal[1, 2, 3, 4]
    target: NonEmpty
    verdict: Literal["approve", "reject"]
    notes: str = ""
    nudges: list[Nudge] = []


class RunStatus(Schema):
    run_id: str
    state: Literal["paused", "stopped", "done"]  # paused = waiting at a gate; stopped = crashed, resumable
    gate: GatePayload | None = None


# --- Model gateway ---------------------------------------------------------------

Stage = Literal["text", "judge", "voice", "qa"]


class ModelRef(Schema):
    provider: NonEmpty
    name: NonEmpty

    @classmethod
    def parse(cls, ref: str) -> ModelRef:
        provider, _, name = ref.partition(":")
        return cls(provider=provider, name=name)

    def __str__(self) -> str:
        return f"{self.provider}:{self.name}"


class Message(Schema):
    role: Literal["system", "user", "assistant"]
    content: str


class ModelRequest(Schema):
    run_id: NonEmpty
    stage: Stage
    node: NonEmpty
    model: ModelRef
    messages: list[Message]
    params: dict[str, Any] = {}
    prompt_version: NonEmpty
    response_schema: dict[str, Any] | None = None


class ModelResponse(Schema):
    text: str
    input_tokens: int
    output_tokens: int
    cache_hit: bool


class CostLine(Schema):
    run_id: str
    stage: Stage
    node: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    list_price_usd: float
    cache_hit: bool


# --- Season plan and casting ----------------------------------------------------


class Beat(Schema):
    kind: Literal["hook", "turn", "cliffhanger", "resolution"]  # resolution ends the last episode
    summary: NonEmpty
    clue_ids: list[str]  # clues planted in this beat


class Cliffhanger(Schema):
    event: NonEmpty  # something that happens, is heard or is said; not a question
    keywords: Keywords  # ep N+1's opening must hit these (decision 25)


class EpisodeDraft(Schema):
    """One episode as the Beat Planner writes it."""

    episode: int
    title: NonEmpty
    starts_at: NonEmpty  # opening words of the story passage this episode adapts, verbatim
    listener_knows: list[NonEmpty]  # state at the start of the episode
    recap: str | None  # one narrator line, required from episode 2 on
    beats: Annotated[list[Beat], Field(min_length=3, max_length=5)]
    cliffhanger: Cliffhanger | None  # every episode but the last
    reveals: list[str]  # clues whose meaning this episode explains


class CastingChoice(Schema):
    character: NonEmpty  # canonical bible name
    voice_id: VoiceId
    why: NonEmpty


class PlanDraft(Schema):
    """Beat Planner output: the season, then casting."""

    episodes: Annotated[list[EpisodeDraft], Field(min_length=5, max_length=7)]
    narrator_voice: VoiceId
    casting: list[CastingChoice]


class PlannerInput(Schema):
    story: Story
    bible: Bible  # the version approved at gate 1
    notes: str | None = None  # editor's notes from gate-2 rejections


class BeatSheet(EpisodeDraft):
    start: int  # char offset of starts_at in Story.text; the episode runs to the next one's start
    previous_cliffhanger: Cliffhanger | None = None  # the seam ep N+1 must pick up


class SeasonPlan(Schema):
    story_id: NonEmpty
    bible_version: int
    version: int  # attempt number within the run; gate-2 target
    episodes: Annotated[list[BeatSheet], Field(min_length=5, max_length=7)]
    casting: dict[str, VoiceId]  # canonical character name, or "narrator" -> voice


# --- Later slices (defined now so hand-offs are fixed before the code) -----------


class ClueSpan(Schema):
    clue_id: NonEmpty
    start: int  # word index into the script
    end: int


class CueMarker(Schema):
    id: NonEmpty
    kind: Literal["sting", "foley"]
    anchor_word: int  # word index the cue snaps to
    role: Literal["hit", "bed", "sting"]


class ScriptLine(Schema):
    speaker: NonEmpty  # "narrator" or a character name
    text: NonEmpty


class Script(Schema):
    story_id: NonEmpty
    episode: int
    bible_version: int | None  # None for the baseline, which reads no bible
    title: NonEmpty
    blurb: NonEmpty
    lines: list[ScriptLine]
    clue_spans: list[ClueSpan]
    cues: list[CueMarker]


class BaselineEpisode(Schema):
    title: NonEmpty
    blurb: NonEmpty
    lines: list[ScriptLine] = Field(min_length=1)


class BaselineDraft(Schema):
    episodes: list[BaselineEpisode] = Field(min_length=5, max_length=7)


class Violation(Schema):
    rule: NonEmpty  # e.g. "word_count", "clue_missing", "seam"
    message: NonEmpty
    line: int | None = None


class CritiqueNote(Schema):
    critic: Literal["tone", "character", "structure", "ear", "lead"]
    note: NonEmpty
    must_fix: bool
    rank: int


class CritiqueNotes(Schema):
    scores: dict[str, float]  # critic -> 1-5
    notes: list[CritiqueNote]


class LinePerformance(Schema):
    line: int
    speaker: NonEmpty
    emotion: NonEmpty
    intensity: Annotated[float, Field(ge=0, le=1)]
    pace: Literal["slow", "normal", "urgent"]
    pause_before: Literal["none", "short", "beat", "dramatic"]
    pause_after: Literal["none", "short", "beat", "dramatic"]
    climax: bool = False


class PerformanceSheet(Schema):
    episode: int
    lines: list[LinePerformance]


class Cue(Schema):
    id: NonEmpty
    clip_id: NonEmpty
    role: Literal["hit", "bed", "sting"]
    anchor: Literal["word", "beat", "end"]
    anchor_index: int


class CueList(Schema):
    episode: int
    cues: Annotated[list[Cue], Field(max_length=4)]  # 1 sting + up to 3 Foley


class Clip(Schema):
    track: Literal["voice", "sfx", "music"]
    source: NonEmpty
    start_ms: int
    end_ms: int
    gain_db: float = 0.0
    fade_in_ms: int = 0
    fade_out_ms: int = 0


class Timeline(Schema):
    episode: int
    clips: list[Clip]
    duration_ms: Annotated[int, Field(le=120_000)]


class ReportCard(Schema):
    episode: int
    scores: dict[str, float]  # fidelity, craft, timing, audio
    revisions: list[str]  # what was revised and why
    cost_lines: list[CostLine]
