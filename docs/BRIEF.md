# Serial Studio — Project Brief (v2, final plan)

Give this whole file to Claude Code at the start of a session (for example, save it as `CLAUDE.md` or `docs/BRIEF.md` in the repo and point Claude at it). It holds every decision made during ideation and planning. Treat the **Decision log** (section 10) as settled unless I explicitly reopen something.

**Repo:** https://github.com/1Ayush-Petwal/Serial-Studio (local clone is the working copy)
**Build window:** 7 days, starting 2026-11-07 (day 1 = today).

### Status at handover
| Item | State |
|---|---|
| Repo (local + GitHub mirror) | Created, being set up |
| AWS account | Set up. Budget alarm still to confirm on day 1 |
| Gemini API key | Being added to `.env` |
| Langfuse keys | Being added to `.env` |
| Modal account | **Day 2.** Must exist, with a spending limit, before Qwen judge goes up |
| Supabase (Postgres + pgvector) | To create, day 1 |
| Render (review page host) | To create, by end of step 2 |
| Open questions (old section 13) | All resolved, see decisions 17–21 |
| Grilling session (2026-11-08) | Done, see decisions 22–38 |

---

## 0. Instructions for Claude

You are my engineering partner on Serial Studio. Help me build it in one week, following the day plan in section 11.

- Write clean, readable, typed Python. Use small modules, with tests for each pipeline stage.
- Before writing code for a stage, state its input and output schema (Pydantic).
- Prefer the simplest thing that works within the week. Flag anything that risks the $10 budget or the timeline.
- Don't reopen decisions in the Decision log unless I ask. If you think one is wrong, say so once, briefly, with the reason.
- On a creative judgment (tone, pacing, what makes a good cliffhanger), give the craft reason, not just the rule.
- Agents decide intent; code decides numbers and milliseconds. Don't use an LLM where a deterministic rule works.
- **How we work:** one feature branch per step in section 11 and a pull request for each, so I can review a step before the next one starts. Never commit secrets: keys live in `.env`, which is git-ignored, with a committed `.env.example`.
- At the end of each step, stop and list the decisions I need to confirm (the "You decide / You do" items in section 11) before moving on.

---

## 1. Product

**Serial Studio** (working name) turns a public-domain mystery short story into a ready-to-publish audiobook series. Every episode has one narrator and light dialogue, a hook in the first 10 seconds and a cliffhanger at the end, and runs **2 minutes at most**.

- **For:** the content team at an audio platform like Kuku FM, which needs many episodic shows at low cost. The editor reviews and approves; the system does the adapting.
- **Problem:** adapting by hand is slow. A one-shot LLM adaptation is valid but flat: clues get dropped, episodes end at random points, and the prose is written for the eye, not the ear.
- **Why mysteries:** they have a checkable structure. Every clue the solution depends on must reach the listener before the reveal (fair play), which gives the quality loop a hard, testable rule.
- **The hard engineering problem:** writing one script is easy. Orchestrating many independent agents to plan, generate, validate and assemble coherent episodes, without characters, clues and continuity falling apart, is the real work. The second hard problem is **timing** in the audio.

**Each episode produces:**
1. A narration script with light dialogue, speaker tags and sound-cue markers (about 260 words, 300 at most)
2. A 2-minute MP3: one narrator voice, 2–3 character voices, one music sting and up to 3 Foley cues
3. An episode title and a two-line hook blurb
4. A quality report card: fidelity, craft, timing and audio scores, plus what was revised and why

**Success metrics:**
- Cost per finished audio minute, reported per episode
- The full pipeline beats a single-prompt baseline in blind head-to-head judging
- The automated critics agree with my own ratings on a hand-scored gold set

---

## 2. Scope

| Area | v1 (this week) | v2 | Out of scope |
|---|---|---|---|
| Source | Project Gutenberg mystery short stories, English | Longer novels split into seasons | Copyrighted web novels |
| Text output | Narration script with light dialogue, title, hook blurb | Hindi script as cultural adaptation, not literal translation | — |
| Audio output | Narrator + 2–3 character voices; 1 music sting + up to 3 Foley cues from a CC0 library; MP3, loudness-normalized, ≤ 2 min | Hindi voices; AI-generated music | Voice cloning of real people |
| Quality | Validators, critique panel, revise loop, timing checks, gold set I hand-score | A/B testing of prompt versions; voice consistency across episodes | Real listener analytics |
| Product surface | FastAPI + minimal review page (approve / reject with notes) | Batch runs over a whole catalogue | Node.js front end |
| Video | — | — | Storyboards, image and video models |

