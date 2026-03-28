# Experiment Analysis: LLM Agent for AWS DeepRacer

## Overview

This document analyses the three completed evaluation runs from the DeepRacer LLM agent experiment (March 26–27, 2026). The agent used **Claude Sonnet 4.6** via AWS Bedrock (eu-central-1) to drive the re:Invent 2018 base loop track in continuous action space mode.

All three runs completed 100% of the lap.

---

## Per-Run Performance

| Metric | Run 1 (2026-03-26) | Run 2 (2026-03-27 AM) | Run 3 (2026-03-27 PM) |
|--------|-------------------|-----------------------|-----------------------|
| Steps to complete | 219 | 248 | 214 |
| Wall clock | 56.9 min | 67.7 min | 66.9 min |
| Avg inference / step | 15.6 s | 16.4 s | 18.8 s |
| Median inference / step | 15.7 s | 16.4 s | 19.2 s |
| Min / Max inference | 10.8 s / 22.4 s | 12.9 s / 31.9 s | 13.0 s / 26.4 s |
| p95 inference | 18.9 s | 18.5 s | 21.2 s |
| Off-track events | 2 | 5 | **0** |
| All wheels on track | 203/219 (93%) | 216/248 (87%) | **214/214 (100%)** |
| Avg |steer| (°) | 14.2 | 15.8 | 12.9 |

> Off-track events reset the car to the last checkpoint but the run continues (up to 10 resets are allowed). All runs completed the lap despite any resets.

Run 3 was the cleanest: zero off-track events and 100% on-track throughout. This also has the most complete trace data and the accompanying [lap story](lap_story_run3_20260327-101257.md).

---

## Inference Latency

Inference latency is the dominant constraint. At a median of ~16–19 seconds per decision step, a single lap takes roughly **57–68 minutes** of wall-clock time even though in simulation time the lap is "instant" (the simulator pauses between steps).

At 1.5 m/s the car covers ~22 cm/second of track. The LLM takes ~17 s on average to decide — meaning each decision covers **~3.3 m of track** between commands (i.e. the car would have moved that far if the simulator weren't paused). This is not a concern for correctness in the paused simulation, but illustrates why this approach is a demonstration rather than a real-time controller.

Latency spikes are clearly API latency outliers — the lap story for run 3 notes a 26.3-second step at 61% progress with no apparent change in decision complexity.

**Latency increased across runs**: run 1 median 15.7 s → run 3 median 19.2 s. This could be time-of-day API load variation on Bedrock, or the slightly larger context from refined system prompts used in later runs. The raw request/response JSONs in `traces/` contain `inputTokens` and `outputTokens` fields that could be used to investigate further.

---

## Navigation Quality

### Strengths

- **Straight-line tracking** is consistently excellent. On long straights the LLM reads near-zero deltas and commands 0° steer, keeping distance from center under 1–2 cm.
- **Smooth turn entry**: the LLM correctly ramps steering up as the track-heading delta increases, and unwinds it as the delta decreases on exit.
- **Context window use**: the 2-image rolling context allows the agent to notice it is "still turning" without re-deriving that fact from scratch at each step.
- **Self-correction**: occasional steering errors are quietly corrected within a few steps without going off-track (especially clear in run 3).

### Weaknesses

- **Compass / direction reasoning errors**: the lap story for run 3 documents an instance at step 30 where the LLM wrote "big right curve" in its internal knowledge while actively steering left through a left-hand bend. The error was harmless because the LLM correctly followed the delta signal rather than its own written note. However, it demonstrates unreliable spatial reasoning about absolute bearing.
- **Off-track events on sharper curves** (runs 1 and 2): the reinvent_base track has two 180° hairpins. Runs 1 and 2 had off-track events at these points; run 3 cleared them cleanly, suggesting the system prompt refinements between runs improved handling of maximum-curvature sections.
- **No speed modulation on most straights**: all runs consistently drove at 1.5 m/s regardless of available track width or upcoming turn geometry. The action space allows up to 3 m/s; the agent almost never used it.

---

## Cost

Token cost data is embedded in each `*_response.json` trace file. A rough estimate based on Claude Sonnet 4.6 pricing (eu-central-1 cross-region inference) and the approximately 1,000–2,000 input tokens (image + text) and 200–400 output tokens per step:

| | Run 1 | Run 2 | Run 3 |
|---|---|---|---|
| Steps | 219 | 248 | 214 |
| Estimated cost | ~$2–4 | ~$3–5 | ~$3–5 |

> Exact cost figures require summing the `inputTokens` / `outputTokens` fields from the response JSONs and applying the Bedrock pricing table. The agent code included a `PricingService` for this; the accumulated cost was logged at the end of each trace run.

---

## Key Conclusions

1. **A general-purpose vision-language model can drive the DeepRacer track** without any task-specific fine-tuning, using only a well-crafted system prompt and the rolling camera feed.
2. **The primary limitation is latency**, not accuracy. At ~17 s/step the approach cannot run in real time; it is only feasible with a simulator that pauses during inference.
3. **Navigation quality improves with prompt iteration**: run 3's zero off-track result vs. runs 1–2 suggests that system prompt quality matters significantly.
4. **Spatial reasoning remains the weak point**: the LLM can reliably follow the local delta signal (turn when the track curves) but has trouble with global bearing and compass direction reasoning.
5. **A context window of 2 is sufficient** for temporal continuity on this track; wider context was not needed to complete any lap.

---

## Data Files

| File | Description |
|------|-------------|
| `experiments/run_1/outputs/simtrace.csv` | Run 1 step-by-step telemetry |
| `experiments/run_2/outputs/simtrace.csv` | Run 2 step-by-step telemetry |
| `experiments/run_3/outputs/simtrace.csv` | Run 3 step-by-step telemetry |
| `experiments/run_1/traces/` | Run 1 raw LLM traces (images + JSON) |
| `experiments/run_2/traces/` | Run 2 raw LLM traces |
| `experiments/run_3/traces/` | Run 3 raw LLM traces |
| `docs/lap_story_run3_20260327-101257.md` | Step-by-step narrative of run 3 |
