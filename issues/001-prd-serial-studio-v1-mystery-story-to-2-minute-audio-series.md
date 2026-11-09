---
number: 1
title: "PRD: Serial Studio v1 - mystery story to 2-minute audio series"
state: open
labels: [ready-for-agent]
url: https://github.com/1Ayush-Petwal/Serial-Studio/issues/1
created: 2026-11-07T19:34:01Z
updated: 2026-11-07T19:34:01Z
---

# #1 PRD: Serial Studio v1 - mystery story to 2-minute audio series

## Problem Statement

Audio platforms like Kuku FM need a steady supply of short episodic audio shows at low cost. Adapting a story by hand into a serial is slow. A one-shot LLM adaptation is fast but flat: clues get dropped, episodes end at random points, prose is written for the eye instead of the ear, and the audio is just text-to-speech stitched together with no direction. Voice is the easy part; what makes an audio story work is what happens between the words: the pause before a reveal, a sound effect landing on the right word, music that rises without drowning the voice, a cliffhanger that makes the listener come back.

An editor on a content team wants to turn a public-domain mystery short story into a ready-to-publish audio series without writing it themselves, while staying in control of taste at the moments that matter.

## Solution

Serial Studio turns a Project Gutenberg mystery short story into a season of 5-7 audio episodes, each at most 2 minutes, with one narrator, light dialogue from 2-3 character voices, one music sting and up to 3 Foley cues. Each episode opens with a hook (stakes within 10 seconds, plus a one-line recap from episode 2 on) and ends on a cliffhanger.

A set of agents handles understanding the story (the story bible and clue ledger), planning the season, writing scripts, checking them and directing the audio. Hard rules are checked in code; taste is checked by a critique panel calibrated against the editor's own ratings. The editor approves at four human gates: the bible, the season plan and casting, each script, and each final mix. Every published episode comes with a report card (fidelity, craft, timing and audio scores, what was revised and why) and a cost per finished audio minute.

Mysteries are the genre because they have a checkable structure: every clue the solution depends on must reach the listener before the reveal (fair play). That gives the quality loop a hard, testable rule.

## User Stories

### Ingestion
1. As an editor, I want to pick a story from Project Gutenberg by title, so that I can start a series without preparing the text myself.
2. As an editor, I want the Gutenberg licence header and footer removed, so that boilerplate never leaks into a script.
3. As an editor, I want hard line-wraps repaired and footnotes handled, so that the source reads as clean prose.
4. As an editor, I want a single story extracted from an anthology by its boundaries, so that I can adapt one story from a collection.
5. As an editor, I want duplicate copies of the same story across anthologies detected, so that the catalogue has one canonical copy per story with the others recorded as lineage.
6. As an operator, I want the cleanest edition chosen as canonical, so that extraction works from the best text.

### Story bible and clue ledger (gate 1)
7. As an editor, I want a story bible with characters, aliases, facts, places and open threads, so that every agent writes against one shared truth.
8. As an editor, I want a clue ledger listing every clue the solution depends on, so that fair play can be checked.
9. As an editor, I want each clue to carry 2-4 must-hear keywords, so that the system can verify the listener actually hears it.
10. As an editor, I want clues made of an absence (the dog that did not bark) captured with keywords that encode the absence, so that subtle clues are not lost.
11. As an editor, I want each clue to record where it appears in the source, so that planning can place it sensibly.
12. As an editor, I want the bible built scene by scene, so that small mid-story details are not dropped.
13. As an editor, I want to review and approve the bible and clue ledger, so that wrong facts or keywords do not poison every later check.
14. As an editor, I want to reject the bible with notes, so that the Story Architect revises it rather than me editing JSON.
15. As an editor, I want the bible versioned, so that every script records which version it was written against.
16. As an editor, I want a pronunciation entry for unusual names in the bible, so that voices say them correctly.

