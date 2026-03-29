#!/usr/bin/env python3
"""
Turn detection benchmark for DeepRacer LLM models.

Tests whether various LLMs can correctly identify a left turn from a
front-facing camera image, using the AWS Bedrock Converse API.

Usage:
    python turn_detection_benchmark.py \
        --models eu.anthropic.claude-sonnet-4-6 \
                 eu.amazon.nova-pro-v1:0 \
                 eu.mistral.pixtral-large-2502-v1:0 \
        --runs 3

    # Write results to a JSON file
    python turn_detection_benchmark.py --models eu.anthropic.claude-sonnet-4-6 --runs 5 --output results.json
"""

import argparse
import base64
import json
import re
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

SYSTEM_PROMPT = (
    "You are analyzing a front-facing camera image from an AWS DeepRacer "
    "1/18th scale car on a race track. "
    "The track has white boundary lines on the left and right and a dashed "
    "yellow centerline."
)

USER_PROMPT = (
    "Look carefully at the track ahead in this image. "
    "Describe what you see: is the track going straight, curving to the left, "
    "or curving to the right? "
    "State the turn direction explicitly."
)


# ---------------------------------------------------------------------------
# Bedrock helpers
# ---------------------------------------------------------------------------

def _build_request_body(
    model_id: str, image_b64: str, temperature: float, run_index: int
) -> dict:
    """Build model-specific invoke_model request body."""
    mid = model_id.lower()
    # Append a unique run tag so each request is a distinct prompt string,
    # preventing server-side prompt-cache hits from collapsing all runs.
    user_prompt = f"{USER_PROMPT} [run={run_index}]"

    if "anthropic" in mid or "claude" in mid:
        return {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 512,
            "temperature": temperature,
            "system": SYSTEM_PROMPT,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": image_b64,
                            },
                        },
                        {"type": "text", "text": user_prompt},
                    ],
                }
            ],
        }

    if "nova" in mid or "amazon" in mid:
        return {
            "system": [{"text": SYSTEM_PROMPT}],
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "image": {
                                "format": "jpeg",
                                "source": {"bytes": image_b64},
                            }
                        },
                        {"text": user_prompt},
                    ],
                }
            ],
            "inferenceConfig": {"maxTokens": 512, "temperature": temperature},
        }

    if "mistral" in mid or "pixtral" in mid:
        return {
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_b64}"
                            },
                        },
                        {"type": "text", "text": user_prompt},
                    ],
                },
            ],
            "max_tokens": 512,
            "temperature": temperature,
        }

    raise ValueError(f"Unrecognised model family for model_id: {model_id}")


def _extract_text(model_id: str, body: dict) -> str:
    """Pull the assistant response text from model-specific response structure."""
    mid = model_id.lower()

    if "anthropic" in mid or "claude" in mid:
        return body["content"][0]["text"]

    if "nova" in mid or "amazon" in mid:
        return body["output"]["message"]["content"][0]["text"]

    if "mistral" in mid or "pixtral" in mid:
        outputs = body.get("outputs") or body.get("choices", [])
        if outputs:
            item = outputs[0]
            return item.get("text") or item["message"]["content"]
        raise ValueError(f"Cannot extract text from Mistral response: {body}")

    raise ValueError(f"Unrecognised model family for model_id: {model_id}")


def _extract_usage(model_id: str, body: dict) -> dict:
    """Extract token usage including cache fields from the response body."""
    mid = model_id.lower()
    if "anthropic" in mid or "claude" in mid:
        u = body.get("usage", {})
        return {
            "input_tokens":               u.get("input_tokens"),
            "output_tokens":              u.get("output_tokens"),
            "cache_read_input_tokens":    u.get("cache_read_input_tokens", 0),
            "cache_creation_input_tokens": u.get("cache_creation_input_tokens", 0),
        }
    if "nova" in mid or "amazon" in mid:
        u = body.get("usage", {})
        return {
            "input_tokens":  u.get("inputTokens"),
            "output_tokens": u.get("outputTokens"),
            "cache_read_input_tokens":    u.get("cacheReadInputTokenCount", 0),
            "cache_creation_input_tokens": u.get("cacheWriteInputTokenCount", 0),
        }
    # Mistral / Pixtral
    u = body.get("usage", {})
    return {
        "input_tokens":  u.get("prompt_tokens"),
        "output_tokens": u.get("completion_tokens"),
        "cache_read_input_tokens":    0,
        "cache_creation_input_tokens": 0,
    }


def call_model(
    client, model_id: str, image_bytes: bytes, temperature: float, run_index: int
) -> tuple[str, dict]:
    """Invoke a Bedrock model via invoke_model.
    Returns (response_text, usage_dict).
    """
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    body = _build_request_body(model_id, image_b64, temperature, run_index)
    response = client.invoke_model(
        modelId=model_id,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json",
    )
    response_body = json.loads(response["body"].read())
    text  = _extract_text(model_id, response_body)
    usage = _extract_usage(model_id, response_body)
    return text, usage


# ---------------------------------------------------------------------------
# Direction detection
# ---------------------------------------------------------------------------

_LEFT_PHRASES = [
    "turn left", "curves left", "curving left", "bends left", "turning left",
    "left turn", "left curve", "left bend", "veering left", "going left",
    "curve to the left", "curving to the left", "turn to the left", "bending to the left",
    "bear left", "bearing left",
]

