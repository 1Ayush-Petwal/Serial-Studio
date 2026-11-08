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
uv run serial-studio show RUN_ID                           # review the bible and clue ledger
uv run serial-studio approve RUN_ID
uv run serial-studio reject RUN_ID --notes "..."           # Story Architect re-extracts with the notes
uv run serial-studio resume RUN_ID                         # continue a crashed run from its last node
```

The judge model comes from `src/serial_studio/models.toml` (`[roles]`), overridable with
`JUDGE_MODEL=provider:model`. Every model call is cached in Postgres; re-runs are free.

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
