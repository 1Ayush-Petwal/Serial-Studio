---
number: 11
title: "Tracer: approved script to MP3 with Kokoro, approved at gate 4 (CLI)"
state: open
labels: [ready-for-agent]
url: https://github.com/1Ayush-Petwal/Serial-Studio/issues/11
created: 2026-11-07T19:45:56Z
updated: 2026-11-07T19:45:56Z
---

# #11 Tracer: approved script to MP3 with Kokoro, approved at gate 4 (CLI)

## Parent

#1

## What to build

First audio path. The Performance Director gives each line speaker, emotion (limited to the speech-emotion model's classes), intensity, pace and pauses. Lines are rendered with Kokoro on a Modal CPU function using the cast from gate 2, given word timestamps, and the timing solver lays out a voice-only timeline with pauses from the director's labels (dramatic pauses protected). The mixer renders the MP3 at -16 LUFS. The episode pauses at gate 4, where the editor listens and approves or rejects.

## Acceptance criteria

- [ ] An approved episode produces an MP3 of 120 seconds or less at about -16 LUFS
- [ ] Every script line appears in the timeline in order with director-labelled pauses
- [ ] Gate 4 approve and reject work from the CLI
- [ ] Covered by tests at the audio-timeline seam with synthetic fixtures

## Blocked by

- #7
