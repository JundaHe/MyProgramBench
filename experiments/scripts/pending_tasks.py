#!/usr/bin/env python3
"""Print a --filter regex for tasks whose image is prepared but which have no gold eval.json yet.

    scripts/pending_tasks.py [--limit N]
"""
import re
import sys
from pathlib import Path

IMAGES = Path("/scratch/jundahe/pb-apptainer/images")
EVAL = Path("/scratch/jundahe/pb-runs/gold-eval/gold")
TASKS = Path("/scratch/jundahe/ProgramBench/src/programbench/data/tasks")

limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 10**9
pending = [
    d.name for d in sorted(TASKS.iterdir())
    if not d.name.startswith("testorg__")
    and (IMAGES / f"programbench__{d.name.replace('__', '_1776_')}--task_cleanroom_v6" / "rootfs").is_dir()
    and not (EVAL / d.name / f"{d.name}.eval.json").exists()
][:limit]
print(f"# {len(pending)} pending", file=sys.stderr)
print("^(" + "|".join(re.escape(p) for p in pending) + ")$" if pending else "^$")
