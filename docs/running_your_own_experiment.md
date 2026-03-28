# Running Your Own LLM DeepRacer Experiment

This guide explains how to replicate or extend this experiment — running an LLM as the decision-making agent for AWS DeepRacer using [deepracer-for-cloud](https://github.com/aws-deepracer-community/deepracer-for-cloud) and the modified SimApp from [PR #221](https://github.com/aws-deepracer-community/deepracer-simapp/pull/221).

## Prerequisites

| Requirement | Notes |
|---|---|
| **deepracer-for-cloud** | Tested on a recent `main` branch checkout |
| **Modified SimApp** | The `llm-agent` branch of `deepracer-simapp` — see PR #221 |
| **AWS account** | Bedrock access required; IAM credentials with `bedrock:InvokeModel` |
| **Bedrock model access** | Enable your chosen model in the AWS console under Bedrock → Model access |
| **deepracer-for-cloud region** | The `APP_REGION` in your environment must match the region where you have Bedrock access |

The experiment was run in `eu-central-1`. Cross-region inference profiles (`eu.anthropic.claude-...`) were used to access models.

---

## Step 1 — Build the modified SimApp

The key change is setting `neural_network: "LLM"` in `model_metadata.json`. The code that handles this lives in the `llm-agent` branch of `deepracer-simapp`. You need to build a custom Docker image from that branch and tell deepracer-for-cloud to use it.

```bash
# Clone the branch
git clone --branch llm-agent https://github.com/aws-deepracer-community/deepracer-simapp.git
cd deepracer-simapp

# Build the RoboMaker image (cpu architecture; the VERSION file controls the image tag)
./build.sh -a cpu
# The resulting image is tagged using the content of the VERSION file (e.g. 6.0.2-llm)
# Set ROBOMAKER_IMAGE to that tag in your deepracer-for-cloud .env
```

The `llm-agent` branch sets the version to `6.0.2-llm` in the `VERSION` file, so the built image will be tagged accordingly.

---

## Step 2 — Create a `model_metadata.json`

The `llm_config` block is what makes the difference. Ready-to-use examples are in the [`examples/`](../examples/) folder of this repo:

| File | Model |
|---|---|
| `model_metadata_claude.json` | Anthropic Claude 3.7 Sonnet (cross-region `eu`) |
| `model_metadata_mistral.json` | Mistral Pixtral Large (cross-region `eu`) |
| `model_metadata_nova.json` | Amazon Nova Pro (cross-region `eu`) |

### Annotated structure

```json
{
  "action_space": {
    "speed":          { "high": 3, "low": 1 },
    "steering_angle": { "high": 30, "low": -30 }
  },
  "sensor": ["FRONT_FACING_CAMERA"],
  "neural_network": "LLM",          // <-- routes execution to LLMAgent
  "action_space_type": "continuous",
  "version": "5",

  "llm_config": {
    "model_id": "arn:aws:bedrock:eu-central-1:<ACCOUNT>:inference-profile/eu.anthropic.claude-3-7-sonnet-20250219-v1:0",
    "max_tokens": 1000,
    "context_window": 2,            // rolling turns of conversation history kept per step
    "repeated_prompt": "Analyze the image and provide a driving command.",
    "system_prompt": [              // array of strings, joined with newlines
      "You are an AI driver assistant ...",
      "..."
    ]
  }
}
```

**Key fields to customise:**

- `model_id` — replace `<ACCOUNT>` with your AWS account ID. For simple (non-cross-region) model IDs you can use the short form, e.g. `anthropic.claude-3-5-sonnet-20241022-v2:0`.
- `context_window` — number of prior turn-pairs kept in the conversation. `0` = stateless (every step is independent). `2` was used in this experiment.
- `system_prompt` — this is the most impactful knob. See the [prompt engineering notes](#prompt-engineering-notes) below.
- `repeated_prompt` — the short user-turn text sent at every step, with the step number prepended: `"Image #42. Analyze the image and provide a driving command."`.
- `action_space` — set `low`/`high` to match the action space you actually want. The LLM will be told these bounds explicitly and its output will be clamped to them.

---

## Step 3 — Configure the evaluation job

deepracer-for-cloud is configured entirely through environment variable files — you never edit `evaluation_params.yaml` directly. When you run `dr-start-evaluation`, DRfC calls `scripts/evaluation/prepare-config.py` which reads your env vars, generates the YAML, and uploads it to S3 automatically.

There are two env files to edit, both in your deepracer-for-cloud directory:

### `system.env` — machine-level settings

These are set once for your machine and apply to all runs:

| Variable | Value | Notes |
|---|---|---|
| `DR_CLOUD` | `aws` | **Required.** Local mode uses MinIO credentials that cannot reach Bedrock. `aws` mode routes both S3 and Bedrock calls to AWS directly. |
| `DR_LOCAL_S3_BUCKET` | your bucket name | The S3 bucket used for all DRfC data |
| `DR_LOCAL_S3_PROFILE` | `default` | AWS credentials profile |
| `DR_AWS_APP_REGION` | e.g. `eu-central-1` | Must match the region where you have Bedrock access |
| `DR_SIMAPP_VERSION` | e.g. `6.0.2-llm` | Must match the image tag you built in Step 1 |

### `run.env` — run-level settings

These control what gets evaluated and where results are stored:

| Variable | Example value | Notes |
|---|---|---|
| `DR_LOCAL_S3_MODEL_PREFIX` | `LLM-Test-Model-1` | S3 "folder" for this model's data |
| `DR_WORLD_NAME` | `reinvent_base` | Track to evaluate on |
| `DR_RACE_TYPE` | `TIME_TRIAL` | Race type |
| `DR_EVAL_NUMBER_OF_TRIALS` | `1` | Number of laps per evaluation |
| `DR_EVAL_MAX_RESETS` | `10` | Off-track resets allowed per trial |
| `DR_EVAL_OFF_TRACK_PENALTY` | `0.2` | Seconds added per reset |

After editing either file, reload the environment:

```bash
dr-update
```

> **No checkpoint is needed.** The LLM has no trained model file. The modified SimApp bypasses `wait_for_checkpoints()` and the checkpoint restore block entirely when `training_algorithm == "llm"`.

---

## Step 4 — Upload files to S3

`dr-start-evaluation` generates and uploads `evaluation_params.yaml` automatically. You need to manually place three files in S3 under the model prefix (`DR_LOCAL_S3_MODEL_PREFIX`) before running. Note that 

| File | S3 path |
|---|---|
| `model_metadata.json` | `s3://<BUCKET>/<MODEL_PREFIX>/model/model_metadata.json` |
| `reward_function.py` | `s3://<BUCKET>/<MODEL_PREFIX>/reward_function.py` |
| `hyperparameters.json` | `s3://<BUCKET>/<MODEL_PREFIX>/ip/hyperparameters.json` |

```bash
aws s3 cp examples/model_metadata_claude.json \
    s3://$DR_LOCAL_S3_BUCKET/$DR_DR_LOCAL_S3_MODEL_PREFIX/model/model_metadata.json

aws s3 cp custom_files/reward_function.py \
    s3://$DR_LOCAL_S3_BUCKET/$DR_DR_LOCAL_S3_MODEL_PREFIX/reward_function.py

aws s3 cp custom_files/hyperparameters.json \
    s3://$DR_LOCAL_S3_BUCKET/$DR_DR_LOCAL_S3_MODEL_PREFIX/ip/hyperparameters.json
```

---

## Step 5 — IAM permissions

The RoboMaker container needs to call Bedrock at runtime. Ensure the IAM role or credentials available inside the container include:

```json
{
  "Effect": "Allow",
  "Action": ["bedrock:InvokeModel"],
  "Resource": "*"
}
```

With deepracer-for-cloud running locally, the container inherits the host's AWS credentials via the environment variables set in your `.env` file.

---

## Step 6 — Run

```bash
# From your deepracer-for-cloud directory
dr-start-evaluation
```

The simulation will start, and on each step:
1. The SimApp captures a colour camera frame
2. `reward_params` (position, heading, progress, waypoints, off-track status, …) are read from `RolloutCtrl`
3. Both are sent to Bedrock
4. The returned `{"steering_angle": ..., "speed": ...}` JSON is injected as the action

Expect **15–20 seconds per step** for Claude Sonnet-class models. A full lap at ~200 steps takes roughly an hour of wall-clock time. The simulator pauses physics during each inference call, so the car is stationary while waiting for the LLM.

### Trace output

If tracing is enabled (default: `True`), four files are written per step to `/root/.ros/log/llm_agent_traces/` inside the robomaker container:

```
<TIMESTAMP>_ep<N>_step<NNN>_img.jpg
<TIMESTAMP>_ep<N>_step<NNN>_request.json
<TIMESTAMP>_ep<N>_step<NNN>_response.json
<TIMESTAMP>_ep<N>_step<NNN>_action.json
```

These are the same files archived in `experiments/run_*/traces/` in this repo. They are invaluable for understanding what the LLM saw and why it made each decision.
To get access to these you should set `DR_ROBOMAKER_MOUNT_LOGS=True` in `run.env`. In this case the logs get mounted to `~/deepracer-for-cloud/data/logs/robomaker/<model_name>`

---

## Prompt engineering notes

The system prompt has the largest effect on driving behaviour. A few things that worked well in this experiment:

- **State the steering convention explicitly.** The car uses Ackermann geometry where positive angles turn LEFT. LLMs trained on general driving data often assume the opposite. The phrase `"IMPORTANT STEERING CONVENTION: Positive steering angles turn the car LEFT"` was added after early runs showed the car consistently turning the wrong way.
- **Ask for `reasoning` and `knowledge` fields.** Having the LLM articulate its reasoning in the JSON response improves action quality (chain-of-thought effect) and makes the traces much easier to analyse.
- **Describe visual landmarks.** `"The track has white lines to the left and the right, and a dashed yellow centerline."` helps ground the model's visual interpretation.
- **Keep `repeated_prompt` short.** The per-step user message is already quite large (action space, reward params, image). A short repeated prompt like `"Analyze the image and provide a driving command."` avoids token waste.
- **Context window trade-offs.** `context_window: 2` (two prior turn pairs) gave the best results here. Higher values increase input token costs and latency without a clear benefit for this task — the track geometry is largely the same at each step.

---

## Supported models

| Model family | Handler | Notes |
|---|---|---|
| Anthropic Claude | `ClaudeHandler` | Best results; natively multimodal; claude-sonnet-4-x recommended |
| Mistral Pixtral | `MistralHandler` | Vision capable; Pixtral Large tested |
| Meta Llama | `LlamaHandler` | Limited vision support depending on variant |
| Amazon Nova | `NovaHandler` | Nova Pro tested; good vision support |

The `HandlerFactory` selects the right handler automatically from the `model_id` string. If the model ID is an ARN (cross-region inference profile), it extracts the provider from the ARN.

---

## Cost estimate

Based on this experiment using Claude Sonnet 4.6 at approximately 2,000 input tokens + 1 image (~1,800 tokens) and 200 output tokens per step:

| Run length | Approx. input tokens | Approx. cost (Claude Sonnet) |
|---|---|---|
| 200 steps (1 lap) | ~760,000 | ~$2.30 USD |
| 5 × 200 step runs | ~3,800,000 | ~$11.50 USD |

These are rough estimates. Actual cost depends on model, region, and prompt length. Check current Bedrock pricing before running extended experiments.

---

## Related

- [deepracer-simapp PR #221](https://github.com/aws-deepracer-community/deepracer-simapp/pull/221) — the code
- [deepracer-for-cloud](https://github.com/aws-deepracer-community/deepracer-for-cloud) — the local simulation tooling
- [docs/analysis.md](analysis.md) — quantitative comparison of the three runs in this experiment