### Season plan and casting (gate 2)
17. As an editor, I want the story split into 5-7 episodes (target 6) at real turns in the plot, so that every cliffhanger lands on a genuine moment rather than mid-scene.
18. As an editor, I want each episode to have a beat sheet of 3-5 beats (hook, turn, cliffhanger), so that every episode has a shape.
19. As an editor, I want every clue assigned to an episode before the reveal, so that the season is fair play by design.
20. As an editor, I want each cliffhanger written as a concrete event with keywords, so that the next episode's hook can be checked against it.
21. As an editor, I want the plan to state what the listener knows at the start of each episode, so that episodes can be written in parallel without contradicting each other.
22. As an editor, I want to choose a voice for each character and a separate narrator voice, so that the cast fits the show and stays fixed across the season.
23. As an editor, I want to approve or reject the season plan and casting with notes, so that the highest-leverage decision in the show is mine.

### Scripts (gate 3)
24. As an editor, I want each episode script around 260 words and never over 300, so that it fits a 2-minute episode with room for pauses and sound.
25. As an editor, I want scripts written as narration with light dialogue and speaker tags, so that they are performable by one narrator and a small cast.
26. As an editor, I want sound-cue markers in the script, so that sound placement is anchored to words.
27. As an editor, I want clue lines marked in the script, so that I can see each planned clue landing.
28. As an editor, I want episodes from 2 on to open with a one-line narrator recap, so that a listener arriving cold is oriented.
29. As an editor, I want each episode's opening to pick up the previous episode's cliffhanger, so that the seams between episodes hold.
30. As an editor, I want a predicted runtime shown for each script, so that I know it fits before any audio is rendered.
31. As an editor, I want scripts that exceed the predicted runtime limit sent back before they reach me, so that I never approve something that cannot fit.
32. As an editor, I want word count, clue placement, seams, names and facts and cue markers checked in code, so that hard rules never depend on an LLM's opinion.
33. As an editor, I want trivial slips such as a misspelled character name fixed automatically, so that I am not bothered with them.
34. As an editor, I want a critique panel to score tone, character voice distinctiveness, structure (hook, beats, cliffhanger) and "can you hear it", so that craft problems are caught before I read.
35. As an editor, I want critique notes ranked by a lead critic and turned into targeted revision notes, so that revisions fix the most important problem first.
36. As an editor, I want at most 2 automatic revisions before a script comes to me, so that runs do not loop forever.
37. As an editor, I want every script to come with a report card of scores and what was revised and why, so that I can judge quickly.
38. As an editor, I want to read episodes in any order but approve them strictly in episode order, so that what the listener knows after each episode is fixed before I sign off on the next.
39. As an editor, I want approving an episode to re-validate the later drafts, so that a change I accept does not silently break a later seam or clue.
40. As an editor, I want to reject a script with notes and have it go back to the Screenplay agent, so that I direct the rewrite without writing it.
41. As an editor, I want the review screen to show clue spans and the previous cliffhanger next to this hook, so that I check the things critics are weakest at.

### Audio direction and mix (gate 4)
42. As an editor, I want each line given an emotion, intensity, pace and pauses, so that the performance follows a tension curve.
43. As an editor, I want dramatic pauses respected, so that reveals have room to land.
44. As an editor, I want character voices distinct from each other and from the narrator, so that a listener can tell who is speaking.
45. As an editor, I want key lines rendered as 2-3 takes with the best one chosen automatically, so that important moments sound their best.
46. As an editor, I want unchanged lines reused when a script is revised, so that a revision re-renders only what changed.
47. As an editor, I want Foley cues anchored to specific words or beats, so that a sound effect never lands late.
48. As an editor, I want one series sting with a few variants chosen by the tension curve, so that the show has a sonic logo listeners learn.
49. As an editor, I want music ducked under speech, so that it never competes with the voice.
50. As an editor, I want every episode at most 120 seconds and normalised to -16 LUFS, so that it meets platform norms.
51. As an editor, I want the system to fit an episode into 120 seconds by shortening ordinary pauses first, then gently time-stretching narration, and only then cutting words, so that the cheapest fix is always tried first.
52. As an editor, I want any word cut after approval to come back to me as a small diff, so that the published audio always matches what I approved.
53. As an editor, I want to listen to the final mix and approve or reject it, so that timing taste is mine.
54. As an editor, I want to give structured timing nudges such as "sting 300 ms later", so that small fixes are applied exactly without another LLM pass.
55. As an editor, I want Audio QA to check dropped or mispronounced words, naturalness, loudness, pace, duration, hook timing, cue sync, speech masking by music and emotion direction, so that technical problems are caught before I listen.
56. As an editor, I want an episode that fails Audio QA re-rendered automatically where possible, so that I only hear candidates that pass.

