# v2 gold pass — FINAL (200/200 tasks, 2026-09-04)

The authoritative benchmark definition. Reference binary evaluated with unmodified `programbench eval`
v1.2.4 through the Apptainer shim (isolated network namespace + unix-socket proxy, `/tmp` 1777,
ICMP enabled; tinycc gold built from upstream source). 11 tasks whose tests need real outbound
network were additionally evaluated with host networking; per task the mode with the higher raw pass
rate is used (`source` field in `gold_scores.json`; 8 tasks come from the host-network run).

**Result: 20 tasks excluded (raw pass rate < 0.9), 180 tasks remain.**

- `gold_scores.json` — per task: raw and post-ignore-list pass rates, status counts, branch errors, executable hash, source run
- `excluded_tasks.json` — the exclusion list
- `gold_passing_tests.json.gz` — per remaining task, the `branch/test` names the reference passes (scoring mask)

Score a run: `scripts/score_submission.py <run_dir>`. Criterion and rationale: `docs/04-exclusion-logic.md`.
Raw eval outputs: `/scratch/jundahe/pb-runs/gold-eval-v2/` and `gold-eval-v2-hostnet/`.
