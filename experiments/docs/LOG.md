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
- Job **5510** (`normal`, 12 cores / 48 GB, 2 workers × 6 xdist; 5508/5509 were cancelled: QoS caps a user at 72 GB total and the node is shared — 28/32 cores were taken by other users): `scripts/gold_eval_loop.slurm` — evaluates
  every prepared image in rounds until the prep job 5502 finishes and nothing is pending.
  Results: `/scratch/jundahe/pb-runs/gold-eval/gold/<iid>/`.
- Pushed branch `experiments` to the fork (SSH key `~/.ssh/id_ed25519` added to the GitHub account; remote `fork` = `git@github.com:JundaHe/MyProgramBench.git`).
- Throughput: node fully allocated (32/32 cores, load ~40; other users hold 16 cores), so no room to
  widen job 5510. Made `pending_tasks.py` cooperative — it skips tasks another running `pb-gold-all`
  job is evaluating (parsed from that job's `=== round:` log line, or `logs/claims-<job>.txt`; the
  5510 round line was truncated by `cut`, so its 66-task list was reconstructed from the prep log
  order into `claims-5510.txt`). Queued a second loop job (4 cores / 16 GB, 1 worker) that starts
  automatically when the image-prep job releases its memory (72 GB per-user cap).
- Job 5502 done (2 h): all 200 images prepared, 0 failures; store = 1.9 TB used on /scratch (`pb-apptainer/images`).
  Log copied from the pre-move directory into `logs/prep-images-5502.out`.
- Gold eval throughput so far: 19 tasks in ~80 min with 2 workers (~4 min/task) → ~13 h for 200
  with two workers; the second job 5512 adds a third once it gets CPUs (QoS also caps CPUs per user).
- Hourly check #1 (18:40): 66/200 evaluated, jobs 5510 (12 c) + 5512 (4 c) running. Partial
  `score_gold.py`: 3/66 below 0.9 (oranda 0.745 — GitHub API 429/404 + proxy TLS errors, i.e.
  network-dependent tests; dust 0.868; doxygen 0.899 — `xmllint` missing from the image).
  **Branch errors** (`results_read_failed`) in deadnix, dust, cppcheck: the branch's `run.sh` does
  `pip install --upgrade pytest ...` at test time, pulling pytest 9.1.1 (image ships 9.0.3); 9.1
  turns "Marks cannot be applied to fixtures" into a collection error inside the image's libtmux
  0.58.0 pytest plugin → no results.xml. Upstream test-suite drift, not the shim; identical under
  Docker today. Kept as measured (protocol = gold as run); open question for the user whether to
  pin pytest to the image version (`PIP_CONSTRAINT`) to get closer to the model card's conditions.
- Hourly check #2 (19:25): 86/200 evaluated. Two problems found and fixed:
  1. **Scheduling bug**: job 5510 exited early ("0 pending") because job 5512's single round had
     claimed every remaining task, leaving the 4-core job to do everything alone. Fix: rounds are
     now bounded (`pending_tasks.py --limit 2*WORKERS`) so loop jobs interleave. Cancelled 5512,
     cleaned its orphan container/committed image, relaunched as jobs **5530** (12 c, 2 workers) and
     **5531** (4 c, 1 worker).
  2. **Shim bug**: the per-container `/tmp` and `/var/tmp` bind dirs were mode 0775, so unprivileged
     users inside the container could not write there — pandoc's big branch (5213 tests) died in
     `apt-get update` (`apt-key` runs as `_apt`: "Couldn't create temporary file /tmp/apt.conf…"),
     giving a bogus gold score of 0.048. Fix: `chmod 1777`. Affected results (pandoc, treemd,
     fselect — the only eval.jsons with /tmp permission symptoms) moved to
     `gold-eval/redo-tmpperm/` so they are re-evaluated.
  Also seen: ffmpeg gold = 0.798 kept (426 tests fail with "Unknown command type: unknown",
  `$(PROGSSUF)` paths — broken generated tests, so a genuine exclusion), pytest-9.1 branch
  collection errors now in 5 tasks.
- Hourly check #3 (21:30): 115/200 evaluated, jobs 5530/5531 healthy, no instance errors. The three
  `/tmp`-affected tasks re-ran: pandoc 0.999, treemd 1.000, fselect 0.954 (was a bogus 0.048 for pandoc).
  Currently 6 excluded: oranda 0.745, ffmpeg 0.798, revive 0.809, dutree 0.843, dust 0.868, doxygen 0.899.
  - revive: 195 kept tests fail because the binary's config needs `go1.24.0` and the image has go1.21
    (`toolchain not available`) — an image limitation, identical under Docker.
  - dutree (and the near-boundary parallel-disk-usage 0.904): goldens encode **host-filesystem
    directory sizes** — expected `subdir 22 B`, we get `4.00 KiB`. 22 B is an XFS short-form
    directory; our /scratch is ext4 (4 KiB dirs), and Docker overlay2 inherits the host FS too. So
    these tests depend on the evaluator's host filesystem; whether Anthropic's hosts were XFS or
    ext4 is unknowable. Cannot be emulated without root (no XFS loop mounts). Recorded as a known
    divergence source: disk-usage tools (dutree, parallel-disk-usage, dust, dua-cli) are the ones
    at risk.
  - `truncate` setup errors in dutree: the target directory does not exist in the branch tar (git
    keeps no empty dirs) — same under Docker.
- Hourly check #4 (22:55): 144/200, jobs healthy, 7 excluded (new: muffet 0.890). **Network-namespace
  problem found**: apptainer containers share the host network, and this host listens on many
  ports (22 sshd, 53, 80, 3306, 8000, 19999 netdata, …). Tests that expect `localhost:19999` /
  `:22` to refuse connections pass under Docker (private netns) but fail here (muffet: 135
  failures on :19999; dropbear: :22/:19999; pixterm), and parallel containers collide on fixed
  ports (bore, oha, quinn: `Address already in use`). ~12 evaluated tasks show port-related
  failures. Plan: give each container its own netns with rootless outbound connectivity (pasta or
  slirp4netns attached to apptainer's `--network none` namespace), then re-evaluate the affected
  tasks. Time-boxed; current jobs keep running meanwhile.
