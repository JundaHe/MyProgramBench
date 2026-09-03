#!/usr/bin/env python3
"""Restore file ownership in an apptainer sandbox built from a docker:// image.

`apptainer build --sandbox` (rootless, even with --fakeroot) squashes every file to the invoking
user, i.e. everything looks root-owned inside the container. ProgramBench images chown /workspace
and /home/agent to uid 1000 (`agent`), which mini-swe-agent relies on (`--user agent`). This reads
the image's layer tars (from the apptainer blob cache, downloading any that are missing) and
re-applies every non-root uid/gid with `chown` inside a fakeroot toolbox.

    scripts/fix_ownership.py <rootfs> <image ref e.g. programbench/foo_1776_bar.abc:task_cleanroom_v6>
"""

import json
import os
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

CACHE = Path(os.environ.get("APPTAINER_CACHEDIR", "/scratch/jundahe/.apptainer/cache")) / "cache" / "blob" / "blobs" / "sha256"
TOOLBOX = Path(os.environ.get("PBDOCKER_ROOT", "/scratch/jundahe/pb-apptainer")) / "toolbox" / "rootfs"
ACCEPT = ", ".join(
    f"application/vnd.{x}" for x in ("docker.distribution.manifest.v2+json", "oci.image.manifest.v1+json")
)


def registry_get(repo: str, path: str, token: str) -> bytes:
    req = urllib.request.Request(
        f"https://registry-1.docker.io/v2/{repo}/{path}", headers={"Authorization": f"Bearer {token}", "Accept": ACCEPT}
    )
    with urllib.request.urlopen(req) as r:
        return r.read()


def main() -> None:
    rootfs, ref = Path(sys.argv[1]), sys.argv[2]
    repo, tag = ref.rsplit(":", 1)
    token = json.load(
        urllib.request.urlopen(f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:{repo}:pull")
    )["token"]
    manifest = json.loads(registry_get(repo, f"manifests/{tag}", token))
    owners: dict[str, tuple[int, int]] = {}
    for layer in manifest["layers"]:
        digest = layer["digest"].split(":")[1]
        blob = CACHE / digest
        if not blob.exists():
            CACHE.mkdir(parents=True, exist_ok=True)
            blob.write_bytes(registry_get(repo, f"blobs/{layer['digest']}", token))
        with tarfile.open(blob, "r:*") as tar:
            for m in tar:
                name = m.name.lstrip("./")
                if "/.wh." in f"/{name}":
                    continue
                if m.uid or m.gid:
                    owners[name] = (m.uid, m.gid)
                else:
                    owners.pop(name, None)
    script = "\n".join(f"chown -h {u}:{g} '/rootfs/{p}' 2>/dev/null || true" for p, (u, g) in owners.items())
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as f:
        f.write(script)
    subprocess.run(["apptainer", "exec", "--fakeroot", "-B", f"{rootfs}:/rootfs", "-B", f"{f.name}:/fix.sh", str(TOOLBOX), "sh", "/fix.sh"], check=True)
    os.unlink(f.name)
    print(f"{ref}: re-applied ownership of {len(owners)} entries")


if __name__ == "__main__":
    main()
