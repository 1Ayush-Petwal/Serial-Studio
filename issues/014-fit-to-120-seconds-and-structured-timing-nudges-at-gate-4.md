---
number: 14
title: "Fit to 120 seconds and structured timing nudges at gate 4"
state: open
labels: [ready-for-agent]
url: https://github.com/1Ayush-Petwal/Serial-Studio/issues/14
created: 2026-11-07T19:46:02Z
updated: 2026-11-07T19:46:02Z
---

# #14 Fit to 120 seconds and structured timing nudges at gate 4

## Parent

#1

## What to build

When a mix exceeds 120 seconds, fix it cheapest first: shorten ordinary pauses toward their minimum (dramatic pauses protected), then time-stretch narration lines without pitch change (never climax lines, max stretch configurable and tuned by ear), then request a word cut from the Screenplay agent that returns to the editor as a small diff at gate 3. At gate 4 the editor can give structured nudges (for example sting 300 ms later) that code applies to the timeline exactly, without an LLM.

## Acceptance criteria

- [ ] An over-length fixture is fixed by pauses alone when that suffices
- [ ] Stretch is applied only when pauses are not enough, never to climax lines, never beyond the configured max
- [ ] A word cut is requested only when both tiers fail, and appears to the editor as a diff
- [ ] A nudge moves the named cue by exactly the given offset and re-renders
- [ ] Covered by tests at the audio-timeline seam

## Blocked by

- #13
