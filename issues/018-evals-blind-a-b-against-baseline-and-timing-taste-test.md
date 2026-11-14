---
number: 18
title: "Evals: blind A/B against baseline and timing-taste test"
state: open
labels: [ready-for-agent]
url: https://github.com/1Ayush-Petwal/Serial-Studio/issues/18
created: 2026-11-07T19:46:11Z
updated: 2026-11-07T19:46:11Z
---

# #18 Evals: blind A/B against baseline and timing-taste test

## Parent

#1

## What to build

Blind head-to-head of pipeline against baseline with positions swapped: text pairs judged by a model family on Groq never used in the loop or as the day-1 judge, across all available pairs; 6 audio pairs (baseline through the same TTS and mixer) judged blind by the editor as a sanity check. Also a blind listening test on 5 episodes of solver timing against evenly spaced pauses.

Human step: the editor does the audio pairs and the timing test.

## Acceptance criteria

- [ ] LLM judge results include win rate with n, positions swapped
- [ ] A/B judge model family is checked against those used in the loop and day 1
- [ ] Editor audio-pair results and agreement with the LLM judge are recorded
- [ ] Timing-taste results are recorded

## Blocked by

- #6
- #15
