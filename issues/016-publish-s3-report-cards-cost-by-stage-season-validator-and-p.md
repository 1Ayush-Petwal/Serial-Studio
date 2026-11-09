---
number: 16
title: "Publish: S3, report cards, cost by stage, season validator and public season page"
state: open
labels: [ready-for-agent]
url: https://github.com/1Ayush-Petwal/Serial-Studio/issues/16
created: 2026-11-07T19:46:06Z
updated: 2026-11-07T19:46:06Z
---

# #16 Publish: S3, report cards, cost by stage, season validator and public season page

## Parent

#1

## What to build

After gate 4, upload the MP3 and script to S3 and store the report card and cost lines. After the last episode, a season-level validator confirms every clue was planted before the reveal and every opened thread is closed. A public, read-only season page lists episodes with title, two-line blurb, player, script, report card and cost per finished audio minute (shadow cost at list prices by stage, first-run, including rejected drafts and retakes, with cash spent alongside).

## Acceptance criteria

- [ ] Approved episodes appear on the season page with player, script, blurb and report card
- [ ] Season validator fails a season with a clue planted after its reveal
- [ ] Cost per finished minute is shown by stage, with cache hits reported separately and cash spent alongside
- [ ] Season page is read-only and needs no token
- [ ] Covered by tests at the web-app seam

## Blocked by

- #8
- #11
