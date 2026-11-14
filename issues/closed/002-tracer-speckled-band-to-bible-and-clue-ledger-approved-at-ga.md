---
number: 2
title: "Tracer: Speckled Band to bible and clue ledger, approved at gate 1 (CLI)"
state: closed
labels: [ready-for-agent]
url: https://github.com/1Ayush-Petwal/Serial-Studio/issues/2
created: 2026-11-07T19:45:37Z
updated: 2026-11-09T06:40:27Z
---

# #2 Tracer: Speckled Band to bible and clue ledger, approved at gate 1 (CLI)

## Parent

#1

## What to build

First end-to-end path. Fetch The Speckled Band from Gutendex, clean it (strip Gutenberg licence header and footer, repair hard line-wraps, handle footnotes), and run the Story Architect over it scene by scene: each call takes one scene chunk plus the current bible and returns a delta, which code merges and dedupes by name and alias. The result is a versioned bible (characters, aliases, facts, places, pronunciations, open threads) and a clue ledger (each clue with source position and 2-4 must-hear keywords, absence clues included) stored in Postgres with pgvector. The graph pauses at gate 1; the editor approves or rejects with notes from a CLI, and a rejection routes back to the Story Architect.

This slice also lays the shared foundation every later slice reuses: repo scaffold, lint and test setup, docker-compose Postgres for tests, committed env example, typed schemas for every hand-off in the PRD, the graph runner with Postgres checkpointer and the generic gate mechanism (interrupt, decision row, resume), and the model gateway. The gateway is the single path for every external model call: it caches by model, input, parameters and prompt version (the cache doubles as a record/replay store for tests), traces to Langfuse, and writes shadow-cost lines. The judge is a Groq-hosted non-Google model chosen by configuration. Check Gemini and Groq free-tier limits against the workload.

## Acceptance criteria

- [ ] Running the pipeline on The Speckled Band produces a bible and clue ledger, persisted and versioned
- [ ] Cleaned text contains no Gutenberg licence text and no hard line-wraps mid-sentence
- [ ] Clue ledger includes the whistle, the clang and the saucer of milk with must-hear keywords and source positions
- [ ] Run pauses at gate 1; CLI approve completes the run; CLI reject with notes re-runs the Story Architect with those notes
- [ ] Killing the run mid-way and resuming continues from the last completed node
- [ ] Every model call goes through the gateway; a second identical run makes zero network calls; a prompt-version bump re-runs
- [ ] Each model call writes a shadow-cost line (stage, provider, units, list price, cache hit) and a Langfuse trace
- [ ] Judge model is swappable by configuration only
- [ ] Malformed stage input fails loudly with a schema error
- [ ] Tests at the graph-runner seam replay recorded responses and pass without network; no secrets in git

## Blocked by

None - can start immediately
