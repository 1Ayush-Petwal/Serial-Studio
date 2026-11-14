---
number: 5
title: "Season plan, beat sheets and casting, approved at gate 2 (CLI)"
state: open
labels: [ready-for-agent]
url: https://github.com/1Ayush-Petwal/Serial-Studio/issues/5
created: 2026-11-07T19:45:43Z
updated: 2026-11-07T19:45:43Z
---

# #5 Season plan, beat sheets and casting, approved at gate 2 (CLI)

## Parent

#1

## What to build

After gate 1, the Beat Planner splits the story into 5-7 episodes (target 6) at real plot turns and writes a beat sheet per episode: 3-5 beats (hook, turn, cliffhanger), every clue assigned to an episode before the reveal, each cliffhanger as a concrete event with keywords, what the listener knows at the start of each episode, and a one-line recap for episode 2 onward. It also proposes casting: a voice per character and a separate narrator voice, stored in the bible. The graph pauses at gate 2; the editor approves or rejects with notes, and a rejection routes back to the Beat Planner.

## Acceptance criteria

- [ ] Approved bible leads to a season plan with 5-7 episodes and 3-5 beats each
- [ ] Every clue in the ledger is assigned to an episode at or before its reveal episode
- [ ] Every episode but the last has a cliffhanger event with keywords; every episode from 2 has a recap
- [ ] Casting assigns a voice to the narrator and each speaking character; narrator differs from Watson
- [ ] Gate 2 approve continues; reject with notes re-runs the Beat Planner
- [ ] Covered by tests at the graph-runner seam

## Blocked by

- #2
