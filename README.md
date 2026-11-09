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
uv run serial-studio show RUN_ID                           # review what the open gate is waiting on
uv run serial-studio approve RUN_ID                        # gate 1 -> Beat Planner, pauses at gate 2
uv run serial-studio reject RUN_ID --notes "..."           # re-runs the gate's agent with the notes
uv run serial-studio resume RUN_ID                         # continue a crashed run from its last node
```

Gates: 1 = bible and clue ledger (Story Architect), 2 = season plan and casting (Beat Planner).
Approving gate 2 writes the voices and each clue's plant/reveal episode into a new bible version.

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

Tests replay `tests/fixtures/speckled_band.jsonl`, an export of a real run's gateway cache.
After changing a prompt, re-record: run the pipeline for real, then
`uv run serial-studio export-recordings tests/fixtures/speckled_band.jsonl`.
