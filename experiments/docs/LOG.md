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
- Network isolation solved (23:10). slirp4netns and pasta both fail here (`/dev/net/tun: Operation not
  permitted` inside the user namespace — AppArmor), but filesystem unix sockets cross network
  namespaces, so: `scripts/pbproxy.py serve <sock>` runs one HTTP/CONNECT proxy per Slurm job on a
  unix socket; the shim starts each container with `--net --network none` (loopback only, like
  Docker), binds the socket in, starts `pbproxy.py relay` inside (127.0.0.1:3128) and sets
  `http(s)_proxy` for every exec. Verified: HTTPS/HTTP via proxy, `pip install`, `git ls-remote`,
  `localhost:19999` refused, relay survives across execs and into committed images, and the harness's
  build-time DNS blackhole still blocks downloads (the relay is SIGSTOPped while the blackhole is in
  place). Cost: programs that resolve DNS/connect to the internet without honouring proxy env vars
  cannot reach it. Implemented as `scripts/pbdocker.v2`; swapped in once the v1 (host-network) pass
  finishes so v1 stays internally consistent. Plan: full second pass (`gold-eval-v2`) under the
  final configuration; v1 vs v2 disagreement doubles as a flakiness signal.
- Hourly check #5 (00:05–00:15): 187/200 in v1, 9 excluded so far. Two new low scores are environment
  artefacts of the binary-copy gold / host network:
  - **pingu 0.723**: `socket: permission denied` — ICMP raw sockets need CAP_NET_RAW in the netns owner's
    user namespace; in v1 the container shares the host netns (owned by the init userns) so fakeroot
    has no such capability. Docker grants CAP_NET_RAW. The v2 isolated netns is owned by our userns,
    so raw sockets should work there (to be confirmed in the v2 pass).
  - **tinycc 0.718**: `include file 'stddef.h' not found` — tcc needs `/usr/local/lib/tcc` (libtcc1.a,
    headers) which `make install` creates; the cleanroom image does not contain it at all (the
    reference binary is unusable there even for the agent). "Copy the reference binary" cannot be a
    faithful gold for programs whose build installs support files. The branch tars carry the
    test-generation agent's source snapshot + `build.sh`, but it is incomplete (`conftest.c`
    missing → make fails), so the gold for tinycc is now built from the **upstream source at the task
    commit** (`git clone tinycc/tinycc @ 9b8765d`, configure/make/make install — no network needed,
    3 s). `make_gold_run.py --source-overrides /scratch/jundahe/pb-runs/gold-src` packages such
    overrides; tinycc is the only one so far. Its executable hash therefore differs from the
    reference binary's.
  - Survey: every branch tar contains `build.sh`; 33 C / 12 C++ tasks, many of whose build.sh run
    `apt-get`, so source-built golds are not generally possible under the build-time internet block.
- **v1 pass complete** (01:13): 200/200, no instance-level errors, 9 branch errors (all the pytest-9.1
  × libtmux collection failure). Scored into `results/v1-hostnet/` (host-network shim, binary-copy
  gold incl. tinycc): 9 excluded (< 0.9) → 191 remain. Excluded: tinycc 0.718, pingu 0.723,
  oranda 0.745, ffmpeg 0.798, revive 0.809, dutree 0.843, dust 0.868, muffet 0.890, doxygen 0.899.
  Of these, tinycc/pingu/muffet (and part of dust/dutree) are attributable to our environment, not
  the tests — hence the v2 pass.
- Shim swapped: `scripts/pbdocker` is now the isolated-netns + proxy version (old one kept as
  `scripts/pbdocker.v1-hostnet`). Jobs **5532** (12 c, 2 workers) and **5533** (4 c, 1 worker) started
  the v2 pass into `/scratch/jundahe/pb-runs/gold-eval-v2/` (tinycc gold = source build).
  Removed 5 orphaned container dirs left by the v1 jobs.
- Hourly check #7 (02:15): v2 pass 51/200 after 1 h (3 workers), no instance/branch errors beyond the
  known pytest-9.1 collection failure, no task scores lower than in v1 (environment regression
  check). Raw criterion: 3 excluded so far (oranda, dust, doxygen).
- Decision recorded earlier tonight: exclusion uses the **raw** hidden-suite pass rate (v1 under that
  criterion would have been 22 excluded / 178 remain — closer to the model card's 34/166 than the
  9/191 the post-ignore-list criterion gives). v1 is archived only; v2 is the single authoritative run.
- **v2 pass complete** (07:03, ~6 h with 3 workers): 200/200, no instance-level errors, 10 pytest-9.1
  branch collection failures, no `/tmp` symptoms. Raw criterion: **23 excluded / 177 remain**
  (`results/v2/`, committed as a snapshot). Fixes confirmed: tinycc 0.998 (was 0.718), pandoc 0.983,
  muffet 0.964 (was 0.890), pixterm 0.998, dropbear 0.947.
- Audit of v2's own artefacts (isolated netns has no raw outbound network):
  - **dog** 0.728 (DNS client: 668 "Network is unreachable"), **gping** (19), **oha** 0.455 (its big
    branch hung for the full 3600 s run_tests timeout — load tests against unreachable hosts — so
    601 tests are `not_run`), plus a handful of internet-touching tests in bat, bore, ffmpeg, xh,
    dropbear, curlie, gomplate, quinn. These need real outbound network, which only the host-network
    mode gives here. Job **5534** re-runs these 11 tasks with `PBDOCKER_HOST_NETWORK=1` into
    `gold-eval-v2-hostnet/` (1 worker to avoid our own port collisions). Final per-task result =
    the network mode with the higher raw pass rate, recorded as `network_mode` in `gold_scores.json`.
  - **pingu** 0.729: Go ICMP via unprivileged datagram sockets needs `net.ipv4.ping_group_range`,
    which is netns-local and can be opened inside our own netns (`0 65535`); verified pingu pings
    localhost. Shim now sets it at container start (isolated mode); pingu re-run under v2 (job below).
