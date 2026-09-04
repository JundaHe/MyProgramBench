# Step 1: gold run → task exclusion list

Model card: "We excluded 34 tasks for which the reference binary itself scored below 0.9 on the
hidden test suite (indicating test flakiness), leaving 166 tasks. Among those tasks, we score only
against tests the reference binary passes."

## Method

1. **Gold submission per task** (`scripts/make_gold_run.py` → `/scratch/jundahe/pb-runs/gold/<iid>/submission.tar.gz`).
   Each archive contains only:
   ```sh
   #!/bin/sh
   set -e
   cp /opt/programbench-reference/executable ./executable
   chmod +x ./executable
   ```
   `/opt/programbench-reference/executable` is placed there by the `pbdocker` shim
   (`PBDOCKER_EXPOSE_REFERENCE=1`) at container start, copied from the image's
   `/workspace/executable` *before* the eval wipes `/workspace`. So the binary under test is
   byte-for-byte the task's reference binary from the `task_cleanroom_v6` image.
2. **Unmodified `programbench eval`** (v1.2.4) with `PROGRAMBENCH_DOCKER_EXECUTABLE=scripts/pbdocker`,
   through `scripts/gold_eval.slurm`. Results land in `/scratch/jundahe/pb-runs/gold-eval/gold/<iid>/<iid>.eval.json`.
3. **Scoring** (`scripts/score_gold.py`, to write): per task, over the *raw* `test_results` in the
   eval.json (every hidden test the harness ran, before `tests.json` ignore lists):
   `gold_pass_rate = #passed / #tests`. Tasks with `gold_pass_rate < 0.9` → `results/excluded_tasks.json`.
   For the remaining tasks, the set of gold-passing tests → `results/gold_passing_tests.json`
   (used later as the scoring mask, per the second sentence of the protocol).

Points that need a decision once data is in:

- Whether a test that is `not_run`/`error` because a whole branch errored counts as a failure for
  the ratio (the card is silent; default: yes, it is "not passed").
- Whether to run gold more than once to separate flaky from deterministic failures. The card
  used a single measurement; start with one run, repeat only the tasks near the 0.9 boundary.

## Runs

| Job | Scope | Partition/CPUs | Status |
|---|---|---|---|
| 5501, 5503, 5504, 5506 | `abishekvashok__cmatrix` (smoke; 4 rounds while fixing the shim) | debug / 8 | 100 ✅ on the 4th run |
| 5510 → 5530 + 5531 | v1 pass (host network), all tasks → `results/v1-hostnet/` | normal / 12+4 | done: 9 excluded / 191 remain |
| 5532 + 5533 | v2 pass: isolated netns + proxy, tinycc source-built gold → `gold-eval-v2` | normal / 12+4 | done (6 h) |
| 5534 | host-network re-run of 11 network-dependent tasks → `gold-eval-v2-hostnet` | normal / 8 | done |
| 5535 | pingu re-run with ICMP enabled | debug / 8 | done |

## Results

**Final: 20 excluded / 180 remain** — `results/v2v3-robust/` (min over two independent runs, mask = intersection; identical task set to the single-run `results/v2/`).

Excluded: axodotdev__oranda.27d60c7, bootandy__dust.62bf1e1, doxygen__doxygen.966d98e, duckdb__duckdb.bdb65ec, esubaalew__run.0fb9dec, ffmpeg__ffmpeg.360a402, hairyhenderson__gomplate.05eb3aa, halitechallenge__halite.822cfb6, lfos__calcurse.49180d5, mgechev__revive.201451e, nachoparker__dutree.44e877d, nikoladucak__caps-log.2cf2d1e, nukesor__pueue.8b9d6fe, osgeo__proj.75d455c, php__php-src.c891263, segmentio__chamber.5f93f5f, skeema__skeema.6a76243, sqlite__sqlite.839433d, tstack__lnav.ee34494, zevv__duc.a58fa4e

v1 (`results/v1-hostnet/`) is archived only.
