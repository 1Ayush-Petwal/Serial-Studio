---
number: 9
title: "Critique panel node with ranked notes and report card"
state: open
labels: [ready-for-agent]
url: https://github.com/1Ayush-Petwal/Serial-Studio/issues/9
created: 2026-11-07T19:45:52Z
updated: 2026-11-07T19:45:52Z
---

# #9 Critique panel node with ranked notes and report card

## Parent

#1

## What to build

Add the critique panel as one LangGraph node running a CrewAI crew with one typed input and one typed output: Tone, Character (speaker names stripped, judge guesses the speaker), Structure (hook, beats, cliffhanger) and Ear (beats that only work visually, sentence length, narrator/dialogue ratio, similar-sounding names) critics, plus a lead critic who ranks notes and marks must-fix ones. Before calibration critics do not gate: the revise loop uses validator violations plus must-fix notes, still at most 2 revisions. Each script reaching gate 3 carries a report card with scores and what was revised and why.

## Acceptance criteria

- [ ] Critique node takes and returns typed objects; malformed crew output fails loudly
- [ ] Must-fix notes trigger a revision; other notes do not
- [ ] Total revisions never exceed 2 across validators and critics combined
- [ ] Report card at gate 3 lists scores per critic and each revision with its reason
- [ ] Critic scores never block a script while uncalibrated
- [ ] Covered by tests at the graph-runner seam with replayed judge responses

## Blocked by

- #7
