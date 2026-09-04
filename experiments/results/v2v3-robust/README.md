# Official benchmark definition — robust version (two independent gold runs)

Built from two complete, independent gold measurements under the final configuration:
- run A: `gold-eval-v2` + its host-network re-runs (11 network-dependent tasks)
- run B: `gold-eval-v3` (exact repeat) + its host-network re-runs; sqlite/skeema re-evaluated on an idle node

Rule (`scripts/score_gold_robust.py`):
- a task is **excluded** if its raw pass rate is < 0.9 in *either* run (min over runs)
- the scoring mask keeps only tests the reference passed in *both* runs

Result: **20 tasks excluded, 180 remain** — identical to the single-run `results/v2/` list. 161/200
tasks have identical pass rates to 3 decimals across the runs; only 21 tests (of ~340k) flipped and
were dropped from the mask. The benchmark is effectively deterministic on this setup.

Files: `gold_scores.json` (per-run rates, flipped-test counts, sources), `excluded_tasks.json`,
`gold_passing_tests.json.gz` (mask). Score a run with `scripts/score_submission.py <run_dir>`
(this directory is the default).
