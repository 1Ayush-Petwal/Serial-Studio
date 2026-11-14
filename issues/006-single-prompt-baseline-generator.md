---
number: 6
title: "Single-prompt baseline generator"
state: open
labels: [ready-for-agent]
url: https://github.com/1Ayush-Petwal/Serial-Studio/issues/6
created: 2026-11-07T19:45:46Z
updated: 2026-11-07T19:45:46Z
---

# #6 Single-prompt baseline generator

## Parent

#1

## What to build

A single-prompt adaptation of a story into episodes, for the gold set and the later A/B test. It uses the same writer model and produces scripts in the same schema as the pipeline so the two are directly comparable, but with none of the planning, validation or critique.

## Acceptance criteria

- [ ] Baseline produces a season of scripts for a story in the shared script schema
- [ ] Baseline uses the writer model through the gateway and is cached
- [ ] Baseline scripts are stored and labelled as baseline for blind evaluation

## Blocked by

- #2
