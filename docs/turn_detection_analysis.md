# Turn Detection Benchmark Analysis

**Date:** 2026-03-29  
**Script:** `scripts/turn_detection_benchmark.py`  
**Settings:** 25 runs per model, temperature=0.1, region=eu-central-1

## Experiment Setup

Five experiments were run across two image resolutions. Experiments 1–3 used 160×120 images extracted directly from the DeepRacer simulator (the native camera resolution). Experiments 4–5 used 640×480 upscaled versions of equivalent left/right turn images to test whether resolution affects model accuracy.

All models were asked to describe the track ahead and state the turn direction explicitly. The verdict was extracted from the first sentence of each response.

| Experiment | Image | Resolution | Ground truth | Notes |
|---|---|---|---|---|
| left_right_1 | `step026_img.jpg` | 160×120 | Left turn | Gradual left curve |
| left_right_2 | `step075_img.jpg` | 160×120 | Right turn | Pronounced right curve, green wall left |
| left_right_3 | `step002_img.jpg` | 160×120 | Straight | Centerline straight ahead |
| left_right_4 | `images/left.jpg` | 640×480 | Left turn | Same scenario, higher resolution |
| left_right_5 | `images/right.jpg` | 640×480 | Right turn | Same scenario, higher resolution |

---

## Results — 160×120 (native DeepRacer resolution)

### Experiment 1 — Left turn (step 26)

| Model | Correct | Accuracy |
|---|---|---|
| Claude Sonnet 4.6 | 6/25 | 24% |
| Amazon Nova Pro | 16/25 | 64% |
| Mistral Pixtral Large | 0/25 | 0% |

Claude was uncertain, essentially guessing with a slight bias toward right (19/25 right). Nova had a reasonable majority toward the correct answer. Pixtral was systematically wrong — 25/25 right — with completely deterministic incorrect responses at temperature=0.1.

### Experiment 2 — Right turn (step 75)

| Model | Correct | Accuracy |
|---|---|---|
| Claude Sonnet 4.6 | 0/25 | 0% |
| Amazon Nova Pro | 25/25 | 100% |
| Mistral Pixtral Large | 25/25 | 100% |

This was the clearest image — a pronounced right-hand bend with a highly visible green wall on the left. Nova was perfectly correct and consistent. Claude was systematically wrong in the opposite direction, calling it a left curve on all 25 runs — a strong, consistent disagreement on an unambiguous image, suggesting Claude interprets the perspective differently, possibly anchoring on the near-side boundary rather than the vanishing point of the track. Pixtral also scores 100% here, but this is not a meaningful result — Pixtral outputs "right" on every image regardless of actual direction. Its correct score on this experiment is purely coincidental and reflects its hardcoded output bias, not genuine detection.

### Experiment 3 — Straight (step 2)

| Model | Correct | Accuracy |
|---|---|---|
| Claude Sonnet 4.6 | 25/25 | 100% |
| Amazon Nova Pro | 15/25 | 60% |
| Mistral Pixtral Large | 0/25 | 0% |

Claude was perfect and fully consistent. Nova correctly identified straight most of the time but hallucinated curves on 10 runs (7 right, 3 left). Pixtral called right on all 25 runs — consistent with its behaviour across every experiment. It does not consider "straight" (or "left") a valid output; it always outputs "right".

---

## Summary Table — 160×120

| Model | Left | Right | Straight | Average |
|---|---|---|---|---|
| Claude Sonnet 4.6 | 24% | 0% | 100% | **41%** |
| Amazon Nova Pro | 64% | 100% | 60% | **75%** |
| Mistral Pixtral Large | 0% | 100%* | 0% | — |

*Pixtral outputs "right" on every image. Its right-turn score is not a detection result — it reflects a hardcoded output bias. Pixtral has no functional turn detection capability.

---

## Results — 640×480 (high resolution)

### Experiment 4 — Left turn (640×480)

| Model | Correct | Accuracy |
|---|---|---|
| Claude Sonnet 4.6 | 25/25 | 100% |
| Amazon Nova Pro | 25/25 | 100% |
| Mistral Pixtral Large | 0/25 | 0% |

