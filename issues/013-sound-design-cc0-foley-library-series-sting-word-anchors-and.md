---
number: 13
title: "Sound design: CC0 Foley library, series sting, word anchors and ducking"
state: open
labels: [ready-for-agent]
url: https://github.com/1Ayush-Petwal/Serial-Studio/issues/13
created: 2026-11-07T19:46:00Z
updated: 2026-11-07T19:46:00Z
---

# #13 Sound design: CC0 Foley library, series sting, word anchors and ducking

## Parent

#1

## What to build

Build a library of 20-30 Freesound CC0 Foley clips with a licence manifest (IDs, licence) and tags embedded in pgvector, plus one series sting with 2-3 variants (code-generated stings as backup). The Sound Designer anchors one sting and up to 3 Foley cues to words, beats or the end of the last line, with a role (hit, bed, sting); Foley is chosen by embedding search, the sting variant from the tension curve. The timing solver snaps cues to anchor words and the mixer ducks music under speech.

Human step: the editor tags the clips with the agent.

## Acceptance criteria

- [ ] Library manifest lists every clip with its Freesound ID and CC0 licence
- [ ] Each episode has exactly one sting and at most 3 Foley cues
- [ ] Each Foley cue starts within tolerance of its anchor word in the timeline
- [ ] Music gain is reduced under speech
- [ ] Covered by tests at the audio-timeline seam

## Blocked by

- #11