### Publishing and the season page
57. As an editor, I want each approved episode published with its MP3, script, title, two-line blurb and report card, so that it is ready to ship.
58. As a listener or stakeholder, I want a public season page with the episode list, player, blurbs and report cards, so that I can hear and evaluate the result without access to the pipeline.
59. As an editor, I want the review pages protected by a token, so that nobody else can approve or reject.
60. As an editor, I want to approve from a hosted page while the pipeline runs elsewhere, so that I am not tied to the machine running it.
61. As an operator, I want a paused or crashed run to resume exactly where it stopped, so that no work or approvals are lost.
62. As an editor, I want the Story Architect to record what each approved episode established, so that the bible reflects the show as written, not only as planned.
63. As an editor, I want a season-level check after the last episode that every clue was planted before the reveal and every opened thread was closed, so that the season is fair play end to end.

### Quality, evaluation and cost
64. As an editor, I want to score a mixed set of about 20 episodes (finals, first drafts, baseline outputs and my own reference adaptations), so that critic thresholds are calibrated to my taste.
65. As an editor, I want critics not to gate anything until thresholds are set from my scores, so that uncalibrated judges do not block good work.
66. As an editor, I want critic-to-human agreement reported, so that I know how far to trust the critics.
67. As a stakeholder, I want the pipeline compared against a single-prompt baseline in blind head-to-head tests with positions swapped, so that I know the pipeline is actually better.
68. As a stakeholder, I want the head-to-head text judging done by a model family not used anywhere in the loop, so that the result is not biased toward the judge the loop was tuned on.
69. As an editor, I want to judge a small set of audio pairs blind myself, so that the automated A/B number is sanity-checked by a human.
70. As a stakeholder, I want a blind listening test of solver timing against evenly spaced pauses, so that timing taste is measured.
71. As a stakeholder, I want cost per finished audio minute at list prices, split by stage and including rejected drafts and retakes, with cash spent shown alongside, so that the number transfers to a real platform.
72. As an operator, I want every model call traced with latency, tokens and GPU time, so that I can find slow or expensive stages.
73. As an operator, I want every model call cached by model, prompt, parameters and prompt version, so that re-runs are free and a prompt change actually re-runs.
74. As an operator, I want every prompt version re-run on the gold set, so that a regression is caught before it ships.

### Operations and budget
75. As an operator, I want total spend kept at $0 expected and $10 maximum, with spending limits on every paid platform, so that there are no surprise bills.
76. As an operator, I want the judge model swappable by configuration, so that the day-one stand-in can be replaced by the final judge without code changes.
77. As an operator, I want the runner, database and web app to be independent so the app can move from its free host to EC2 without code changes, so that hosting is a deployment detail.
78. As an operator, I want every stage hand-off typed and validated, so that malformed input fails loudly instead of being guessed at.
79. As an operator, I want secrets kept only in a git-ignored environment file with a committed example, so that keys never reach the repository.

## Implementation Decisions

Settled decisions are numbered in the project brief's decision log (1-38). This PRD summarises them.

