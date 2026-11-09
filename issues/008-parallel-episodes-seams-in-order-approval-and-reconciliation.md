---
number: 8
title: "Parallel episodes, seams, in-order approval and reconciliation"
state: open
labels: [ready-for-agent]
url: https://github.com/1Ayush-Petwal/Serial-Studio/issues/8
created: 2026-11-07T19:45:50Z
updated: 2026-11-07T19:45:50Z
---

# #8 Parallel episodes, seams, in-order approval and reconciliation

## Parent

#1

## What to build

Fan out one branch per episode with the Send API so the whole season drafts in parallel. Each episode's opening must hit the previous cliffhanger's keywords and episodes from 2 open with the recap; a seam validator checks this. At gate 3 the editor can read in any order but approve only in episode order. On each approval the Story Architect records what the episode established, compares it with the plan, and later drafts are re-validated; anything that now fails goes back to the Screenplay agent before the editor sees it.

## Acceptance criteria

- [ ] A full season drafts in parallel and all episodes reach gate 3
- [ ] Seam validator fails an episode whose opening misses the previous cliffhanger keywords
- [ ] Approving episode N+1 before episode N is refused
- [ ] Approving an edited episode N whose ending changed re-validates episode N+1 and returns it to the Screenplay agent if the seam breaks
- [ ] Story Architect writes a new bible version after each approval
- [ ] Covered by tests at the graph-runner seam

## Blocked by

- #7
