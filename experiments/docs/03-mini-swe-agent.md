# Step 2: mini-swe-agent harness

Model card: "the same mini-swe-agent harness that the upstream repo uses, without the six-hour
time limit."

## What "the harness" is

`mini-swe-agent` ships a ProgramBench runner: `mini-extra programbench` →
`minisweagent/run/benchmarks/programbench.py`, config `minisweagent/config/benchmarks/programbench.yaml`.
Installed here: **mini-swe-agent 2.4.6** in `/scratch/jundahe/venvs/msa` (uv venv, Python 3.12).
It imports `programbench.utils.load_data` / `instance_filters` from the programbench package, so the
same venv also has programbench installed (`uv pip install -e /scratch/jundahe/ProgramBench`, done 2026-09-03;
`mini-extra programbench --help` works).

Key defaults in `programbench.yaml` (2.4.6):

| Setting | Default | Note |
|---|---|---|
| `agent.wall_time_limit_seconds` | **21600** (= 6 h) | this is the "six-hour time limit"; set to `0` to disable |
| `agent.step_limit` | 1000 | unchanged by the model card |
| `agent.cost_limit` | 0 (off) | |
| `environment.timeout` | 180 s per command | |
| `environment.container_timeout` | `7h` (`sleep 7h` keeps the container alive) | must be raised when the 6 h limit is removed, otherwise the container dies mid-run |
| `environment.run_args` | `--rm --network none --cpus 20 --memory 60g --memory-swap 60g --user agent --cap-drop SYS_PTRACE` | agent runs as user `agent`, no network |
| image | `<image_name>:task_cleanroom_v6` | same tag as eval |

The runner writes `<out>/<iid>/submission.tar.gz` (tar of `/workspace` via `docker cp`) +
`<iid>.traj.json`, directly consumable by `programbench eval`.

## Running it here (no Docker)

Two options in mini-swe-agent: `DockerEnvironment` (docker CLI, configurable `executable`) and
`SingularityEnvironment`. The singularity one builds a fresh sandbox per instance in `$TMPDIR`,
has no `--user`/network handling, and `copy_submission` requires `container_id` (docker only) —
so it is unusable as-is. Decision: **DockerEnvironment + `scripts/pbdocker`**
(`environment.executable: /scratch/jundahe/programbench-experiments/scripts/pbdocker`), extending
the shim to accept mini-swe-agent's `run_args` (`--rm`, `--network none`, `--user agent`,
`--memory*`, `--cap-drop`). Resource flags are ignored (Slurm cgroup is the cap).

Overrides (`configs/programbench-no-time-limit.yaml`, merged on top of the builtin default with a second `-c`):

```yaml
agent:
  wall_time_limit_seconds: 0        # model card: "without the six-hour time limit"
environment:
  container_timeout: "168h"         # container must outlive the run
  executable: /scratch/jundahe/programbench-experiments/scripts/pbdocker
```

Invocation (inside a Slurm job, `module load apptainer/1.5.2 lab/base`):

```bash
/scratch/jundahe/venvs/msa/bin/mini-extra programbench \
  -c /scratch/jundahe/venvs/msa/lib/python3.12/site-packages/minisweagent/config/benchmarks/programbench.yaml \
  -c configs/programbench-no-time-limit.yaml -m <model> -o /scratch/jundahe/pb-runs/<run-name> --filter <regex>
```

Open items: which model/API to run (`-m`, no API key configured on this host yet), workers per Slurm
job, and per-instance wall time given the 7-day `long` partition cap (no 6 h limit means a single
instance can in principle run until `step_limit` = 1000 steps).
