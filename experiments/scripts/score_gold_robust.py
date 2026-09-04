#!/usr/bin/env python3
"""Robust benchmark definition from several independent gold runs.

    scripts/score_gold_robust.py <results_out> <run1> <run2> ...

Each <run> is one gold measurement: a comma-separated list of eval dirs that together form that
measurement (e.g. the isolated-netns pass plus its host-network re-runs; per task the dir with the
higher raw pass rate is used, as in score_gold.py). Across runs:

  excluded  = tasks whose raw pass rate is < 0.9 in ANY run  (a task that can dip below the threshold
              on a re-run is treated as unreliable — the user's flakiness concern)
  mask      = tests the reference passed in EVERY run (a test that flips between runs is dropped, so
              a submission is never scored on a test the reference itself fails sometimes)

Writes gold_scores.json (per task: per-run raw rates, min/max, flipped-test count), excluded_tasks.json,
gold_passing_tests.json.gz, README.md.
"""

import gzip
import json
import sys
from pathlib import Path

THRESHOLD = 0.9


def load_run(dirs: list[Path]) -> dict[str, dict]:
    best: dict[str, dict] = {}
    for d in dirs:
        for p in d.glob("*/*.eval.json"):
            r = json.loads(p.read_text())
            tests = r["test_results"]
            rate = sum(t["status"] == "passed" for t in tests) / max(1, len(tests))
            if p.parent.name not in best or best[p.parent.name]["rate"] < rate:
                best[p.parent.name] = {
                    "rate": rate, "source": str(d), "n": len(tests),
                    "passed": {f"{t['branch']}/{t['name']}" for t in tests if t["status"] == "passed"},
                    "all": {f"{t['branch']}/{t['name']}" for t in tests},
                }
    return best


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    runs = [load_run([Path(x) for x in arg.split(",")]) for arg in sys.argv[2:]]
    tasks = sorted(set.intersection(*(set(r) for r in runs)))
    rows, mask = {}, {}
    for iid in tasks:
        rates = [r[iid]["rate"] for r in runs]
        common = set.intersection(*(r[iid]["all"] for r in runs))
        always = set.intersection(*(r[iid]["passed"] for r in runs))
        flipped = sum(1 for t in common if any(t in r[iid]["passed"] for r in runs) and t not in always)
        rows[iid] = {"raw_rates": rates, "min_rate": min(rates), "max_rate": max(rates), "flipped_tests": flipped,
                     "tests_in_all_runs": len(common), "sources": [r[iid]["source"] for r in runs]}
        mask[iid] = sorted(always)
    excluded = sorted(i for i, x in rows.items() if x["min_rate"] < THRESHOLD)
    (out / "gold_scores.json").write_text(json.dumps(rows, indent=1, sort_keys=True))
    (out / "excluded_tasks.json").write_text(json.dumps({"threshold": THRESHOLD, "rule": "min raw rate over runs", "excluded": excluded}, indent=1))
    with gzip.open(out / "gold_passing_tests.json.gz", "wt") as f:
        json.dump({i: mask[i] for i in tasks if i not in excluded}, f)
    n_flip = sum(x["flipped_tests"] for x in rows.values())
    print(f"{len(tasks)} tasks over {len(runs)} runs; {len(excluded)} excluded (min raw < {THRESHOLD}); {len(tasks) - len(excluded)} remain; "
          f"{n_flip} tests flipped between runs (dropped from the mask)")
    for i, x in sorted(rows.items(), key=lambda kv: kv[1]["min_rate"]):
        if x["min_rate"] < 0.95 or x["flipped_tests"] >= 10:
            print(f"  {' / '.join(f'{r:.3f}' for r in x['raw_rates'])}  flipped={x['flipped_tests']:4d}  {i}{'  EXCLUDED' if i in excluded else ''}")


if __name__ == "__main__":
    main()
