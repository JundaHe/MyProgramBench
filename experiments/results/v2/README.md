# v2 gold pass — PARTIAL SNAPSHOT (52/200 tasks, committed 2026-09-04 02:20)

Authoritative run (isolated network namespace + proxy, /tmp fix, tinycc source-built gold).
Jobs 5532/5533 are still running; this directory will be overwritten with the full 200-task result.

- `gold_scores.json` — per task: raw and post-ignore pass rates, branch errors, executable hash
- `excluded_tasks.json` — tasks with raw pass rate < 0.9 (the benchmark's exclusion list)
- `gold_passing_tests.json.gz` — per remaining task, the `branch/test` names the reference passes (scoring mask)

Criterion: raw hidden-suite pass rate (see `docs/00-plan.md`).
