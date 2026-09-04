#!/usr/bin/env python3
"""Host-side runner: DeepSeek Harness (dsh) on ProgramBench tasks, producing a `programbench eval`-compatible
run directory (<out>/<iid>/submission.tar.gz) plus dsh session logs as trajectories.

    scripts/dsh_programbench.py <out_dir> --key-file ~/.deepseek_key [--model deepseek-v4-flash]
        [--filter REGEX] [--tasks-file results/v2/...] [--workers N] [--wall-time-seconds 0]

Per task: start a container through the pbdocker shim (isolated netns; the only reachable host is
api.deepseek.com through a transparent relay; the dsh runtime and this repo's driver are bind-mounted
read-only; the reference binary is NOT exposed anywhere but ./executable), run scripts/dsh_agent.py as
user `agent`, then tar /workspace into submission.tar.gz and stop the container.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
SHIM = HERE / "pbdocker"
TASKS = Path("/scratch/jundahe/ProgramBench/src/programbench/data/tasks")
RUNTIME = Path("/scratch/jundahe/dsh-runtime")


def sh(*cmd: str, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=True, capture_output=True, **kw)


def run_task(iid: str, out: Path, args: argparse.Namespace) -> str:
    tdir = out / iid
    home = tdir / "dsh-home"
    keydir = tdir / "key"
    for d in (home, keydir):
        d.mkdir(parents=True, exist_ok=True)
        d.chmod(0o777)  # written by uid 1000 (`agent`) inside the container
    (keydir / "key").write_bytes(args.key_file.read_bytes())
    (keydir / "key").chmod(0o644)
    api_host = urlsplit(args.base_url).hostname if args.base_url else "api.deepseek.com"
    env = {
        **os.environ,
        "PBDOCKER_EXTRA_BINDS": f"{RUNTIME}:/opt/dsh:ro,{HERE}:/opt/pb/scripts:ro,{HERE.parent / 'configs'}:/opt/pb:ro,{home}:/dsh-home,{keydir}:/run/pbagent:ro",
        "PBDOCKER_TCP_RELAYS": f"{api_host}:443",
        "PBPROXY_ALLOW": api_host,
    }
    env.pop("PBDOCKER_EXPOSE_REFERENCE", None)
    image = f"programbench/{iid.replace('__', '_1776_')}:task_cleanroom_v6"
    patch = HERE.parent / "configs" / "dsh-programbench.patch.yml"
    (tdir / "params.json").write_text(json.dumps({
        "instance_id": iid, "image": image, "model": args.model, "base_url": args.base_url or "https://api.deepseek.com",
        "provider": "deepseek-official", "workflow": args.workflow, "wall_time_seconds": args.wall_time_seconds,
        "hard_timeout_seconds": args.hard_timeout_seconds, "max_tokens": 49152, "profile": "sdk",
        "patch_file": str(patch), "patch_sha256": hashlib.sha256(patch.read_bytes()).hexdigest(),
        "dsh_runtime": json.loads((RUNTIME / "deepseek_harness_runtime" / "deepseek-harness-runtime.json").read_text()),
        "dsh_sdk_version": next((d.name for d in RUNTIME.iterdir() if d.name.startswith("deepseek_harness_sdk-")), "?"),
        "experiments_git_commit": sh("git", "-C", str(HERE), "rev-parse", "HEAD").stdout.strip(),
        "shim": str(SHIM), "network": {"mode": "isolated netns + unix-socket proxy", "allowed_hosts": [api_host]},
        "container_user": "agent", "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }, indent=1))
    name = f"programbench-dsh-{iid[:20].replace('.', '-')}-{int(time.time()) % 100000}"
    r = sh(str(SHIM), "run", "-d", "--name", name, "-w", "/workspace", "--user", "agent", image, "sleep", "168h", env=env)
    if r.returncode:
        return f"{iid}: container start failed: {r.stderr.strip()[-300:]}"
    try:
        sh(str(SHIM), "exec", name, "bash", "-lc",
           'git config user.name "dsh" && git config user.email "dsh@local"', env=env)
        cmd = (
            f"PYTHONPATH=/opt/dsh python3 /opt/pb/scripts/dsh_agent.py --dsh-home /dsh-home --key-file /run/pbagent/key "
            f"--model {args.model} --wall-time-seconds {args.wall_time_seconds} --instance-id {iid} --patch /opt/pb/dsh-programbench.patch.yml "
            f"--workflow {args.workflow}" + (f" --base-url {args.base_url}" if args.base_url else "")
        )
        t0 = time.time()
        r = sh(str(SHIM), "exec", name, "bash", "-lc", cmd, env=env, timeout=args.hard_timeout_seconds or None)
        (tdir / "agent.log").write_text(r.stdout + r.stderr)
        sh(str(SHIM), "exec", name, "bash", "-lc", "tar -czf /tmp/_submission.tar.gz -C /workspace .", env=env)
        sh(str(SHIM), "cp", f"{name}:/tmp/_submission.tar.gz", str(tdir / "submission.tar.gz"), env=env)
        status = "?"
        if (home / "result.json").exists():
            status = json.loads((home / "result.json").read_text())["exit_status"]
        sh(sys.executable, str(HERE / "dsh_extract.py"), str(tdir))  # workflows/ + prompt record from the session log
        return f"{iid}: {status} in {(time.time() - t0) / 60:.0f} min"
    except subprocess.TimeoutExpired:
        sh(str(SHIM), "exec", name, "bash", "-lc", "tar -czf /tmp/_submission.tar.gz -C /workspace .", env=env)
        sh(str(SHIM), "cp", f"{name}:/tmp/_submission.tar.gz", str(tdir / "submission.tar.gz"), env=env)
        return f"{iid}: hard timeout after {args.hard_timeout_seconds}s (workspace saved)"
    finally:
        (keydir / "key").unlink(missing_ok=True)
        sh(str(SHIM), "rm", "-f", name, env=env)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--key-file", type=Path, required=True)
    ap.add_argument("--model", default="deepseek-v4-flash")
    ap.add_argument("--base-url", default="", help="e.g. https://openrouter.ai/api/v1 (then --model in OpenRouter form)")
    ap.add_argument("--workflow", choices=["required", "allowed"], default="required")
    ap.add_argument("--filter", default="")
    ap.add_argument("--tasks-file", type=Path, help="JSON list of instance ids (default: all non-excluded tasks in results/v2)")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--wall-time-seconds", type=int, default=0, help="agent wall-time limit; 0 = none (model card)")
    ap.add_argument("--hard-timeout-seconds", type=int, default=0, help="kill switch for the whole episode; 0 = none")
    ap.add_argument("--redo", action="store_true")
    args = ap.parse_args()
    if args.tasks_file:
        tasks = json.loads(args.tasks_file.read_text())
    else:
        ex = set(json.loads((HERE.parent / "results" / "v2" / "excluded_tasks.json").read_text())["excluded"])
        tasks = [d.name for d in sorted(TASKS.iterdir()) if (d / "task.yaml").exists() and not d.name.startswith("testorg__") and d.name not in ex]
    if args.filter:
        tasks = [t for t in tasks if re.match(args.filter, t)]
    if not args.redo:
        tasks = [t for t in tasks if not (args.out_dir / t / "submission.tar.gz").exists()]
    print(f"{len(tasks)} tasks, {args.workers} workers, model {args.model}", flush=True)
    with ThreadPoolExecutor(args.workers) as pool:
        for line in pool.map(lambda t: run_task(t, args.out_dir, args), tasks):
            print(line, flush=True)


if __name__ == "__main__":
    main()
