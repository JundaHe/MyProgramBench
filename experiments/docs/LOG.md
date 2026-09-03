# Experiment log (append-only, newest at the bottom)

## 2026-09-03

- Read the model-card protocol; decided the 34-task exclusion must be re-measured (`00-plan.md`).
- Probed the workstation: Docker forbidden, rootless containers blocked by AppArmor, Apptainer works
  (`01-environment.md`). Installed `uv`, `uv sync` in `/scratch/jundahe/ProgramBench` (v1.2.4).
- Wrote `scripts/pbdocker` (docker→Apptainer shim), `scripts/prep_image.sh`, `scripts/make_gold_run.py`.
- Pulled `abishekvashok__cmatrix.5c082c6:task_cleanroom_v6` as a sandbox (3.0 GB); synced its test
  blob from HF (snapshot `de0ddfb6`).
- Shim smoke test passed (login shell).
- Generated `/scratch/jundahe/pb-runs/gold/` (200 submissions, each `compile.sh` = copy reference binary).
- Slurm job **5501** (`debug`, 8 cores): `programbench eval` of the cmatrix gold submission →
  `/scratch/jundahe/pb-runs/gold-eval/`. Log: `logs/gold-eval-5501.out`.
- Job 5501 done (5.5 min): cmatrix gold = **90** on kept tests (569/632); raw 933 passed / 73 failure /
  115 error / 24 skipped of 1145. All errors and most failures were tmux: `error connecting to
  /tmp/tmux-1009/default`. Root cause: `apptainer exec` inherits the host env, and my shell runs
  inside tmux, so `$TMUX` leaked into the container (also via `sbatch --export=ALL`). Fix: shim
  passes `--cleanenv` on every exec (docker exec never inherits host env). Verified tmux works.
- Found that `apptainer build --sandbox` squashes file ownership (everything → invoking user), even
  with `--fakeroot`/`--disable-cache`. Docker Hub layers show `/workspace` and `/home/agent` are
  uid 1000 (`agent`). Wrote `scripts/fix_ownership.py` (re-applies uid/gid from the layer tars via
  fakeroot chown); wired into `prep_image.sh`; applied to the cmatrix image. Eval is unaffected
  (runs as root) but mini-swe-agent's `--user agent` needs it.
- `programbench blob sync` (all tasks) done: 7.7 GB under `$HF_HOME`.
- Job **5502** (`normal`, 1 day): pull all 200 images sequentially (`scripts/prep_all_images.slurm`).
- Job **5503**: re-run cmatrix gold with the fixed shim (`FORCE=1`).
- Wrote `scripts/score_gold.py` (raw vs kept pass rate, exclusion list, gold-passing mask).
- Job 5503 failed at `seed_git`: `fatal: detected dubious ownership in repository at '/workspace'`.
  After the ownership fix `/workspace` belongs to `agent`; root's `git` relies on the image's
  `/root/.gitconfig` (`safe.directory /workspace`), but `--containall` masks `$HOME` with an empty
  session dir. Fix: `--no-home` (image's `/root` visible, writable via overlay) and bind per-container
  host dirs over `/tmp` **and** `/var/tmp` (both were 64 MiB tmpfs). Verified git init/add works.
- Job **5504**: cmatrix gold re-run (3rd attempt) with the fixed shim.
- Job 5504 done (9 min): cmatrix gold = **97** (521/536 kept; raw 793/815). All 15 remaining kept
  failures are 2–5 s timeouts on tests expecting the binary to fail fast without a TTY. Cause:
  apptainer forwards the host `$TERM` (`tmux-256color`) even under `--cleanenv`, so ncurses finds a
  terminfo entry and cmatrix draws into the pipe forever; docker exec has no `$TERM`. Fix: shim runs
  every exec through `env -u TERM` → `Error opening terminal: unknown.` rc=1, as in Docker.
- The experiments repo now lives at `/scratch/jundahe/ProgramBench/experiments` on branch
  `experiments` of the user's fork (`fork` = github.com/JundaHe/MyProgramBench);
  `/scratch/jundahe/programbench-experiments` is a symlink to it. Jobs started before the move keep
  writing their logs into `/scratch/jundahe/programbench-experiments.old/logs/` (copy over when done).
- Job **5506**: cmatrix gold, 4th run, with `env -u TERM`.
- Job 5506 done (6 min): cmatrix gold = **100 ✅** (506/506 kept; raw 770/771, 14 branches, no
  branch errors). Pipeline validated. Raw test counts differed across the four runs (1145 → 815 →
  771): the extra entries in the bad runs came with the failures (rerun/setup-error entries), to be
  checked on a task with genuine gold failures before trusting raw counts.
- Job **5508** (`normal`, 24 cores, 3 workers × 8 xdist): `scripts/gold_eval_loop.slurm` — evaluates
  every prepared image in rounds until the prep job 5502 finishes and nothing is pending.
  Results: `/scratch/jundahe/pb-runs/gold-eval/gold/<iid>/`.
