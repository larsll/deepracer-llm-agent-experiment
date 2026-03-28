# DeepRacer LLM Agent — Experiment Documentation

This repository documents an experiment using **Claude Sonnet 4.6** (via AWS Bedrock) as a driving agent for [AWS DeepRacer](https://aws.amazon.com/deepracer/). Rather than a trained reinforcement-learning model, the agent sends a front-facing camera image **and** a full numeric state block (x/y position, heading, track progress, waypoints, `all_wheels_on_track`, and more) to the LLM at every decision step and receives a steering angle and speed command in return.

The camera provides local visual context, but the system prompt relies more heavily on the numeric state — particularly heading delta and track progress — than on image interpretation. The reliable navigation behaviours observed in the experiments are rooted in the structured data, not in visual reasoning.

> **The code has moved.** The agent implementation was contributed upstream to the [deepracer-community/deepracer-simapp](https://github.com/aws-deepracer-community/deepracer-simapp/pull/221) project. This repository now exists solely to preserve the experiment outputs, raw traces, configuration, and analysis.

---

## Experiment Summary

| | |
|---|---|
| **Model** | Claude Sonnet 4.6 (`anthropic.claude-sonnet-4-5-20251101-v1:0`) via AWS Bedrock (eu-central-1) |
| **Track** | re:Invent 2018 base loop (`reinvent_base`), ~17.7 m circumference, 121 waypoints |
| **Action space** | Continuous — speed 1–3 m/s, steering ±30° |
| **Context window** | 1 image + previous response |
| **Experiment date** | March 26–27, 2026 |

### Results

All three full evaluation runs completed the lap:

| Run | Date | Steps | Wall clock | Avg inference/step | Off-track |
|-----|------|-------|------------|-------------------|-----------|
| Run 1 | 2026-03-26 | 219 | 56.9 min | 15.6 s | 2 |
| Run 2 | 2026-03-27 | 248 | 67.7 min | 16.4 s | 5 |
| Run 3 | 2026-03-27 | 214 | 66.9 min | 18.8 s | **0** ✓ |

**The LLM can successfully navigate the track** without any task-specific fine-tuning — using only a well-crafted system prompt and the rolling camera feed. Run 3 completed the lap with zero off-track events and 100% of steps with all wheels on track.

The primary limitation is latency. At ~15–19 seconds per decision step, a single lap takes roughly an hour of wall-clock time. The simulator pauses physics during inference, making this a demonstration of capability rather than a practical real-time controller.

Two earlier runs (52 and 40 steps respectively) were aborted during debugging and are not included here.

---

## Key Findings

1. **A general-purpose vision-language model can drive a racing track** without fine-tuning — but the camera feed alone is not enough. Reliable navigation depends on explicit numeric state data (heading, position, progress) injected into every prompt alongside the image.
2. **The primary limitation is latency, not accuracy.** At ~17 s/step the approach cannot run in real time; it is only feasible with a simulator that pauses during inference.
3. **Navigation quality improves with prompt iteration.** Run 3's clean lap (0 off-track events) vs. runs 1 and 2 suggests that system prompt quality matters significantly.
4. **The LLM's image-based and parameter-based reasoning can disagree.** The model sometimes narrates the wrong turn direction from the camera while simultaneously issuing a correct steering command based on the heading delta. The numeric params win in practice, but the disagreement reveals a real tension between visual and structured-data reasoning.
5. **A context window of 2 frames is sufficient** for temporal continuity on this track.

### What the agent does well

- **Straight-line tracking**: near-zero steer commands on straights, keeping within 1–2 cm of centre. This relies primarily on the numeric heading delta parameter, not image interpretation.
- **Smooth turn entry and exit**: steering ramps up as curvature increases and unwinds cleanly on exit — driven by the quantitative heading delta rather than visual curvature estimation from the image.
- **Self-correction**: occasional steering errors are quietly recovered within a few steps, without going off-track.

### Where it struggles

- **Image and heading can disagree**: the LLM's interpretation of the camera image and the numeric heading parameters sometimes point in opposite directions. At step 30 of run 3, the model wrote "big right curve" in its reasoning while actively steering left through a left-hand bend — the image-derived narrative was wrong, but the heading delta was correct, and the correct action was issued. The structured data overrides visual reasoning in practice, but the mismatch demonstrates that the camera alone is not a reliable source of directional truth.
- **Speed modulation**: the agent mostly drove at 1.5 m/s regardless of track geometry; the upper bound of 3 m/s was almost never used.
- **Sharp hairpins** (runs 1 and 2): the two 180° hairpins on the track caused off-track events in the earlier runs, suggesting this is where prompt quality has the most impact.

---

## Repository Structure

```
docs/
  analysis.md                        # Quantitative comparison across all three runs
  lap_story_run3_20260327-101257.md  # Step-by-step narrative of run 3
  simapp_implementation.md           # How the LLM agent was wired into the SimApp
  running_your_own_experiment.md

experiments/
  evaluation_params.yaml

  run_1/                         # 2026-03-26, 219 steps — 2 off-track events
    config/model_metadata.json
    traces/                      # Raw LLM traces (*_img.jpg, *_request.json, *_response.json, *_action.json)
    outputs/
      simtrace.csv
      mp4/
        camera-pip.mp4           # Picture-in-picture camera recording

  run_2/                         # 2026-03-27 03:00, 248 steps — 5 off-track events
    config/model_metadata.json
    traces/
    outputs/
      simtrace.csv
      mp4/
        camera-pip.mp4           # Picture-in-picture camera recording

  run_3/                         # 2026-03-27 10:00, 214 steps — 0 off-track events ✓
    config/model_metadata.json
    traces/
    outputs/
      simtrace.csv
      mp4/
        camera-pip.mp4           # Picture-in-picture camera recording
```

---

## Further Reading

- [docs/analysis.md](docs/analysis.md) — quantitative breakdown of all three runs: latency distributions, per-run telemetry, cost estimates
- [docs/lap_story_run3_20260327-101257.md](docs/lap_story_run3_20260327-101257.md) — step-by-step narrative of run 3
- [docs/simapp_implementation.md](docs/simapp_implementation.md) — how the LLM agent was wired into the DeepRacer SimApp
- [docs/running_your_own_experiment.md](docs/running_your_own_experiment.md) — how to replicate or extend the experiment

---

## Related

- **Code implementation**: [aws-deepracer-community/deepracer-simapp#221](https://github.com/aws-deepracer-community/deepracer-simapp/pull/221)
- **deepracer-for-cloud**: [aws-deepracer-community/deepracer-for-cloud](https://github.com/aws-deepracer-community/deepracer-for-cloud) — the tooling used to run the simulator locally

## License

This project is licensed under the MIT License. See the LICENSE file for details.
