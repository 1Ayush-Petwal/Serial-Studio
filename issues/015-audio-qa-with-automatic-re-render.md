---
number: 15
title: "Audio QA with automatic re-render"
state: open
labels: [ready-for-agent]
url: https://github.com/1Ayush-Petwal/Serial-Studio/issues/15
created: 2026-11-07T19:46:04Z
updated: 2026-11-07T19:46:04Z
---

# #15 Audio QA with automatic re-render

## Parent

#1

## What to build

Check every mix before gate 4: round-trip WER against the script, predicted MOS, loudness about -16 LUFS, pace about 150 wpm, long silences, duration 120 seconds or less, first stakes line within 10 seconds, cue-to-anchor offset, WER of the final mix against the dry voice (a rise means masking), and emotion match gated on intensity direction rather than exact class. Failures re-render the offending lines where possible; results go on the report card.

## Acceptance criteria

- [ ] Each check produces a value and pass or fail on the report card
- [ ] A line with a dropped word is detected by WER and re-rendered
- [ ] Music loud enough to mask speech is detected by mix-versus-dry WER
- [ ] Emotion match fails only when intensity direction is wrong
- [ ] Only mixes that pass reach gate 4, or reach it flagged after retries are exhausted

## Blocked by

- #12
- #13