- Jobs 5534 (host-network re-run, 2 h 35 m) and 5535 (pingu, 4 min) done. Recovered: dog 0.909,
  gping 0.952, oha 0.956, pingu 0.969, bat 0.952, curlie 1.000, xh 0.993, bore 0.987. Merged with
  `score_gold.py <v2>,<v2-hostnet>` (best raw rate per task, 8 tasks taken from the host-network run).
- **FINAL benchmark definition: 20 excluded / 180 remain** → `results/v2/` (README marks it final).
- Flakiness question (user, 2026-09-04 ~11:00): could a re-run push kept tasks below 0.9? Analysis of
  the two full runs so far: the 28 kept tasks in [0.90, 0.95) have *identical* raw rates across runs
  to 3 decimals in almost every case (cppcheck 0.904/0.904, zk 0.908/0.908, kiro 0.912/0.911, …) —
  their gold failures are deterministic bad tests, not randomness. Genuinely flipping tests are few
  (gron 17, errcheck 16, peco 15, gdu 13, felix 11, serpl 10 …); 53/180 kept tasks have ≥1 flip.
  Timing/load-sensitive failures cluster in dog (151), xplr (22), the_silver_searcher (15), gping (13).
  At-risk kept tasks: serpl 0.908 (10 flips), dog 0.909 (timing), cppcheck 0.904, zk 0.908.
  Started **v3** (jobs 5537/5538): an exact repeat of the v2 configuration into `gold-eval-v3`, to
  measure run-to-run variance directly. Proposed robust rule (pending user's OK): exclude a task if
  its raw rate is < 0.9 in *any* run; mask = tests passing in *all* runs.
- dsh (DeepSeek Harness) integration, 2026-09-04 afternoon — see `docs/05-dsh-agent.md`. Runtime =
  Python SDK wheel with bundled Node, bind-mounted into the task container; agent runs as `agent`
  inside an isolated netns whose only reachable host is the LLM API (OpenRouter) via a transparent
  TLS relay; profile patch disables web tools/telemetry and pins danger-full-access. Two boot fixes
  (permission preset must be stated explicitly; a reused dsh-home resumes the old session). Smoke
  test on cmatrix with deepseek-v4-flash via OpenRouter (job 5547, 45 min hard cap): the parent
  launched one `workflow` run (`explore-cmatrix`, 5 parallel child agents) at 1.6 min; three
  children finished by 10 min, the last two (tmux / escape-sequence exploration) kept working —
  writing implementation files — until the cap, with the parent blocked inside the workflow tool.
  227 tool calls in total, no compile.sh yet at 45 min. Per-task records: params.json, prompt.txt,
  notifications.jsonl, all session logs, extracted workflow scripts (`workflows/`), summary.json.
  Defaults set to 6 h wall-time per task + 6.5 h kill switch.
- **dsh pilot started** (2026-09-04 19:40): 10 tasks (`configs/pilot10.json`: cmatrix, zoxide, scc, figlet,
  entr, gron, hyperfine, fzf, tex-fmt, tokei), `deepseek/deepseek-v4-pro` via OpenRouter, 6 h/task,
  two groups — `required` (prompt demands the workflow tool; job 5548) and `allowed` (control; job
  5549). The `long` QoS allows one job per user, so 5549 (2 workers) runs first and 5548 queues;
  to be consolidated into one job with 4 workers once the v3 gold pass (job 5537) releases its cores.
- v3 repeat pass done (job 5537 ended OUT_OF_MEMORY at 9 h but after the last task; 5538 cancelled
  earlier to free CPU quota). 200/200 evaluated → `results/v3-repeat/` (diagnostic). Findings: 178
  tasks identical to v2 to 3 decimals; total flipped tests outside sqlite/skeema ≈ 20. sqlite and
  skeema collapsed because one big branch each hit the 3600 s `run_tests` timeout under node load
  (the dsh pilot was running) — an infrastructure effect that also threatens submission evals:
  **run evals with low parallelism on an idle node**. dog/oha/gping lower only because v3 lacked
  the host-network re-runs. Official definition remains `results/v2/` (20/180); the robust
  min-over-runs rule (`scripts/score_gold_robust.py`) is ready but waits for the v3 host-network +
  sqlite/skeema re-runs once the pilot releases the CPU quota.
- 2026-09-05 00:40 **pilot paused: OpenRouter credits exhausted** ($3 of $3000 left; this key alone
  used $1366, $54 today). scc (required) ended `finished:error` after 16 × HTTP 402 retries; jobs
  5549/5550 cancelled to stop episodes idling on retries. Completed episodes kept: allowed =
  cmatrix, zoxide, scc, figlet, entr, gron (6); required = cmatrix, zoxide (2) + scc (error, to redo).
  Observations so far: required/cmatrix ran 2 workflows successfully; required/zoxide's workflow
  script failed to parse (garbled JS with dropped characters — possibly a low-quality OpenRouter
  provider route) and the model fell back to `subagent`; allowed/scc used `subagent` on its own.
  While waiting for credits, the freed CPU quota goes to gold work: v3 host-network re-run of the
  11 network tasks, sqlite/skeema v3 re-run on an idle node, and `programbench eval` of the 8
  finished pilot submissions (jobs queued via `gold_eval.slurm`, now generic: RUN_DIR/OUT).
