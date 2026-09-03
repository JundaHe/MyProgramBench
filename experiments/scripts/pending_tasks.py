#!/usr/bin/env python3
"""Print a --filter regex for tasks whose image is prepared but which have no gold eval.json yet,
excluding tasks another running `pb-gold-all` job is already evaluating (parsed from that job's last
"=== ... round: <regex>" log line), so several loop jobs can share the work.

    scripts/pending_tasks.py [--limit N]
"""
import os
import re
import subprocess
import sys
from pathlib import Path

IMAGES = Path("/scratch/jundahe/pb-apptainer/images")
EVAL = Path(os.environ.get("PB_GOLD_EVAL_DIR", "/scratch/jundahe/pb-runs/gold-eval/gold"))
TASKS = Path("/scratch/jundahe/ProgramBench/src/programbench/data/tasks")
LOGS = Path("/scratch/jundahe/ProgramBench/experiments/logs")


def claimed_elsewhere() -> set[str]:
    jobs = subprocess.run(["squeue", "-h", "-u", os.environ["USER"], "-n", "pb-gold-all", "-o", "%i"], capture_output=True, text=True).stdout.split()
    claimed: set[str] = set()
    for job in jobs:
        if job == os.environ.get("SLURM_JOB_ID"):
            continue
        rounds = re.findall(r"round: \^\((.*)\)\$", (LOGS / f"gold-eval-all-{job}.out").read_text()) if (LOGS / f"gold-eval-all-{job}.out").exists() else []
        if rounds:
            claimed |= {x.replace("\\", "") for x in rounds[-1].split("|")}
        if (LOGS / f"claims-{job}.txt").exists():  # manual claim list (job 5510's round line was truncated in its log)
            claimed |= set((LOGS / f"claims-{job}.txt").read_text().split())
    return claimed

limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 10**9
pending = [
    d.name for d in sorted(TASKS.iterdir())
    if not d.name.startswith("testorg__")
    and (IMAGES / f"programbench__{d.name.replace('__', '_1776_')}--task_cleanroom_v6" / "rootfs").is_dir()
    and not (EVAL / d.name / f"{d.name}.eval.json").exists()
    and d.name not in claimed_elsewhere()
][:limit]
print(f"# {len(pending)} pending", file=sys.stderr)
print("^(" + "|".join(re.escape(p) for p in pending) + ")$" if pending else "^$")
