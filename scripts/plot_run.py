#!/usr/bin/env python3
"""Plot lap trace from a simtrace CSV using deepracer-utils.

Usage:
    python plot_run.py <simtrace.csv> [--track TRACK_NAME] [--output OUTPUT_PATH]
"""

import argparse
import matplotlib
matplotlib.use("Agg")

from deepracer.tracks import TrackIO
from deepracer.logs import (
    SimulationLogsIO as slio,
    PlottingUtils as pu,
)

parser = argparse.ArgumentParser(description="Plot a DeepRacer simtrace CSV.")
parser.add_argument("csv", help="Path to simtrace CSV file")
parser.add_argument("--track", default="reinvent_base", help="Track name (default: reinvent_base)")
parser.add_argument("--output", default=None, help="Output image path (default: <csv_stem>_plot.png)")
args = parser.parse_args()

import os
CSV_PATH = args.csv
TRACK_NAME = args.track
OUTPUT_PATH = args.output or os.path.splitext(CSV_PATH)[0] + "_plot.png"

# Load track
track = TrackIO().load_track(TRACK_NAME)

# Prepend SIM_TRACE_LOG: to each data line so SimulationLogsIO can parse the CSV.
# Also convert steps from float (e.g. "1.0") to int ("1") as the parser expects.
with open(CSV_PATH, "r") as f:
    lines = f.readlines()

raw_data = []
for line in lines[1:]:  # skip header
    line = line.strip()
    if not line:
        continue
    parts = line.split(",")
    parts[1] = str(int(float(parts[1])))  # steps: "1.0" -> "1"
    raw_data.append("SIM_TRACE_LOG:" + ",".join(parts))

# Write to a temp file that load_data can consume
import tempfile, os
with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as tmp:
    tmp.write("\n".join(raw_data))
    tmp_path = tmp.name

loaded = slio.load_data(tmp_path)
os.unlink(tmp_path)

df = slio.convert_to_pandas(loaded, episodes_per_iteration=1)

# Determine unique iterations
iterations = [int(i) for i in sorted(df["iteration"].unique())]
print(f"Iterations found: {iterations}")

# Plot all iterations
import matplotlib.pyplot as plt
fig = pu.plot_laps(iterations, df, track, section_to_plot="iteration", style="modern", return_fig=True)
fig.savefig(OUTPUT_PATH, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
print(f"Saved to {OUTPUT_PATH}")
