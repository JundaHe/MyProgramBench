# Plan

Goal: reproduce the ProgramBench protocol used in the Claude 5 model card (§8.11.1) so that our
numbers are comparable to the 87.6 / 85.4 / 86.3 reported there.

## Protocol, decomposed

| # | Model-card sentence | What it means operationally | Status |
|---|---|---|---|
| 1 | "excluded 34 tasks for which the reference binary itself scored below 0.9 on the hidden test suite" | Run the **reference binary** through the full eval, compute per-task pass rate over the raw hidden tests, drop tasks < 0.9 | in progress → `02-gold-run.md` |
| 2 | "we score only against tests the reference binary passes" | From the same gold run, keep the per-test pass/fail mask; score submissions only on gold-passing tests | after 1 |
| 3 | "same mini-swe-agent harness that the upstream repo uses, without the six-hour time limit" | Set up `mini-swe-agent`'s `programbench` runner with the time limit removed | `03-mini-swe-agent.md` |

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
- **Scoring of gold.** We read raw `test_results` from each `*.eval.json` (not `programbench info`,
  which first drops `tests.json`'s ignored tests) because the model card's ratio is over the
  hidden suite as run.
