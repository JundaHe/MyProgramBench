#!/usr/bin/env python3
"""Build a "gold" run directory: one submission per task whose compile.sh just installs the
task's reference binary (exposed by pbdocker via PBDOCKER_EXPOSE_REFERENCE=1) as ./executable.

Exception: tasks with a directory under --source-overrides/<instance_id>/ (upstream source at the task
commit + a compile.sh that builds offline) are packaged from there instead. Used when the reference
binary alone is not runnable because its build also installs support files (tinycc: /usr/local/lib/tcc).

    scripts/make_gold_run.py <run_dir> [--tasks-dir <ProgramBench tasks dir>] [--source-overrides <dir>]
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
    ap.add_argument("--source-overrides", type=Path, default=Path("/scratch/jundahe/pb-runs/gold-src"))
    args = ap.parse_args()
    tasks = sorted(d.name for d in args.tasks_dir.iterdir() if (d / "task.yaml").exists() and not d.name.startswith("testorg__"))
    for iid in tasks:
        out = args.run_dir / iid / "submission.tar.gz"
        out.parent.mkdir(parents=True, exist_ok=True)
        if (src := args.source_overrides / iid / "compile.sh").exists():
            with tarfile.open(out, "w:gz") as tar:
                tar.add(src.parent, arcname=".", filter=lambda ti: None if "/.git" in f"/{ti.name}" else ti)
            print(f"{iid}: packaged from source override {src.parent}")
            continue
        with tarfile.open(out, "w:gz") as tar:
            info = tarfile.TarInfo("compile.sh")
            info.size, info.mode = len(COMPILE_SH), 0o755
            tar.addfile(info, io.BytesIO(COMPILE_SH))
    print(f"wrote {len(tasks)} gold submissions under {args.run_dir}")


if __name__ == "__main__":
    main()
