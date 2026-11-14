---
number: 3
title: "Anthology story boundaries and near-duplicate detection for all 3 demo stories"
state: closed
labels: [ready-for-agent]
url: https://github.com/1Ayush-Petwal/Serial-Studio/issues/3
created: 2026-11-07T19:45:39Z
updated: 2026-11-07T19:45:39Z
---

# #3 Anthology story boundaries and near-duplicate detection for all 3 demo stories

## Parent

#1

## What to build

Extend ingestion so a single story can be pulled from an anthology by its boundaries, and so the same story found in several Gutenberg books is recognised. Near-duplicates use MinHash on 5-word shingles; Jaccard 0.8 or above means the same story. The cleanest edition becomes canonical and the others are recorded as lineage. Ingest The Speckled Band, The Red-Headed League and Silver Blaze, each from at least one anthology, and run each through the Story Architect to gate 1.

## Acceptance criteria

- [ ] All 3 demo stories are extracted from anthologies with correct start and end
- [ ] At least one duplicate copy of each story across Gutenberg books is detected and linked as lineage
- [ ] Canonical copy choice is deterministic and recorded
- [ ] Each of the 3 stories reaches gate 1 with a bible and clue ledger
- [ ] Silver Blaze's ledger captures the dog that did not bark as an absence clue with keywords
- [ ] Covered by tests at the graph-runner seam

## Blocked by

- #2
