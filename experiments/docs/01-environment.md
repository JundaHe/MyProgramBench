# Environment: SOAR workstation (`pro5000-soar`)

Source of policy: `/scratch/jundahe/soar-workstation-cheatsheet.md` (summary of the lab docs).
Everything below was probed on 2026-09-03.

## Constraints that shape the setup

| Constraint | Consequence |
|---|---|
| Docker is admin-only (`/var/run/docker.sock` is `root:docker`, user not in group; joining the group is explicitly forbidden) | programbench's eval must run on Apptainer via the `scripts/pbdocker` shim |
| `kernel.apparmor_restrict_unprivileged_userns = 1` (Ubuntu 24.04 default): `unshare -Ur` fails even inside a Slurm job | rootless podman/docker (user-installed static binaries) are **not** an option — only AppArmor-profiled binaries (`/etc/apparmor.d/apptainer`) may create user namespaces |
| Login shell: ~4 cores / 16 GB, `/dev/fuse` blocked (`squashfuse_ll ... Operation not permitted`) | SIF images cannot be mounted in the login shell; **sandbox (directory) images work anywhere**. All real work goes through `sbatch`/`srun` |
| Slurm partitions: `debug` 2 h, `normal` 1 d, `long` 7 d (`-p` and `--qos` must match); 32 cores, 123 GB RAM, single node | Gold eval is split into batches sized for the partition |
| No conda; `uv` installed to `~/.local/bin` (v0.12.9); venv lives in `/scratch/jundahe/ProgramBench/.venv` | `export PATH=$HOME/.local/bin:$PATH` in every job |
| Caches must live in `/scratch` | `HF_HOME=/scratch/jundahe/huggingface`, `APPTAINER_CACHEDIR=/scratch/jundahe/.apptainer/cache` (set by `module load lab/base`; the `tmp` dir had to be created by hand) |

Internet is available (PyPI, GitHub, Docker Hub, HuggingFace all reachable).

## Apptainer capabilities verified (v1.5.2, non-setuid install)

| Capability | Result | Needed for |
|---|---|---|
| `apptainer build --sandbox <dir> docker://...` | OK in login shell (cmatrix image: 3.0 GB, ~1 min) | image pull |
| `--fakeroot` (subuid range `558752:65536` present) | uid 0 inside, can read the `--x--x--x` reference binary | root-like builds/tests |
| `instance start --overlay <dir>` on a sandbox | kernel overlayfs (`userxattr`), upper dir persists across `exec` | container state + `commit` |
| instance PID namespace | PID 1 is `appinit`; `kill -KILL -1` inside is contained | harness's timeout sweep (`container.py`) |
| stdin passthrough to `apptainer exec` | OK | `docker exec -i ... tar -xzf -` |
| `/etc/resolv.conf` | bound read-only from host by default → `--no-mount /etc/resolv.conf` + seed a writable copy; DNS blackhole then works (`curl: Could not resolve host`) | build-time internet block |
| `/tmp` | `--containall` makes it a 64 MiB tmpfs (`sessiondir max size`) → bind a per-container host dir instead | builds writing to /tmp |
| Network | host network namespace, no isolation; parallel containers share ports | keep `-b 1`; watch for port clashes when `-w > 1` |
| `$HOME` | `--containall` masks it with an empty session dir → `--no-home` so the image's `/root` (with `.gitconfig` `safe.directory`) is used | `seed_git` step |
| host env | `apptainer exec` inherits it (a leaked `$TMUX` broke all tmux tests) → `--cleanenv`; `$TERM` is forwarded regardless → `env -u TERM` | docker-exec parity |
| `--cpus` | no equivalent; ignored — Slurm's cgroup (`-c N`) is the cap. `PYTEST_XDIST_AUTO_NUM_WORKERS` is still passed through | |

## Shim: `scripts/pbdocker`

docker-CLI-compatible front end for exactly the calls in `programbench/container.py`
(`run -d`, `exec [-i] [-w]`, `cp` both directions, `commit`, `stop`, `rm -f`, `rmi -f`).
Store layout under `/scratch/jundahe/pb-apptainer/`:

```
toolbox/rootfs                      alpine sandbox; fakeroot `cp -a` / `rm -rf` of subuid-owned files
images/<ref>/rootfs                 base sandbox (scripts/prep_image.sh)
images/<ref>/{upper,commit.json}    committed image = base + snapshot of a container's overlay upper
containers/<name>/{upper,work,tmp}  one apptainer instance each
```

Smoke test (2026-09-03, login shell): full run→exec→cp→commit→run-from-commit→cp-out→rm→rmi cycle
passed on `programbench/abishekvashok_1776_cmatrix.5c082c6:task_cleanroom_v6`.

Observation: the sha256 of `/workspace/executable` in the cleanroom image is
`4889d5b0…2370`, while `task.yaml`'s `eval_clean_hashes` lists `776f1c41…4210`. So
`eval_clean_hashes` is *not* the cleanroom binary's hash (probably the `:task_v6` build). Irrelevant
for the gold run (the copy happens after `_remove_hashed_files`), but worth knowing.