**Episode length:** about 2 minutes, never more. At ~150 words a minute, scripts aim for ~260 words with a hard cap of 300, leaving room for pauses and sound cues. Length is checked before voicing and again after mixing.

---

## 3. System architecture

```
Ingest ──► Story Architect ──► Plan & write ──► Quality gate ──(approved)──┐
(Gutendex,   (bible, clue        (Beat Planner,   (critique panel,         │
 clean,       ledger, pgvector)   Screenplay,      fair-play check,        │
 near-dup)                        validators)      my approval)            │
                    ▲                  ▲  └──── revise, max 2 ◄────┘       │
                    │                                                      ▼
                    │       Eval log ◄── Publish ◄── Audio checks ◄── Audio direction
                    │                    (S3, report  (Whisper, MOS,    (emotion per line,
                    └─── bible update ─── card)        loudness,         music sting, Foley,
                                                       duration)         mix, 120 s cap)

Shared infrastructure: Free LLM API (writer) · vLLM + Chatterbox + Kokoro on Modal (judge,
extraction, voice) · Supabase (Postgres+pgvector, checkpointer) · Render free, later EC2
(FastAPI review + season pages) · graph runner on laptop or Modal · S3 · Langfuse
(traces, cost, latency). See decisions 30-31.
```

---

## 4. Agent design

Each agent has one job: understanding the story, planning it, writing it, or checking the others. **LangGraph** owns the flow, the typed shared state, per-episode fan-out, the review pause and checkpointing. **CrewAI** runs only the critique panel, as one LangGraph node with typed input and output.

```
Story Architect ─► Beat Planner ─► Screenplay agent ─► Validators ──pass──► Critique panel (CrewAI)
      ▲                                  ▲    ▲            │ violations          │ notes, max 2
      │                                  │    └────────────┘                     │
      │                                  └───────────────────────────────────────┘
      │                                                                          │ notes resolved
      │                                                                          ▼
      │   Publish ◄─ Audio QA ◄─ Timing solver & Mixer ◄─ Sound Designer ◄─ Performance Director ◄─ My review (interrupt)
      │      │                                                                          (reject with notes → Screenplay)
      └──────┘  after approval, the Story Architect records what the episode established
```

| Role | Agent | Job | Model / tool | Hands on |
|---|---|---|---|---|
| Understand | **Story Architect** | Owns story, character and world context: bible, clue ledger (with must-hear keywords per clue), what the listener knows after each episode, open threads. The only agent that writes to the bible. Extracts scene by scene (decision 23) | Judge model, structured output; pgvector | New bible version |
| Plan | **Beat Planner** | Splits the story into a season; 3–5 beats per 2-min episode (hook, turn, cliffhanger); places every clue | Writer model | Season plan, beat sheets |
| Generate | **Screenplay agent** | Narration, light dialogue, speaker tags, sound-cue markers; ~260 words, ≤ 300 | Writer model | Script |
| Validate | **Validators** | Hard rules in code: word count, clue planted where planned, names/facts vs bible, well-formed cue markers; auto-fixes trivial slips (misspelled name) | Code + bible lookups | Pass, or list of violations |
| Critique | **Critique panel (CrewAI)** | Tone, Character, Structure (hook, beats, cliffhanger) and Ear ("can you hear it?") critics; a lead critic ranks notes | Judge model on Modal | Scores + ranked notes |
| Approve | **My review** | 4 LangGraph interrupts (see Human gates below); approve, or reject with notes to the owning agent | Review page | Approved output |
| Audio | **Performance Director** | Emotional beat map; emotion, intensity, pace and pauses per line | Writer model | Performance sheet |
| Audio | **Sound Designer** | Anchors 1 music sting + ≤ 3 Foley cues to words/beats; picks clips from tagged CC0 library | Embedding search in pgvector | Cue list |
| Audio | **Timing solver & Mixer** | Renders lines, resolves word anchors into a timeline, ducks music under speech, enforces 120 s cap | Chatterbox on Modal, Whisper alignment, ffmpeg | MP3 |
| Audio | **Audio QA** | Round-trip transcription, naturalness, loudness, duration, timing checks | Whisper, UTMOS, emotion model | Pass, or re-render |
| Close | **Publish** | Uploads; stores report card in eval log; triggers Story Architect update | S3, Postgres | Report card |

