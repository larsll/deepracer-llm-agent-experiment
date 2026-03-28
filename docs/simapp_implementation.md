# SimApp Implementation Notes

This document describes how the LLM agent was integrated into the [DeepRacer SimApp](https://github.com/aws-deepracer-community/deepracer-simapp). The implementation was contributed upstream via [PR #221](https://github.com/aws-deepracer-community/deepracer-simapp/pull/221). The code is not in this repository; these notes describe the design for anyone who wants to understand or extend it.

---

## What Changed

The PR adds an LLM execution path alongside the existing RL (PPO/SAC) path. The simulator and physics engine are unchanged; only the agent decision-making layer is swapped out.

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

---

## Key Code Changes

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

## What Stays the Same

The Gazebo/ROS simulation, sensor stack, simtrace CSV format, evaluation metrics, and the re:Invent track are all identical to a normal DeepRacer evaluation run. The `reward_function.py` is still invoked by the framework (via `RolloutCtrl`) but its scalar return value is discarded — there is no training loop to consume it. The only difference visible to the simulator is that actions arrive much more slowly than with an RL model.

---

## Step-by-Step: What Happens at Each Decision Point

At each step the agent:

1. Captures a front-facing camera image from the simulator (colour, not grayscale)
2. Reads the full `reward_params` dict from `RolloutCtrl` — position, heading, progress, closest waypoints, `all_wheels_on_track`, speed, and more
3. Encodes the image as base64 and builds a Bedrock message containing: the system prompt, the action space bounds, up to N previous turn pairs (context window = 2), the repeated step prompt, the `reward_params` as a `"Current state information:"` JSON block, and the image
4. Calls Claude Sonnet 4.6 via Bedrock and parses the JSON response for `steering_angle` and `speed`
5. Injects the action back into the DeepRacer simulator

The simulator pauses between steps, so the car remains stationary during inference. Each step produces four trace files: `*_img.jpg`, `*_request.json`, `*_response.json`, and `*_action.json`.
