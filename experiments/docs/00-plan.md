# Plan

Goal: reproduce the ProgramBench protocol used in the Claude 5 model card (§8.11.1) so that our
numbers are comparable to the 87.6 / 85.4 / 86.3 reported there.

## Protocol, decomposed

| # | Model-card sentence | What it means operationally | Status |
|---|---|---|---|
| 1 | "excluded 34 tasks for which the reference binary itself scored below 0.9 on the hidden test suite" | Run the **reference binary** through the full eval, compute per-task pass rate over the raw hidden tests, drop tasks < 0.9 | in progress → `02-gold-run.md` |
| 2 | "we score only against tests the reference binary passes" | From the same gold run, keep the per-test pass/fail mask; score submissions only on gold-passing tests | after 1 |
| 3 | "same mini-swe-agent harness that the upstream repo uses, without the six-hour time limit" | Set up `mini-swe-agent`'s `programbench` runner with the time limit removed | configured, **out of scope** (no model runs; see below) |

## Scope (decided 2026-09-03)

Deliverable is the **benchmark definition only**: the task exclusion list and the gold-passing test
mask (`results/`), plus instructions for scoring a submission with them. No agent/model inference
is run here; `03-mini-swe-agent.md` documents the harness setup for whoever runs one later.

## Decisions

- **Exact 34 cannot be copied; it must be re-measured.** The 34 task IDs are not published, and
  the criterion is a measured quantity (gold pass rate). The public `tests.json` already ignores
  `gold_fail`/`gold_flaky` tests; reconstructing a ratio from those gives 54 tasks < 0.9, not 34, so
  the offline approximation was rejected. See `02-gold-run.md`.
- **200 vs 201 tasks.** `src/programbench/data/tasks/` has 201 directories; one is the bundled
  fixture `testorg__calculator.abc1234` (`submission.py: FIXTURE_PREFIX`). The benchmark is 200.
  The gold run generator skips the fixture.
- **Benchmark version.** All public releases (v1.0.0 → v1.2.4) ship the same 201 task dirs; we pin
  upstream commit `963063c` (v1.2.4). Hidden tests come from HF `programbench/ProgramBench-Tests`
  snapshot `de0ddfb637590c7ecb54fa0b5301f6dc7dfbcee5` (recorded by `programbench blob sync`).
- **No Docker on this machine → Apptainer through a docker-CLI shim.** See `01-environment.md`.
  programbench is used unmodified; only `PROGRAMBENCH_DOCKER_EXECUTABLE` is pointed at the shim.
- **Reference binary access.** The eval wipes `/workspace` before `compile.sh`, and the reference
  binary lives at `/workspace/executable` (mode `--x--x--x`). The shim copies it to
  `/opt/programbench-reference/executable` at container start when `PBDOCKER_EXPOSE_REFERENCE=1`;
  the gold `compile.sh` is just `cp` from there. This flag is never set for agent runs.
- **Scoring of gold (decided 2026-09-04).** The exclusion ratio is over the **raw** hidden test suite
  as run — all `test_results` in each `*.eval.json`, *without* applying `tests.json`'s ignore lists.
  Those lists already remove tests that fail on gold, so applying them first inflates every score
  (median 0.9999 vs 0.985 raw) and would exclude only 9 tasks instead of a number near the model
  card's 34. The gold-passing mask is likewise taken over all tests run. `kept` (post-ignore) rates are
  reported for reference only.
- **Single measurement, our own.** The v2 pass (isolated network namespace, `/tmp` fix, tinycc
  source-built gold) is the authoritative run; the earlier v1 pass is archived under
  `results/v1-hostnet/` but is not used for comparison or scoring.