### Human gates (decision 33)
All gates use one mechanism: LangGraph interrupt -> `/review` page -> decision row in Postgres -> runner resumes the graph. Reject-with-notes routes to the agent that owns the output.

| # | Gate | When | Reject goes to |
|---|---|---|---|
| 1 | Bible + clue ledger (incl. keywords) | once per story | Story Architect |
| 2 | Season plan + casting (voice per character) | once per story | Beat Planner |
| 3 | Script (with est. duration) | per episode, approved strictly in episode order (decision 38) | Screenplay |
| 4 | Final mix | per episode, any order; structured timing nudges applied by code (decision 34) | Timing solver or Sound Designer |

### How coherence holds at scale
1. **One writer of truth.** Only the Story Architect writes to the bible; every other agent reads it through a tool. Each script records the bible version it was written against.
2. **Plan the season, then write in parallel.** The Beat Planner fixes the whole season up front, including what the listener should know at the start of each episode and each cliffhanger as a concrete event with keywords. Ep N+1's beat sheet gets ep N's cliffhanger event; a validator checks the seam (decision 25). LangGraph's Send API fans out one branch per episode.
3. **Reconcile after every episode.** When I approve an episode, the Story Architect compares what was written with the plan. If they differ (a clue moved, a secret revealed early), later drafts are re-validated.
4. **Typed hand-offs.** Every hand-off is a Pydantic schema. A stage that gets malformed input fails loudly instead of guessing.
5. **Season-level checks.** After the last episode, a season validator confirms every clue is planted before the reveal and every opened thread is closed.

**Shared state** (one typed object): story id, bible version, season plan, current episode, beat sheet, script, violations, critique notes, revision count, approval, audio location. A **Postgres checkpointer** saves it after every node, so a paused or crashed run resumes where it stopped.

---

## 5. Audio generation and timing

**Rule:** agents decide intent (which emotion, which cue, where it goes); code decides milliseconds. Everything is placed relative to **words**, not clock times, and one solver resolves anchors into a timeline.

1. **Emotional beat map (Performance Director).** Every beat gets an emotion and an intensity (0–1), giving a tension curve. Every line gets speaker, emotion, intensity, pace (slow / normal / urgent) and pause before/after (none / short / beat / dramatic). Emotion is intent, not an engine input: a code table maps (emotion, intensity, pace) to exaggeration, cfg and pauses. Emotion vocabulary is limited to the speech-emotion model's classes (decision 28).
2. **Line performance.** Each line is rendered on its own with **Chatterbox** on Modal: intensity → exaggeration, pace → cfg. Key moments get 2–3 takes; the best wins on round-trip WER, naturalness and fit to its time budget. Unchanged lines are cached, so a revision re-renders only what changed.
3. **Word timing.** Every take gets word-level timestamps from Whisper alignment (Kokoro gives them natively for English).
4. **Music and sound placement (Sound Designer).** Each cue is anchored to a word ("on *slammed*"), a beat ("under beat 3") or the end of the last line (cliffhanger sting), with a role: hit, bed under speech, or sting.
5. **Timing solver (code).** Resolves anchors into a timeline: one track each for voice, SFX and music; each clip has start, end, gain and fades. Pauses come from the director's labels; cues snap to anchor words.
6. **Mixer (code).** Renders with ffmpeg: ducks music under speech, applies fades, normalizes to -16 LUFS, writes the MP3.

**Why timing is hard:** a line's length is unknown until rendered, and emotion changes it (higher Chatterbox exaggeration tends to speed speech up). One retake shifts every cue after it — anchors make that a re-flow, not a rebuild. The 120 s cap forces trade-offs between dramatic pauses and words. A late sound effect reads as a mistake.

