---
number: 10
title: "Gold-set calibration: scoring tool, thresholds and agreement"
state: open
labels: [ready-for-agent]
url: https://github.com/1Ayush-Petwal/Serial-Studio/issues/10
created: 2026-11-07T19:45:54Z
updated: 2026-11-07T19:45:54Z
---

# #10 Gold-set calibration: scoring tool, thresholds and agreement

## Parent

#1

## What to build

Tooling for the editor to score a blind, shuffled gold set of about 20 episodes from one story (6 finals, 6 first drafts, 6 baseline, 2 hand-adapted references) on tone, character, hook and cliffhanger, ear and overall. From those scores set each critic's threshold as the cut that best separates the editor's 4-and-above from 2-and-below, report agreement (Spearman and percent within one point), and switch critics to gating. Every prompt version can be re-run on the gold set to catch regressions.

Human step: the editor hand-adapts the reference scenes and does the scoring (about 4 hours).

## Acceptance criteria

- [ ] Scoring tool presents the 20 blind and shuffled and stores scores
- [ ] Thresholds and agreement stats are computed and saved
- [ ] After calibration, critic scores below threshold trigger revision
- [ ] A prompt-version change can be re-run on the gold set and compared

## Blocked by

- #9
- #6