At higher resolution, Claude and Nova both achieved perfect scores. Claude's earlier perspective inversion on the left-turn image (24% at 160×120) is completely resolved — it now correctly and consistently identifies the left curve on all 25 runs. Nova improves from 64% to 100%. Pixtral calls right on all 25 runs, as it does on every image at every resolution.

### Experiment 5 — Right turn (640×480)

| Model | Correct | Accuracy |
|---|---|---|
| Claude Sonnet 4.6 | 10/25 | 40% |
| Amazon Nova Pro | 25/25 | 100% |
| Mistral Pixtral Large | 25/25 | 100% |

Nova is perfectly consistent on the right turn at high resolution, matching its 160×120 result. Pixtral also scores 100% here — again coincidentally, since it outputs "right" unconditionally. Claude improves from 0% to 40%, meaning the resolution upgrade partially corrects its perspective inversion on right turns, but Claude is still wrong on most runs (15/25 calling it a left curve), indicating a residual systematic bias on right-hand bends even with richer image data.

## Summary Table — 640×480

| Model | Left | Right | Average |
|---|---|---|---|
| Claude Sonnet 4.6 | 100% | 40% | **70%** |
| Amazon Nova Pro | 100% | 100% | **100%** |
| Mistral Pixtral Large | 0% | 100%* | — |

*Pixtral outputs "right" unconditionally at this resolution as well.

---

## Resolution Comparison

| Model | Left 160×120 | Left 640×480 | Right 160×120 | Right 640×480 |
|---|---|---|---|---|
| Claude Sonnet 4.6 | 24% | **100%** (+76pp) | 0% | **40%** (+40pp) |
| Amazon Nova Pro | 64% | **100%** (+36pp) | 100% | **100%** (=) |
| Mistral Pixtral Large | 0% (always "right") | 0% (always "right") | 100%* (always "right") | 100%* (always "right") |

Resolution is a significant factor for Claude: higher resolution provides enough visual detail to anchor its perspective correctly on left turns, and partially on right turns. Nova was already reliable but also benefits on the left-turn case. Pixtral's output is entirely resolution-independent and entirely direction-independent — it always outputs "right", making resolution irrelevant.

---

## Key Observations

**Amazon Nova Pro** is the most reliable model across both resolutions and all directions. It achieved 100% at 640×480 on both left and right turns, and had no accuracy degradation from higher resolution. Its only weakness at 160×120 was occasional uncertainty on straight sections (60%).

**Claude Sonnet 4.6** is highly resolution-sensitive. At the native 160×120 resolution it shows a systematic perspective inversion on curves (24% on left, 0% on right). At 640×480 this is largely corrected (100% on left, 40% on right). The improvement on left turns is complete; on right turns a residual inversion remains, suggesting Claude uses different visual cues for left vs right bends, and the low-resolution image is insufficient to resolve the ambiguity reliably. Claude is uniquely strong on straight detection (100% at 160×120).

**Mistral Pixtral Large** always outputs "right", at every resolution, for every image tested. Its 100% accuracy on right-turn experiments is not a detection result — it is a trivial consequence of a fixed output. The model has no functional ability to detect track direction in the DeepRacer camera perspective. This is not a resolution or detail problem; it is a complete failure of the task regardless of input quality.

## Systematic Bias Summary

| Model | Bias |
|---|---|
| Claude Sonnet 4.6 | Perspective inversion on curves at low resolution; resolution-dependent; excellent at straight |
| Amazon Nova Pro | Slight uncertainty on straights at low resolution; consistently excellent on curves |
| Mistral Pixtral Large | Always outputs "right" — fixed output regardless of image content or resolution |

## Implications for DeepRacer

For use as a driving model, correct curve direction detection is more critical than straight detection (a missed straight is less catastrophic than an inverted turn). 

**Nova Pro** is the strongest candidate at any resolution. It is accurate, consistent, and does not degrade at low resolution.

**Claude** is usable at 640×480 but unreliable at the native DeepRacer camera resolution (160×120). Since DeepRacer operates at 160×120 natively, Claude's inversion at that resolution would cause the car to steer in the wrong direction at corners. The model would need to be deployed with upscaled images — which adds latency — to be viable.

**Pixtral** cannot be used for turn direction detection. It always outputs "right" regardless of what the image shows. Its apparently strong score on right-turn experiments is a meaningless coincidence — a broken clock being right once a day.