**Fitting into 120 seconds** — cheapest fix first:
1. Shorten ordinary pauses toward their minimum (dramatic pauses protected).
2. Time-stretch narration lines slightly without changing pitch (never climax lines; max stretch tuned by ear on day 5).
3. Send the script back to the Screenplay agent: "cut N words from the beat with the most slack". Should be rare: a validator predicts runtime before gate 3 (must estimate ≤ 110 s). If tier 3 fires, the cut returns to me as a small diff (decision 29).

**Voice engine decision:** Chatterbox (MIT, emotion-intensity control, GPU → Modal, output watermarked) for final renders. Kokoro-82M (Apache 2.0, CPU, speed control only, on a Modal CPU function) as fallback and for fast drafts.

**Casting (decision 27):** Chatterbox reference clips are rendered from Kokoro's built-in voices (e.g. `bm_george`, `bf_emma`), so the cast is synthetic and the Kokoro fallback sounds the same. Narrator is a separate voice from Watson. `character → voice_id` lives in the bible, fixed per season, chosen at gate 2.

---

## 6. Tech stack and budget

Expected spend **$0**; hard ceiling **$10**. No AWS GPU instances.

| Layer | Choice | Runs on | Cost |
|---|---|---|---|
| Orchestration | LangGraph; one CrewAI crew as the critique panel | Python app | $0 |
| Writer model | Free tier of a hosted LLM API (Gemini or Groq) | Provider | $0 |
| Judge & extraction model | 7–8B open model, 4-bit, served with vLLM — different model family from the writer | Modal serverless GPU (T4 ≈ $0.59/hr; $30/month free credit) | $0 within credit |
| Expressive voice | Chatterbox | Modal GPU | $0 within credit |
| Fallback voice | Kokoro-82M | Modal CPU function | $0 within credit |
| Sound | 20–30 Freesound CC0 Foley clips (manifest with IDs + licence) + one series sting family (3 variants), code-generated as backup | pgvector (Foley only) | $0 |
| Story memory + checkpointer | Postgres + pgvector | Supabase free (docker-compose locally for tests) | $0 |
| Audio checks | Whisper (small), UTMOS, an open speech-emotion model (e.g. emotion2vec) | Modal or CPU | $0 |
| API & review page | FastAPI + server-rendered page: `/review` (token-gated) + `/season` (public) | Render free now, EC2 later | $0 / AWS credits |
| Graph runner | LangGraph process, resumes on decision rows | Laptop or Modal | $0 |
| Storage | S3 (MP3s, scripts) | AWS | AWS credits |
| Tracing | Langfuse cloud, free tier; also logs tokens + GPU-seconds for shadow cost (decision 35) | Langfuse | $0 |