**Modules**
- **Ingest:** Gutendex client, text cleaning (licence strip, line-wrap repair, footnotes), story boundary detection, near-duplicate detection (MinHash on 5-word shingles, Jaccard 0.8 or above means the same story; cleanest edition is canonical, others stored as lineage).
- **Story Architect:** the only writer to the bible. Extracts scene by scene: each call receives one scene chunk plus the current bible and returns a delta; code merges and dedupes by name and alias. Bible is versioned and stored in Postgres with pgvector. After each approval, records what the episode established and flags later drafts for re-validation.
- **Beat Planner:** season plan (5-7 episodes), beat sheets, clue placement, cliffhanger events with keywords, "listener knows at start of episode N", recap for episodes 2 and later, casting.
- **Screenplay agent:** script with narration, light dialogue, speaker tags, sound-cue markers and clue markers.
- **Validators (pure code):** word count (target about 260, cap 300), predicted runtime (110 seconds or less, from per-voice words per minute plus the pause table plus sting tail), clue markers present in the planned episode with keywords inside the span and before the reveal, seam keywords in the first part of the next episode, names and facts against the bible, cue-marker well-formedness, trivial auto-fixes.
- **Critique panel:** one LangGraph node running a CrewAI crew (Tone, Character, Structure, Ear critics and a lead critic) with one typed input and one typed output. Produces scores and ranked notes. Before calibration it does not gate; the revise loop runs on validator violations and the lead critic's must-fix notes. Max 2 revisions.
- **Graph runner:** LangGraph owns typed shared state, Send API fan-out per episode, a Postgres checkpointer, and four interrupts (gates). A run starts on a story and resumes when a decision row appears.
- **Performance Director:** per-line speaker, emotion, intensity, pace, pauses. Emotion is intent only; a code table maps emotion, intensity and pace to engine exaggeration, guidance weight and pause lengths. Emotion vocabulary is limited to the speech-emotion model's classes.
- **Voice rendering:** Chatterbox on Modal GPU for final renders; Kokoro on a Modal CPU function as fallback and for drafts. Chatterbox reference clips are rendered from Kokoro's built-in voices so the cast is synthetic, licence-clean and identical under fallback. Narrator is separate from Watson. Line-level caching; 2-3 takes for key moments, best chosen on round-trip WER, predicted naturalness and fit to time budget.
- **Alignment:** Whisper word-level timestamps per take.
- **Sound Designer:** anchors one sting and up to 3 Foley cues to words, beats or the end of the last line, with a role (hit, bed, sting). Foley chosen by embedding search over a tagged library of 20-30 Freesound CC0 clips with a licence manifest. The sting is one series family with 2-3 variants chosen from the tension curve; code-generated stings are the backup.
- **Timing solver (pure code):** resolves anchors into a timeline with voice, SFX and music tracks (start, end, gain, fades). Fit-to-120-seconds order: shorten ordinary pauses (dramatic pauses protected), then time-stretch narration without pitch change (never climax lines, max stretch tuned by ear), then request a word cut that returns to the editor as a diff. Applies structured timing nudges from gate 4.
- **Mixer:** ffmpeg render with ducking, fades, -16 LUFS normalisation, MP3 output.
- **Audio QA:** round-trip WER, predicted MOS, loudness, pace, long silences, duration, hook timing, cue-to-anchor offset, WER of mix against dry voice (masking), emotion match gated on intensity direction rather than exact class.
- **Publish:** uploads to S3, stores report card and cost lines, triggers the Story Architect update, runs the season-level validator after the last episode.
- **Web app:** one FastAPI app, server-rendered, no mode flag. Review routes are token-gated and write decision rows; season routes are public and read-only. Runs on Render free now and EC2 later.
- **Model gateway:** every external model call (writer, judge, TTS, alignment, emotion, MOS) goes through one interface that caches by model, prompt or input, parameters and prompt version, logs to Langfuse, and records tokens and GPU-seconds for shadow cost.
- **Evals:** gold-set calibration, critic agreement (Spearman and percent within one point), single-prompt baseline generator, A/B harness, timing-taste listening test.

**Models and infrastructure**
- Writer: Gemini Flash free tier; Groq free tier as second provider.
- Judge and extraction: a Groq-hosted non-Google model on day 1; Qwen3-8B 4-bit AWQ on vLLM on a Modal T4 from day 2 (fallbacks Llama 3.1 8B AWQ, then Mistral 7B); bibles re-extracted on the final judge.
- A/B text judge: a third model family on Groq, never used in the loop or as the day-1 judge.
- Database: Supabase free (Postgres, pgvector, checkpointer); docker-compose Postgres locally for tests.
- Runner: laptop or Modal. Web app: Render free, EC2 later. Storage: S3. Tracing: Langfuse free.

**Human gates**

