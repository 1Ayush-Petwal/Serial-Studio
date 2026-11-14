---
number: 19
title: "Ship: EC2 deploy, README with eval numbers, cost per minute and sample season"
state: open
labels: [ready-for-agent]
url: https://github.com/1Ayush-Petwal/Serial-Studio/issues/19
created: 2026-11-07T19:46:13Z
updated: 2026-11-07T19:46:13Z
---

# #19 Ship: EC2 deploy, README with eval numbers, cost per minute and sample season

## Parent

#1

## What to build

Move the web app to EC2 on the AWS free plan pointing at the same database, keep S3 for audio, confirm the AWS budget alarm and Modal spending limit, and write the README: eval report (critic-human agreement, A/B win rate, timing test), cost per finished audio minute, known ceilings (calibration on one story), and a link to a published sample season.

## Acceptance criteria

- [ ] Season page is served from EC2 with no code changes from Render
- [ ] README numbers are filled in from stored results, not typed by hand
- [ ] A full season of one story is published with report cards
- [ ] Total cash spent is under $10 and reported

## Blocked by

- #10
- #16
- #17
- #18
