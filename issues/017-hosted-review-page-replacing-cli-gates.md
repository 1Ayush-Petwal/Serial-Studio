---
number: 17
title: "Hosted review page replacing CLI gates"
state: open
labels: [ready-for-agent]
url: https://github.com/1Ayush-Petwal/Serial-Studio/issues/17
created: 2026-11-07T19:46:09Z
updated: 2026-11-07T19:46:09Z
---

# #17 Hosted review page replacing CLI gates

## Parent

#1

## What to build

Token-gated review routes in the same web app as the season page, deployed on Render free. They list pending items at all four gates and let the editor approve or reject with notes (and structured nudges at gate 4). Gate 3 shows the script with clue spans highlighted, the previous cliffhanger next to this hook, predicted runtime and the report card; gate 4 plays the MP3. A decision writes a row; the runner reads it and resumes the graph. The runner never runs on Render.

## Acceptance criteria

- [ ] Review routes reject requests without the token
- [ ] Approve and reject at each gate write the correct decision row and the runner resumes
- [ ] In-order approval at gate 3 is enforced in the UI and server-side
- [ ] Gate 3 view shows clue spans and the previous cliffhanger side by side
- [ ] Deployed on Render and usable from a phone-width screen
- [ ] Covered by tests at the web-app seam

## Blocked by

- #8
- #11
