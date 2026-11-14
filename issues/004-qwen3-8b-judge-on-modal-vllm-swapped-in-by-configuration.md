---
number: 4
title: "Qwen3-8B judge on Modal vLLM, swapped in by configuration"
state: open
labels: [ready-for-agent]
url: https://github.com/1Ayush-Petwal/Serial-Studio/issues/4
created: 2026-11-07T19:45:41Z
updated: 2026-11-07T19:45:41Z
---

# #4 Qwen3-8B judge on Modal vLLM, swapped in by configuration

## Parent

#1

## What to build

Stand up Qwen3-8B 4-bit AWQ on vLLM on a Modal T4 behind an OpenAI-compatible endpoint, set a Modal spending limit, and switch the judge to it through configuration only. Re-extract the bibles on Qwen so the bible matches the final judge. Measure cold start, latency and cost per call. If it does not load or throughput is unusable, fall back to Llama 3.1 8B AWQ, then Mistral 7B.

## Acceptance criteria

- [ ] Modal account has a spending limit set
- [ ] Judge calls go to Qwen on Modal with a config change only, no code change
- [ ] Bibles for the demo stories are re-extracted on Qwen and pass gate 1
- [ ] Cold start, latency and per-call GPU cost are recorded in Langfuse and shadow-cost lines
- [ ] Structured outputs from Qwen validate against the schemas

## Blocked by

- #2
