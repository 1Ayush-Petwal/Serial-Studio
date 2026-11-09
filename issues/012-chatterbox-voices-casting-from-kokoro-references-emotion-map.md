---
number: 12
title: "Chatterbox voices: casting from Kokoro references, emotion mapping, takes and line cache"
state: open
labels: [ready-for-agent]
url: https://github.com/1Ayush-Petwal/Serial-Studio/issues/12
created: 2026-11-07T19:45:58Z
updated: 2026-11-07T19:45:58Z
---

# #12 Chatterbox voices: casting from Kokoro references, emotion mapping, takes and line cache

## Parent

#1

## What to build

Switch final renders to Chatterbox on Modal GPU. Each cast voice's reference clip is rendered from its Kokoro built-in voice so the cast is synthetic and identical under fallback. A code table maps emotion, intensity and pace to exaggeration, guidance weight and pause lengths. Key lines get 2-3 takes; the best wins on round-trip WER, predicted naturalness and fit to its time budget. Unchanged lines are cached so a revision re-renders only what changed. Measure per-voice words per minute and feed it to the runtime estimator. Kokoro remains the fallback.

## Acceptance criteria

- [ ] Final renders use Chatterbox; switching to Kokoro is a config change
- [ ] Emotion, intensity and pace map to engine settings via a code table
- [ ] Key lines render multiple takes and the chosen take is recorded with its scores
- [ ] Revising one line re-renders only that line
- [ ] Measured per-voice wpm replaces the 150 wpm default in the estimator
- [ ] Render time and GPU cost per episode are recorded

## Blocked by

- #11
- #5
