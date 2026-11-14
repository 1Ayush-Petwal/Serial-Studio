---
number: 7
title: "Tracer: one episode script with validators and revise loop, approved at gate 3 (CLI)"
state: open
labels: [ready-for-agent]
url: https://github.com/1Ayush-Petwal/Serial-Studio/issues/7
created: 2026-11-07T19:45:48Z
updated: 2026-11-07T19:45:48Z
---

# #7 Tracer: one episode script with validators and revise loop, approved at gate 3 (CLI)

## Parent

#1

## What to build

After gate 2, the Screenplay agent writes episode 1: about 260 words, cap 300, narration with light dialogue, speaker tags, sound-cue markers and clue markers around each planted clue. Code validators check word count, predicted runtime (110 seconds or less from per-voice words per minute, the pause table and the sting tail; 150 wpm until measured), clue markers present in the planned episode with keywords inside the span and before the reveal, names and facts against the bible, and cue-marker well-formedness. Trivial slips such as a misspelled name are fixed automatically. Violations become targeted notes and send the script back, at most 2 revisions. The script then pauses at gate 3 with its predicted runtime and violations; reject with notes routes to the Screenplay agent.

## Acceptance criteria

- [ ] Episode 1 script is produced in the script schema and records the bible version
- [ ] Each validator rule has a passing and failing case through the graph-runner seam
- [ ] A misspelled character name is auto-fixed without a revision
- [ ] Violations trigger revision with targeted notes; the loop stops after 2 revisions
- [ ] Scripts estimating over 110 seconds never reach gate 3 without being flagged
- [ ] Gate 3 shows predicted runtime; reject with notes re-runs the Screenplay agent

## Blocked by

- #5