_RIGHT_PHRASES = [
    "turn right", "curves right", "curving right", "bends right", "turning right",
    "right turn", "right curve", "right bend", "veering right", "going right",
    "curve to the right", "curving to the right", "turn to the right", "bending to the right",
    "bear right", "bearing right",
]

_STRAIGHT_PHRASES = [
    "going straight", "goes straight", "straight ahead", "driving straight",
    "continuing straight", "tracks straight", "is straight", "appears straight",
    "appears to be going straight", "appears to be straight",
]


def detect_direction(text: str) -> str:
    """
    Detect turn direction from the first full sentence (up to the first '.').
    Returns 'left', 'right', 'straight', or 'unknown'.
    """
    first = text.split(".")[0].lower()
    first = re.sub(r"[*_`#]", "", first)  # strip markdown formatting
    left_hits     = sum(1 for p in _LEFT_PHRASES     if p in first)
    right_hits    = sum(1 for p in _RIGHT_PHRASES    if p in first)
    straight_hits = sum(1 for p in _STRAIGHT_PHRASES if p in first)
    best = max(left_hits, right_hits, straight_hits)
    if best == 0:
        return "unknown"
    if [left_hits, right_hits, straight_hits].count(best) > 1:
        return "unknown"
    if left_hits == best:
        return "left"
    if right_hits == best:
        return "right"
    return "straight"


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------

def run_benchmark(
    models: list,
    n_runs: int,
    region: str,
    temperature: float,
    image_path: Path,
    ground_truth: str | None,
) -> dict:
    client = boto3.client("bedrock-runtime", region_name=region)
    image_bytes = image_path.read_bytes()

    all_results: dict = {}

    for model_id in models:
        print(f"\n{'=' * 62}")
        print(f"Model : {model_id}")
        print(f"{'=' * 62}")

        correct = 0
        runs = []

        for i in range(1, n_runs + 1):
            try:
                text, usage = call_model(client, model_id, image_bytes, temperature, i)
                direction   = detect_direction(text)
                ok          = (direction == ground_truth) if ground_truth else None
                if ok is not None:
                    correct += int(ok)

                cache_read = usage.get("cache_read_input_tokens") or 0
                cache_new  = usage.get("cache_creation_input_tokens") or 0
                cache_tag  = f" cache=r{cache_read}/w{cache_new}" if (cache_read or cache_new) else ""

                preview = text[:110].replace("\n", " ")
                flag    = ("✓" if ok else "✗") if ok is not None else "?"
                print(
                    f"  Run {i:>2}: {flag}  detected={direction:<8}"
                    f"{cache_tag:<20} | {preview}…"
                )
                runs.append(
                    {"run": i, "detected": direction, "correct": ok,
                     "usage": usage, "response": text}
                )

            except ClientError as exc:
                err = exc.response["Error"]["Message"]
                print(f"  Run {i:>2}: ✗  ERROR — {err}")
                runs.append({"run": i, "correct": False, "error": err})

        accuracy = correct / n_runs * 100 if ground_truth else None
        if accuracy is not None:
            print(f"\n  \u2192 {correct}/{n_runs} correct  ({accuracy:.0f}% accuracy)")
        else:
            print(f"\n  (no ground truth — accuracy not computed)")

        all_results[model_id] = {
            "correct": correct if ground_truth else None,
            "total": n_runs,
            "accuracy_pct": round(accuracy, 1) if accuracy is not None else None,
            "runs": runs,
        }

    return all_results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark LLMs on detecting a left turn from a DeepRacer "
            "camera image using AWS Bedrock."
        )
    )
    parser.add_argument(
        "image",
        metavar="IMAGE",
        help="Path to the JPEG image to test.",
    )
    parser.add_argument(
        "--ground-truth",
        default=None,
        choices=["left", "right", "straight"],
        help="Expected turn direction for accuracy scoring (omit to skip scoring).",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        required=True,
        metavar="MODEL_ID",
        help="One or more Bedrock model IDs to test.",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="Number of times each model is tested (default: 3).",
    )
    parser.add_argument(
        "--region",
        default="eu-central-1",
        help="AWS region for Bedrock (default: eu-central-1).",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=1.0,
        help="Sampling temperature (default: 1.0). Lower values → more deterministic.",
    )
    parser.add_argument(
        "--output",
        default=None,
        metavar="PATH",
        help="Optional path to write full JSON results.",
    )
    args = parser.parse_args()

    image_path = Path(args.image)
    if not image_path.exists():
        print(f"ERROR: image not found at {image_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Image        : {image_path}")
    print(f"Ground truth : {args.ground_truth or '(not set — accuracy scoring disabled)'}")
    print(f"Runs/model   : {args.runs}")
    print(f"Temperature  : {args.temperature}")
    print(f"Region       : {args.region}")

    results = run_benchmark(
        args.models, args.runs, args.region, args.temperature, image_path, args.ground_truth
    )

    # Summary table
    print(f"\n{'=' * 62}")
    print("SUMMARY")
    print(f"{'=' * 62}")
    col = 48
    print(f"{'Model':<{col}} {'Correct':>7}  {'Accuracy':>8}")
    print("-" * (col + 20))
    for model_id, res in results.items():
        print(
            f"{model_id:<{col}} "
            f"{res['correct']}/{res['total']:>3}     "
            f"{res['accuracy_pct']:>6.1f}%"
        )

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(json.dumps(results, indent=2))
        print(f"\nResults written to {out_path}")


if __name__ == "__main__":
    main()
