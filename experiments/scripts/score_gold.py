#!/usr/bin/env python3
"""Score a gold eval directory and derive the task exclusion list + gold-passing test mask.

    scripts/score_gold.py <eval_dir e.g. /scratch/jundahe/pb-runs/gold-eval/gold> <results_dir>

Per task, two pass rates are reported:
  raw   = passed / all test_results the harness ran (the hidden test suite, before any tests.json ignore list)
  kept  = programbench's own score: after dropping tests.json ignored branches/tests
Exclusion (< 0.9) uses `raw`: the model card's "reference binary scored below 0.9 on the hidden test
suite" refers to the suite as run, and the public ignore lists (which already drop gold-failing tests)
would inflate every score (median kept 0.9999 vs raw 0.985 in our runs). `kept` is reported for reference.
The gold-passing mask is likewise taken over all tests run (not only the kept ones).
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, "/scratch/jundahe/ProgramBench/src")
from programbench.utils.load_data import get_active_branches, get_ignored_tests, load_all_instances  # noqa: E402

THRESHOLD = 0.9


def main() -> None:
    eval_dir, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    instances = {i["instance_id"]: i for i in load_all_instances()}
    rows, passing = {}, {}
    for p in sorted(eval_dir.glob("*/*.eval.json")):
        iid = p.parent.name
        r = json.loads(p.read_text())
        active, ignored = set(get_active_branches(instances[iid])), get_ignored_tests(instances[iid])
        raw = Counter(t["status"] for t in r["test_results"])
        kept = [t for t in r["test_results"] if t["branch"] in active and f"{t['branch']}/{t['name']}" not in ignored]
        kept_c = Counter(t["status"] for t in kept)
        rows[iid] = {
            "raw": dict(raw), "raw_rate": raw["passed"] / max(1, len(r["test_results"])),
            "kept": dict(kept_c), "kept_rate": kept_c["passed"] / max(1, len(kept)),
            "error_code": r["error_code"], "branch_errors": sorted(r["test_branch_errors"]),
            "executable_hash": r["executable_hash"],
        }
        passing[iid] = sorted(f"{t['branch']}/{t['name']}" for t in r["test_results"] if t["status"] == "passed")
    excluded = sorted(i for i, x in rows.items() if x["raw_rate"] < THRESHOLD)
    (out / "gold_scores.json").write_text(json.dumps(rows, indent=1, sort_keys=True))
    (out / "excluded_tasks.json").write_text(json.dumps({"threshold": THRESHOLD, "excluded": excluded}, indent=1))
    (out / "gold_passing_tests.json").write_text(json.dumps({i: passing[i] for i in rows if i not in excluded}, sort_keys=True))
    print(f"{len(rows)} tasks scored; {len(excluded)} excluded (< {THRESHOLD}); {len(rows) - len(excluded)} remain")
    for i, x in sorted(rows.items(), key=lambda kv: kv[1]["raw_rate"]):
        print(f"{x['raw_rate']:.3f} raw  {x['kept_rate']:.3f} kept  {i}{'  EXCLUDED' if i in excluded else ''}")


if __name__ == "__main__":
    main()
