#!/usr/bin/env python3
"""Build a "gold" run directory: one submission per task whose compile.sh just installs the
task's reference binary (exposed by pbdocker via PBDOCKER_EXPOSE_REFERENCE=1) as ./executable.

    scripts/make_gold_run.py <run_dir> [--tasks-dir <ProgramBench tasks dir>]
"""

import argparse
import io
import tarfile
from pathlib import Path

COMPILE_SH = b"#!/bin/sh\nset -e\ncp /opt/programbench-reference/executable ./executable\nchmod +x ./executable\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--tasks-dir", type=Path, default=Path("/scratch/jundahe/ProgramBench/src/programbench/data/tasks"))
    args = ap.parse_args()
    tasks = sorted(d.name for d in args.tasks_dir.iterdir() if (d / "task.yaml").exists() and not d.name.startswith("testorg__"))
    for iid in tasks:
        out = args.run_dir / iid / "submission.tar.gz"
        out.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(out, "w:gz") as tar:
            info = tarfile.TarInfo("compile.sh")
            info.size, info.mode = len(COMPILE_SH), 0o755
            tar.addfile(info, io.BytesIO(COMPILE_SH))
    print(f"wrote {len(tasks)} gold submissions under {args.run_dir}")


if __name__ == "__main__":
    main()
