# Experiment Analysis: LLM Agent for AWS DeepRacer

> Key findings from this analysis are summarised in the [README](../README.md). This document covers the full quantitative breakdown.

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

### Camera vs. numeric state

The agent receives two kinds of input at every step: a colour camera image and a structured JSON block containing x/y position, heading, track progress, distance from centre, closest waypoints, `all_wheels_on_track`, and speed. The system prompt was developed with the expectation that the numeric state would carry most of the navigational load; the camera provides local visual context but is not relied upon for precise directional decisions.

This is evident in the trace data. The reliable behaviours described below — straight-line tracking, smooth turn entry — correlate tightly with the heading delta parameter, not with image content. The failure modes in Weaknesses involve cases where the model's visual interpretation conflicts with the numeric heading; in all observed cases the numeric state wins. The camera's main contribution appears to be helping the model assess whether the track is curving ahead and confirming on-track status — tasks that do not require precise bearing — rather than providing directional guidance.

### Strengths

- **Straight-line tracking** is consistently excellent. On long straights the LLM reads near-zero heading deltas and commands 0° steer, keeping distance from center under 1–2 cm. This is driven by the numeric delta, not image interpretation.
- **Smooth turn entry**: the LLM correctly ramps steering up as the track-heading delta increases, and unwinds it as the delta decreases on exit.
- **Temporal context from prior responses**: each step includes the previous assistant response alongside the current image. This allows the agent to notice it is "still turning" without re-deriving that fact from scratch — continuity comes from the retained text, not from a second image.
- **Self-correction**: occasional steering errors are quietly corrected within a few steps without going off-track (especially clear in run 3).

### Weaknesses

- **Camera-derived direction reasoning disagrees with the heading parameter**: the lap story for run 3 documents an instance at step 30 where the LLM wrote "big right curve" in its internal reasoning while actively steering left through a left-hand bend. The heading delta clearly indicated a left turn; the camera image apparently suggested otherwise. The correct action was issued — the structured parameter overrode the image interpretation — but the disagreement is a meaningful signal. The camera alone cannot be trusted for directional reasoning; the model's visual narrative of where the track goes frequently does not match the calculated bearing. This is not a problem when the numeric state is available and authoritative, but it would rule out a camera-only configuration entirely.
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

1. **A general-purpose vision-language model can drive the DeepRacer track** without task-specific fine-tuning — but the camera feed alone is not sufficient. Reliable navigation requires explicit numeric state (x/y, heading, progress) injected into every prompt alongside the image.
2. **The camera and the heading parameter can give conflicting directional signals.** In observed cases the model resolves them in favour of the numeric data — issuing the correct steering command even while its image-based narrative describes the wrong turn direction. This confirms that the camera is not a reliable source of directional truth and that a camera-only configuration would likely fail.
3. **The primary limitation is latency**, not accuracy. At ~17 s/step the approach cannot run in real time; it is only feasible with a simulator that pauses during inference.
4. **Navigation quality improves with prompt iteration**: run 3's zero off-track result vs. runs 1–2 suggests that system prompt quality matters significantly.
5. **A single image per step is sufficient**; temporal continuity is provided by retaining the previous assistant response in the prompt, not by passing multiple images.

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
