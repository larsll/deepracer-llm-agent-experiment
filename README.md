# DeepRacer LLM Agent — Experiment Documentation

This repository documents an experiment using **Claude Sonnet 4.6** (via AWS Bedrock) as a vision-based autonomous driving agent for [AWS DeepRacer](https://aws.amazon.com/deepracer/). Rather than a trained reinforcement-learning model, the agent sends a front-facing camera image to the LLM at every decision step and receives a steering angle and speed command in return.

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

| Run | Date | Steps | Wall clock | Avg inference/step |
|-----|------|-------|------------|-------------------|
| Run 1 | 2026-03-26 | 219 | 56.9 min | 15.6 s |
| Run 2 | 2026-03-27 | 248 | 67.7 min | 16.4 s |
| Run 3 | 2026-03-27 | 214 | 66.9 min | 18.8 s |

The key finding: **the LLM can successfully navigate the track**, but at ~15–19 seconds per decision step the lap takes ~1 hour of wall-clock time (vs. seconds for a normal RL model). The simulator runs in paused mode between steps, so the car never physically moves during inference — making this a demonstration of capability rather than a practical racing approach.

Two earlier runs (52 and 40 steps respectively) were aborted during debugging and are not included here.

---

## Repository Structure

```
docs/                          # Analysis and narrative (cross-run)
  analysis.md
  lap_story_run3_20260327-101257.md
  running_your_own_experiment.md

experiments/
  reward_function.py             # Shared DeepRacer reward function (pass-through for LLM)
  evaluation_params.yaml         # Shared evaluation job parameters
  training_params.yaml           # Shared training environment parameters
  metrics/                       # High-level evaluation metrics JSON

  run_1/                         # 2026-03-26, 219 steps, 56.9 min — 2 off-track events
    config/
      model_metadata.json            # Model config used for this run
    traces/                          # Raw LLM traces: *_img.jpg, *_request.json,
                                     #   *_response.json, *_action.json per step
    outputs/
      simtrace.csv                   # Step-by-step simulator telemetry

  run_2/                         # 2026-03-27 03:00, 248 steps, 67.7 min — 5 off-track events
    config/
      model_metadata.json
    traces/
    outputs/
      simtrace.csv

  run_3/                         # 2026-03-27 10:00, 214 steps, 66.9 min — 0 off-track events ✓
    config/
      model_metadata.json
    traces/
    outputs/
      simtrace.csv
      mp4/
        camera-pip.mp4               # Picture-in-picture camera recording
        camera-topview.mp4           # Top-down track view
```

---

## What Changed in the SimApp

The [PR #221](https://github.com/aws-deepracer-community/deepracer-simapp/pull/221) adds an LLM execution path alongside the existing RL (PPO/SAC) path. The simulator and physics engine are unchanged; only the agent decision-making layer is swapped out.

### Normal DeepRacer flow

```
Camera frame → grayscale conversion → CNN policy network (TF/TFLite) → steering + speed
```

The policy network is a trained convolutional model loaded from a checkpoint. The evaluation worker blocks on `wait_for_checkpoints()` and restores a TF checkpoint before the episode can start.

### LLM agent flow

```
Camera frame (colour) → base64 encode → Bedrock API (Claude / Mistral / Llama / Nova) → JSON parse → steering + speed
```

There is no trained model. The simulator **pauses physics** between every step while the API call completes (~15–19 s), then injects the returned action.

### Key code changes

| What | How |
|------|-----|
| **New `neural_network: "LLM"` type** | Added to the `NeuralNetwork` enum in `architecture/constants.py`. This is the single flag that routes the entire pipeline to LLM mode. |
| **New `LLMAgent` class** (`llm_agent.py`, ~376 lines) | Replaces the CNN inference call. On each step it encodes the camera image as base64, builds a prompt with the action space and rolling conversation context, calls Bedrock, and parses the JSON response. |
| **Bedrock client layer** | `BedrockClient` + per-provider handlers (`ClaudeHandler`, `MistralHandler`, `LlamaHandler`, `NovaHandler`) normalise the different message formats across model families. Each handler maintains conversation context across steps. |
| **New `LLMActionSpaceConfig`** | Passes the raw steering/speed bounds from `model_metadata.json` directly to the LLM instead of creating a standard PPO/SAC gym action space. |
| **Checkpoint loading bypassed** | `evaluation_worker.py` wraps the entire checkpoint restore block in `if False:` — the LLM has no model file to load, so `wait_for_checkpoints()` is also commented out. |
| **Camera kept in colour** | Standard DeepRacer converts the camera to grayscale before the CNN. The LLM path skips the `ObservationRGBToYFilter` step and passes the full RGB image. |
| **New `llm_config` in `model_metadata.json`** | Adds a config block alongside the existing `action_space` block, containing `model_id`, `system_prompt`, `max_tokens`, `context_window`, and `repeated_prompt`. The `neural_network` field is set to `"LLM"` and `training_algorithm` to `"llm"`. |
| **Step tracing built in** | The base handler writes `*_request.json`, `*_response.json`, `*_img.jpg`, and `*_action.json` for every step, producing the trace files in this repository. |
| **`reward_params` injected into LLM prompt** | In a normal RL run, `reward_params` (position, heading, progress, waypoints, `all_wheels_on_track`, …) is passed only to `reward_function()` to produce a scalar training signal — the CNN **never sees** this data. In the LLM path, `LLMAgent.choose_action()` reads `self.agent_ctrl._reward_params_` directly and passes the entire dict to the model handler, which serialises it as a `"Current state information:"` JSON block appended to every user message. The LLM therefore has explicit numeric state awareness at each step that the RL CNN must instead infer implicitly from pixels over thousands of training episodes. |

### What stays the same

The Gazebo/ROS simulation, sensor stack, simtrace CSV format, evaluation metrics, and the re:Invent track are all identical to a normal DeepRacer evaluation run. The `reward_function.py` is still invoked by the framework (via `RolloutCtrl`) but its scalar return value is discarded — there is no training loop to consume it. The only difference visible to the simulator is that actions arrive much more slowly than with an RL model.

---

## How It Worked

At each step the agent:
1. Captures a front-facing camera image from the simulator (colour, not grayscale)
2. Reads the full `reward_params` dict from `RolloutCtrl` — position, heading, progress, closest waypoints, `all_wheels_on_track`, speed, and more
3. Encodes the image as base64 and builds a Bedrock message containing: the system prompt, the action space bounds, up to N previous turn pairs (context window = 2), the repeated step prompt, the `reward_params` as a `"Current state information:"` JSON block, and the image
4. Calls Claude Sonnet 4.6 via Bedrock and parses the JSON response for `steering_angle` and `speed`
5. Injects the action back into the DeepRacer simulator

The simulator pauses between steps, so the car remains stationary during inference. Each step produces four trace files: `*_img.jpg`, `*_request.json`, `*_response.json`, and `*_action.json`.

See [docs/lap_story_run3_20260327-101257.md](docs/lap_story_run3_20260327-101257.md) for a detailed step-by-step narrative of the final run, [docs/analysis.md](docs/analysis.md) for a quantitative comparison across all three runs, and [docs/running_your_own_experiment.md](docs/running_your_own_experiment.md) if you want to replicate or extend the experiment.

---

## Related

- **Code implementation**: [aws-deepracer-community/deepracer-simapp#221](https://github.com/aws-deepracer-community/deepracer-simapp/pull/221)
- **deepracer-for-cloud**: [aws-deepracer-community/deepracer-for-cloud](https://github.com/aws-deepracer-community/deepracer-for-cloud) — the tooling used to run the simulator locally

## License

This project is licensed under the MIT License. See the LICENSE file for details.
