# Serial Studio

Turns a public-domain mystery short story into a season of 2-minute audio episodes.
Plan and decisions: [`docs/BRIEF.md`](docs/BRIEF.md). PRD: issue #1.

## Setup

```sh
uv sync
cp .env.example .env        # fill in keys; .env is git-ignored
docker compose up -d        # local Postgres + pgvector (tests use it)
```

## Run

```sh
uv run serial-studio run "The Speckled Band" --book 1661   # ingest + Story Architect, pauses at gate 1
uv run serial-studio run "The Red-Headed League" --book 1661   # other demo stories
uv run serial-studio run "Silver Blaze" --book 834
uv run serial-studio show RUN_ID                           # review what the open gate is waiting on
uv run serial-studio approve RUN_ID                        # gate 1 -> Beat Planner -> gate 2 -> episode 1 script -> gate 3
uv run serial-studio reject RUN_ID --notes "..."           # re-runs the gate's agent with the notes
uv run serial-studio resume RUN_ID                         # continue a crashed run from its last node
uv run serial-studio baseline "The Speckled Band" --book 1661   # single-prompt season for the A/B test
```

Ingest cuts the story out of the anthology by its heading, then looks for other Gutenberg copies
(Gutendex searches on the book's and the story's title): MinHash over 5-word shingles, Jaccard >= 0.8
means the same story. The cleanest copy (fewest markup artefacts, then lowest book id) becomes the text;
every copy is kept as `Story.lineage`.

The baseline is one writer call (same model, same script schema, no planning or validation); its
scripts are stored with `source = 'baseline'` in the `scripts` table, a label kept out of the script a
blind judge reads.

Gates: 1 = bible and clue ledger (Story Architect), 2 = season plan and casting (Beat Planner),
3 = episode script (Screenplay agent). Approving gate 2 writes the voices and each clue's plant/reveal
episode into a new bible version.

The Screenplay agent marks clues `[clue:id] ... [/clue]` and cues `[sting]`, `[sfx:id]`, `[bed:id]`
inline; code strips them into word indices. Validators: <= 300 words, predicted runtime <= 110 s
(150 wpm, 0.3 s per line break, 3 s sting tail - placeholders until voices are measured), every planned
clue marked once with all its keywords inside the span, no clue before its planned episode, speakers
in the bible and cast, well-formed markers (1 sting, <= 3 Foley). Misspelled names are fixed in code;
anything else goes back as a note, at most 2 revisions, then gate 3 shows what is still broken.

The whole season drafts in parallel (one LangGraph `Send` branch per episode). Episode 2 on must open
with a narrator recap and say the previous ending's keywords in the first 60 words. Gate 3 shows every
draft (`show RUN_ID --episode N`) but approves only the next episode in order. Each approval has the
Story Architect record what the episode established - the ending it actually reached, facts, departures
from the plan - as a new bible version; later drafts are re-validated against it, and any that now
break (say, a seam after a changed ending) go back to the Screenplay agent before the editor sees them.

Critique panel (CrewAI crew, judge model through the gateway): tone, character (guesses each speaker
from lines with names stripped -> `speaker_accuracy`), structure and ear critics, and a lead critic who
ranks the notes and marks must-fix ones. Until calibration (#10) scores never gate: only must-fix notes
send a script back, sharing the 2-revision budget with the validators. Gate 3 shows the report card:
scores per critic and every revision with its reason. CrewAI telemetry and trace upload are off.

Models come from `src/serial_studio/models.toml` (`[roles]`), overridable with
`JUDGE_MODEL=provider:model` / `WRITER_MODEL=provider:model`. The writer (Gemini) needs a key from
an AI Studio project without prepaid billing, or calls fail with 402.
Free-tier Gemini queues long calls: one Beat Planner plan (~17K in / 3K out) has taken 13 minutes to
several hours. The gateway retries timeouts and dropped connections; a crashed run continues with `resume`. Every model call is cached in Postgres; re-runs are free.

Groq free tier for the day-1 judge (`openai/gpt-oss-120b`): 8K tokens/min (input + output cap),
200K tokens/day, refilled continuously. One Story Architect pass over a story is ~30K tokens.
A call that would wait more than 2 minutes fails loudly; `resume` continues from the last scene.

## Test

```sh
uv run pytest               # needs the docker-compose Postgres; no network, no keys
uv run ruff check . && uv run mypy
```

Tests replay `tests/fixtures/recordings.jsonl`, an export of a real run's gateway cache.
After changing a prompt, re-record: run the pipeline for real, then
`uv run serial-studio export-recordings tests/fixtures/recordings.jsonl`.