**AWS guardrails:** stay on the AWS free plan (it blocks xlarge+ instances, so no GPUs — don't upgrade to request GPU quota). The free plan ends after 6 months or when credits run out, so the EC2 host is a demo environment. Set an AWS budget alarm and a Modal spending limit on day 1.

---

## 7. Quality and taste

Taste is measured as **agreement with a human editor**. Critics are trusted only once their scores match mine on a hand-scored gold set. Validators are code and fail fast; critics are judges calibrated against my ratings.

| Check | Run by | Tested against | How it's scored |
|---|---|---|---|
| Plot coverage | Validator | Key events from the source | Share of key events present |
| Character facts | Validator | Story bible | Contradicted or invented facts per episode |
| Fair-play clues | Validator | Clue ledger | Every clue planted in its assigned episode, before the reveal |
| Episode length | Validator | 2-minute cap | Script ≤ 300 words; MP3 ≤ 120 s |
| Tone | Tone critic | Series tone notes + gold set | 1–5: mood and register match the series |
| Voice distinctiveness | Character critic | The script | Speaker names stripped; judge guesses the speaker; accuracy |
| Hook and cliffhanger | Structure critic | Rubric + gold set | 1–5: stakes in the first 10 s; pull of the ending |
| Can you hear it? | Ear critic | Audio-drama rubric | Count of beats that only work visually |
| Easy to follow by ear | Ear critic | Rubric | Sentence length, narrator/dialogue ratio, similar-sounding names |
| Overall preference | Offline eval | Single-prompt baseline | Blind head-to-head, positions swapped, win rate. Text pairs judged by a third-family Groq model; 6 audio pairs judged by me (decision 32) |
| Pronunciation / dropped lines | Audio QA | Script | Whisper WER on the MP3 |
| Naturalness | Audio QA | Open MOS model | Predicted MOS per episode |
| Loudness and pace | Audio QA | Listening norms | ~-16 LUFS; ~150 wpm; long silences flagged |
| Duration | Audio QA | Cap | ≤ 120 s |
| Hook timing | Audio QA | Real timeline | First stakes line starts within 10 s |
| Cue sync | Audio QA | Anchor words | Offset between each SFX and its anchor word |
| Speech under music | Audio QA | Dry voice track | WER of final mix vs dry voice; a rise = masking |
| Emotion match | Audio QA | Performance sheet | Speech-emotion model: heard vs directed, per line |
| Timing taste | Offline eval | Flat timing | Blind listening, 5 episodes: solver timing vs evenly spaced pauses |

**Calibration:** I hand-adapt 2–3 scenes as references and rate ~20 generated episodes. Critic–human agreement goes in the README. Pass thresholds are set from the gold set on day 3, not guessed. Before calibration, critics produce notes but don't gate; the loop runs on validator violations + the lead critic's must-fix notes. The 20 are deliberately mixed: 6 finals, 6 first drafts, 6 baseline, 2 references, one story, blind and shuffled. Thresholds: the cut that best separates my ≥ 4 from ≤ 2. Agreement: Spearman + % within 1 point (decision 26).

**Feedback loop:** a failed check becomes a targeted note ("lines 12–18 rely on a visual cue", "the torn-glove clue is never planted"). At most 2 revisions, then the script comes to me with its report card. Every prompt version is re-run on the gold set, so a regression is caught before it ships.

---

## 8. Ingestion details

- Fetch stories via the **Gutendex** API (Project Gutenberg).
- Strip the Gutenberg licence header/footer; repair hard line-wraps; detect chapters/story boundaries; handle footnotes.
- **Near-duplicate detection (MinHash)** — the same story appears in several anthologies.
- Demo genre: **mystery** (e.g. Sherlock Holmes short stories). Pick 3 stories for the demo set.

---

## 9. Suggested repo layout (starting point, not a decision)

```
serial-studio/
  ingest/        gutendex client, cleaning, dedup
  bible/         Story Architect, schemas, pgvector access
  graph/         LangGraph graph, state, checkpointer, nodes
  agents/        beat_planner, screenplay, critique_panel (CrewAI)
  validators/    rule checks (pure Python)
  audio/         performance, tts (chatterbox/kokoro), align, sound, timing_solver, mixer
  evals/         critics calibration, gold set, audio QA, baseline A/B
  serving/       modal apps (vllm, chatterbox, whisper)
  api/           FastAPI + review page
  infra/         docker-compose, EC2 setup, S3
  tests/
```

---

## 10. Decision log (settled)

| # | Decision | Reason |
|---|---|---|
| 1 | Product: text → audiobook series in a Kuku FM style; text and audio output only | Cheapest viable MVP; matches the target use case |
| 2 | Source: Project Gutenberg, mystery genre | Free, legal, messy enough to need real extraction; mysteries give a testable fair-play rule |
| 3 | Single narrator with light dialogue (not full-cast drama) | Closer to Kuku FM shows; simpler casting and mixing |
| 4 | English first; Hindi in v2 | Ship one language well in a week |
| 5 | No video | Budget and scope |
| 6 | Episodes ≤ 2 minutes (~260 words, cap 300) | Micro-format; cheaper renders and evals |
| 7 | Agent roles follow the head of AI/ML's design: Story Architect, Beat Planner, Screenplay, Critique & Validation, Audio agents | Separation of understanding, planning, generating and checking |
| 8 | LangGraph backbone; CrewAI only for the critique panel | One orchestrator owns state; CrewAI fits a role-based panel |
| 9 | Writer model: free hosted LLM API tier | $0 budget |
| 10 | Judge/extraction: 7–8B open model on vLLM on Modal, different family from the writer | Shows model serving; avoids self-preference bias |
| 11 | Final voice: Chatterbox on Modal; Kokoro as CPU fallback | Emotion control is needed for performance |
| 12 | Sound: 1 sting + ≤ 3 Foley cues per episode from a CC0 library | $0, high impact in a 2-min format |
| 13 | Timing: word-anchored cues; deterministic solver fits ≤ 120 s | Timing is the hardest audio problem; anchors survive retakes |
| 14 | No AWS GPU; stay on AWS free plan; budget ≤ $10 | Free plan blocks GPU instances; no surprise bills |
| 15 | Human review gate before any audio is rendered | Editor stays in control; saves render cost |
| 16 | Timeline: 1 week | Fixed |
| 17 | Demo set: three Sherlock Holmes stories, *The Speckled Band*, *The Red-Headed League* and *Silver Blaze*. Alternate if a second author is wanted: Chesterton's *The Blue Cross* | Speckled Band has the strongest fair-play clues and the most sound (whistle, clang, night vigil). Red-Headed League is a clean clue chain with a comic-to-tense tone shift that tests the Tone critic. Silver Blaze's "dog that didn't bark" is a clue made of an *absence*, a hard test for the clue ledger. Holmes stories recur across Gutenberg anthologies, which exercises near-dup detection |
| 18 | Episodes per story: target 6; the Beat Planner may choose 5–7 | Each ~9–10k-word story has ~5–7 natural turns. A cliffhanger must land on a real turn, so more episodes means padding or cutting mid-scene. 3 stories × 6 = ~18 episodes: enough for the gold set and well inside Modal credit |
| 19 | Writer model: Gemini Flash on the free tier; Groq free tier as second provider | Key already in hand. Verify current free-tier limits on day 1 against ~18 scripts × up to 3 drafts plus planning. Cache every LLM call so re-runs are free |
| 20 | Judge/extraction model: Qwen3-8B, 4-bit AWQ, on vLLM on a Modal T4 (max context ~8k). Fallbacks: Llama 3.1 8B AWQ, then Mistral 7B | Different family from Gemini (so not Gemma), avoiding self-preference bias. Strong structured JSON output for the Story Architect. Fits a T4's 16 GB in 4-bit. Confirm load and throughput on day 4 |
| 21 | Workflow: feature branch + PR per build step; secrets only in `.env` | Lets me review each step; keeps keys out of git |
| 22 | Scope held: text coherence and audio direction both ship, no cuts | Both are the product. Zero slack, so ordering bugs get fixed early |
| 23 | Story Architect extracts scene by scene: one chunk + current bible in, delta out; code merges and dedupes | 8B models drop mid-context details, and clues are small mid-story details. Also yields clue position for the Beat Planner |
| 24 | Clues planted via inline markers `[clue:id]...[/clue]` + 2-4 must-hear keywords per clue; markers stripped before TTS | Deterministic validator, precise revise notes, works for absence clues. Gaming is the critics' job to catch |
| 25 | Episode seams: Beat Planner writes each cliffhanger as an event with keywords; ep N+1's opening must hit them; ep 2+ opens with a 1-line narrator recap inside the word budget | A cliffhanger is a plan-level question, so the planner owns it and parallel writers execute it |
| 26 | Calibration: critics don't gate before thresholds exist; gold set of 20 is mixed quality from one story | Finals alone cluster at 3-4, leaving no variance to measure agreement |
| 27 | Voices: Chatterbox reference clips rendered from Kokoro built-in voices; narrator separate from Watson | Synthetic and licence-clean; fallback keeps the same cast; third-person narration stays clear in 2 min |
| 28 | Emotion is intent: code maps (emotion, intensity, pace) to exaggeration/cfg/pauses; emotion match reported, gated only on intensity direction | Chatterbox has no emotion input; classifier exact-class accuracy on TTS is noisy |
| 29 | Runtime predicted before gate 3 (≤ 110 s, per-voice wpm measured on day 4); tier-3 cuts return to me as a diff | Approved script and published audio must not diverge |
| 30 | Infra for the build: Supabase (Postgres + pgvector + checkpointer), Render free for the web app, graph runner on laptop or Modal, Kokoro on Modal CPU; EC2 later | State in hosted Postgres makes the runner portable; kills the EC2 OOM risk |
| 31 | One FastAPI app: `/review` (token-gated, writes decision rows) and `/season` (public, read-only). No mode flag | Same app on Render now and EC2 later |
| 32 | A/B: third-family Groq model (not used in the loop or day 1) judges text pairs; I judge 6 audio pairs; baseline uses the same TTS + mixer | Qwen is biased because the loop was tuned against it |
| 33 | Four human gates: bible, season plan + casting, script, final mix | Gates sit where one decision steers the most downstream work |
| 34 | Gate 4 takes structured timing nudges ("sting +300 ms") applied by code | Agents decide intent, code decides ms |
| 35 | Cost per minute = shadow cost at list prices, by stage, first-run, including rejected drafts and retakes; cash spent reported alongside | $0 on free tiers tells a platform nothing |
| 36 | Sound: Freesound CC0 Foley with a licence manifest; one series sting with 2-3 variants picked from the tension curve; code-generated stings as backup | The sting is the show's sonic logo; repetition is the point |
| 37 | Judge stand-in: a Groq-hosted non-Google model on day 1; Qwen3-8B on Modal from day 2; bible re-extracted on Qwen | Modal account arrives day 2; calibration must use the final judge |
| 38 | Script approvals strictly in episode order; reading in any order is fine | "What the listener knows after ep N" must be fixed before signing off ep N+1 |

---

## 11. Final implementation plan (4 steps over 7 days)

Each step ends with a check-in: Claude stops, summarizes what was built, and lists what I need to decide or do.

### Step 1 — Foundations, ingestion and the Story Architect (day 1)
- Scaffold the repo (layout in section 9), `pyproject.toml`, linting, pytest, `docker-compose` for Postgres + pgvector, `.env.example`.
- Pydantic schemas for every hand-off (story, bible, clue ledger, season plan, beat sheet, script, violations, critique notes, report card), defined before the code that uses them.
- Gutendex client; strip the Gutenberg licence header/footer; repair hard line-wraps; detect story boundaries in anthologies; handle footnotes; MinHash near-dup detection.
- Story Architect: scene-chunked extraction of bible, characters, clue ledger (with must-hear keywords and "listener knows after episode N"), open threads, stored in pgvector, versioned. Runs on the Groq stand-in judge today.
- Create Supabase project; docker-compose Postgres stays for tests.
- Check the Gemini free-tier limits against the workload; add the LLM call cache. Set the AWS budget alarm.
- **Done when:** the 3 demo stories ingest cleanly (with duplicate copies detected) and each has a bible and clue ledger, with tests passing.
- **You decide:** review the 3 bibles and clue ledgers for accuracy (gate 1, CLI for now).

### Step 2 — Text pipeline (days 2–3)
- Day 2 first: Modal account + spending limit; vLLM serving Qwen3-8B AWQ; swap judge; re-extract bibles on Qwen.
- Beat Planner: season plan (5–7 episodes, target 6) and beat sheets (3–5 beats each: hook, turn, cliffhanger as event + keywords, recap for ep 2+), placing every clue, plus casting. Gate 2.
- Screenplay agent: ~260 words, cap 300, narration + light dialogue, speaker tags, cue markers.
- LangGraph graph: typed shared state, Send-API fan-out per episode, Postgres checkpointer.
- Validators in code (word count, predicted runtime ≤ 110 s, clue markers + keywords, seams, names/facts vs bible, cue markers, trivial auto-fixes).
- CrewAI critique panel as one typed LangGraph node (Tone, Character, Structure, Ear + lead critic); revise loop, max 2, ungated until calibration; gate 3 (CLI first, in-order approval).
- Single-prompt baseline generator, for the later A/B test.
- **Done when:** one story runs end to end to approved scripts with report cards.
- **You do:** hand-adapt 2–3 reference scenes and score ~20 generated episodes; thresholds are set from your scores.

### Step 3 — Model serving and audio (days 4–5)
- Modal apps: Chatterbox, Whisper, Kokoro (CPU). vLLM/Qwen already up from day 2. Measure cold start, latency and cost per call; log to Langfuse. Measure per-voice wpm for the runtime estimator.
- Collect and tag 20–30 Freesound CC0 Foley clips (manifest) and embed in pgvector; series sting + variants.
- Performance Director, line takes (2–3 for key moments), Whisper word alignment, Sound Designer, timing solver, ffmpeg mixer (ducking, fades, -16 LUFS, 120 s cap with the 3-tier fit strategy), Audio QA.
- Gate 4 with structured timing nudges.
- **Done when:** one approved episode becomes a ≤ 120 s MP3 that passes Audio QA and gate 4.
- **You do:** tag the sound clips with Claude; tune the max time-stretch by ear.

### Step 4 — Product surface, coherence and ship (days 6–7)
- FastAPI app (`/review` token-gated, `/season` public) on Render, then EC2 (free plan) + S3; Langfuse tracing across the graph; shadow-cost table.
- Story Architect reconciliation after each approval; season-level validator.
- Evals: critic–human agreement, blind A/B vs the single-prompt baseline (positions swapped; third-family LLM on text, me on 6 audio pairs), timing-taste listening test on 5 episodes.
- README with eval report, cost per finished audio minute, and a sample season; record the demo.
- **Done when:** a full season of one story is published with report cards, and the README numbers are filled in.
- **You do:** blind listening for the A/B and timing tests; record the demo.

If a day slips, the review page shrinks to a command-line tool first, then the demo drops to one story.

## 12. Risks

| Risk | Effect | Fallback |
|---|---|---|
| Free API rate limits | Runs stall mid-story | Cache every LLM call; second free provider; demo on one story |
| Modal cold starts | First call slow | Accept for demo; report cold-start time |
| Mispronounced names | Higher round-trip WER | Pronunciation dictionary in the story bible |
| EC2 out of memory | Postgres/API/Kokoro crash together | Resolved: Kokoro on Modal CPU, Postgres on Supabase (decision 30) |
| Supabase free pauses after ~7 days idle | DB offline at demo | Keep it active; `pg_dump` before demo |
| Render free spins down, ~512 MB | Slow first load; can't run the graph | Page only; graph runs on laptop or Modal |
| Critics disagree with my ratings | Scores untrustworthy | Rewrite rubric with gold-set examples; report agreement honestly |
| CrewAI/LangGraph state drift | Hard-to-debug hand-offs | Crew gets one typed input, returns one typed output |
| Parallel episodes drift from plan | Clue/reveal lands in wrong episode | Reconcile after each approval; re-validate later drafts; else write in order |
| Chatterbox slow/costly on T4 | Renders eat Modal credit | Cache lines; extra takes only for key moments; fall back to Kokoro |

---

## 13. Open questions

All four original questions are resolved (decisions 17–20). Still to verify, not decide:
- Gemini free-tier limits fit the workload (day 1); if not, switch writing to Groq.
- Groq stand-in judge model choice (day 1); A/B judge must be a different Groq model family.
- Qwen3-8B AWQ loads on a T4 under vLLM with usable throughput (day 2); if not, use the fallbacks in decision 20.
- Chatterbox render speed on a T4 (day 4).

## 14. Background and sources

- Kuku (Kuku FM, Kuku TV) uses AI for 70%+ of content (scripting, voice, translation); micro-drama cost ~ $100/min. Kuku's in-house audio-to-video pipeline: Transcribe → LLM scene chunking → visuals → MoviePy, 7+ Indian languages, < $0.30/min.
  - https://www.ipomarket.in/news/kuku-fm-ipo-2026-drhp-date-price-review
  - https://rajatdhoot.substack.com/p/building-ai-powered-videos-from-audio
  - https://startuptalky.com/news/kuku-technologies-announces-1-000-hire/
- AWS free plan: https://aws.amazon.com/about-aws/whats-new/2025/07/aws-free-tier-credits-month-free-plan/ · xlarge restriction: https://dev.classmethod.jp/en/articles/try-new-aws-free-tier-2025/
- Modal pricing: https://modal.com/pricing
- Kokoro-82M: https://huggingface.co/hexgrad/Kokoro-82M
- Chatterbox: https://huggingface.co/ResembleAI/chatterbox · settings: https://deepinfra.com/ResembleAI/chatterbox
- Living brief (doc): https://claude.ai/artifact/UUh7jtT927byJjKVNuY1Hi
