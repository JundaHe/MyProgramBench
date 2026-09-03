#!/usr/bin/env python3
"""Score an evaluated run against the benchmark definition in results/<version>/.

    scripts/score_submission.py <run_dir with <iid>/<iid>.eval.json> [--results experiments/results/v2]

Per task (only tasks not in excluded_tasks.json):  score = |passed ∩ gold_passing| / |gold_passing|
Benchmark score = mean over all remaining tasks; a task with no eval.json counts as 0.
"""

import argparse
import gzip
import json
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--results", type=Path, default=Path(__file__).resolve().parent.parent / "results" / "v2")
    args = ap.parse_args()
    mask = json.loads(gzip.open(args.results / "gold_passing_tests.json.gz").read())
    scores = {}
    for iid, tests in sorted(mask.items()):
        p = args.run_dir / iid / f"{iid}.eval.json"
        if not p.exists():
            scores[iid] = 0.0
            continue
        passed = {f"{t['branch']}/{t['name']}" for t in json.loads(p.read_text())["test_results"] if t["status"] == "passed"}
        scores[iid] = len(passed & set(tests)) / len(set(tests))
    for iid, s in scores.items():
        print(f"{s:.3f}  {iid}")
    print(f"benchmark score: {sum(scores.values()) / len(scores):.4f} over {len(scores)} tasks "
          f"({sum(1 for iid in mask if (args.run_dir / iid / f'{iid}.eval.json').exists())} evaluated)")


if __name__ == "__main__":
    main()
