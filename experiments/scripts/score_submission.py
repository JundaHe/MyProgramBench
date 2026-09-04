#!/usr/bin/env python3
"""Score an evaluated run against the benchmark definition in results/<version>/.

    scripts/score_submission.py <run_dir with <iid>/<iid>.eval.json> [--results experiments/results/v2]

Per task (only tasks not in excluded_tasks.json), counting test-result ENTRIES exactly like
programbench's own score (pytest-rerunfailures records each attempt, so a flaky test contributes
its failed attempts too), restricted to tests the reference passes:

    score = #entries(status == passed, name ∈ gold_passing) / #entries(name ∈ gold_passing)

Benchmark score = mean over all remaining tasks; a task with no eval.json counts as 0.
"""

import argparse
import gzip
import json
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--results", type=Path, default=Path(__file__).resolve().parent.parent / "results" / "v2v3-robust")
    args = ap.parse_args()
    mask = json.loads(gzip.open(args.results / "gold_passing_tests.json.gz").read())
    scores = {}
    for iid, tests in sorted(mask.items()):
        p = args.run_dir / iid / f"{iid}.eval.json"
        if not p.exists():
            scores[iid] = 0.0
            continue
        names = set(tests)
        entries = [t for t in json.loads(p.read_text())["test_results"] if f"{t['branch']}/{t['name']}" in names]
        scores[iid] = sum(t["status"] == "passed" for t in entries) / len(entries) if entries else 0.0
    for iid, s in scores.items():
        print(f"{s:.3f}  {iid}")
    n_eval = sum(1 for iid in mask if (args.run_dir / iid / (iid + ".eval.json")).exists())
    print(f"benchmark score: {sum(scores.values()) / len(scores):.4f} over {len(scores)} tasks ({n_eval} evaluated)")


if __name__ == "__main__":
    main()