| Gate | When | Reject goes to |
|---|---|---|
| 1. Bible and clue ledger | once per story | Story Architect |
| 2. Season plan and casting | once per story | Beat Planner |
| 3. Script | per episode, approved strictly in order | Screenplay agent |
| 4. Final mix | per episode, any order, structured nudges applied by code | Timing solver or Sound Designer |

All gates share one mechanism: interrupt, review page, decision row, runner resumes.

**Schemas (typed hand-offs, defined before the code that uses them)**
Story, bible (characters, aliases, facts, pronunciations, voice per character), clue (id, text, source position, must-hear keywords, assigned episode, reveal episode), open thread, season plan, beat sheet (beats, cliffhanger event with keywords, recap, listener-knows state), script (lines with speaker, clue spans, cue markers, bible version), violation, critique notes, performance sheet, cue list, timeline, decision row (gate, target, approve or reject, notes, structured nudges), report card, shadow-cost line (stage, provider, units, list price, cache hit).

**Cost metric**
Shadow cost at public list prices, first-run (cache hits reported separately), split by stage (text, judge, voice, QA), including rejected drafts and retakes; cash spent reported alongside.

## Testing Decisions

A good test exercises external behaviour through a public seam and asserts on outcomes a user would see (gate payloads, routing, published artifacts, timeline numbers), not on internal calls or intermediate data shapes. Tests must be deterministic and free to run.

**Seams (three in total)**
1. **Graph runner (primary).** Start a story run and resume with decisions against a test Postgres. All external model calls go through the model gateway, whose cache doubles as a record/replay store, so tests replay recorded responses. Assertions cover: ingestion output and duplicate detection, the payload at each of the four gates, routing of rejections to the owning agent, max-2 revision loop, in-order approval at gate 3, re-validation of later drafts after approval, validator violations (word count, runtime, clue markers and keywords, seams, names and facts, cue markers), resume after a simulated crash, the published season, report card and shadow-cost lines, and the season-level fair-play check. Validators and the runtime estimator are pure code and are covered through this seam, not tested in isolation.
2. **Audio timeline.** Input a performance sheet, rendered takes with word timestamps, and a cue list; output a timeline and MP3. Assertions: duration 120 seconds or less, cue-to-anchor-word offsets within tolerance, the fit tiers firing in order (pauses, then stretch, then word-cut request), dramatic pauses and climax lines protected, structured nudges applied exactly, ducking present under speech, -16 LUFS output. Uses short synthetic audio fixtures.
3. **Web app over HTTP.** Review routes reject requests without the token and write the correct decision row; in-order approval is enforced; season routes are public and read-only.

**Prior art:** none yet; the repository has no code. These seams set the pattern for later tests.

## Out of Scope

- Video, storyboards, image and video models.
- Hindi or any language other than English (v2).
- AI-generated music (v2).
- Voice cloning of real people.
- Copyrighted sources, web novels, and longer novels split into seasons (v2).
- Full-cast drama; the format is one narrator with light dialogue.
- Batch runs over a whole catalogue (v2).
- A/B testing of prompt versions and voice consistency across series (v2).
- Real listener analytics.
- Triggering pipeline runs from the hosted page; it reviews and plays only.
- A Node.js front end.
- AWS GPU instances.

## Further Notes

- Build window is 7 days from 2026-11-07; day 1 has already slipped, and scope is held with no cuts, so ordering risk is the main schedule risk. Day-slip fallback: the review page drops to a CLI first, then the demo drops to one story. The public season page stays.
- Demo set: The Speckled Band, The Red-Headed League, Silver Blaze. Calibration uses one story (likely The Speckled Band); this ceiling is reported in the README.
- Free-tier ceilings to watch: Gemini daily quota, Supabase pausing after about 7 idle days, Render free spin-down and about 512 MB RAM (page only, never the runner), Modal $30 monthly credit with a spending limit.
- Still to verify, not decide: Gemini limits fit the workload; Qwen3-8B AWQ loads on a T4 with usable throughput; Chatterbox render speed on a T4; Groq stand-in judge choice.
- Work proceeds as one branch and pull request per build step in the brief.
