#!/usr/bin/env bash
# Pull a ProgramBench task image from Docker Hub into the pbdocker sandbox store.
#   scripts/prep_image.sh <instance_id> [tag]      (tag defaults to task_cleanroom_v6)
set -euo pipefail
iid=$1; tag=${2:-task_cleanroom_v6}
ref="programbench/${iid/__/_1776_}:$tag"
root=${PBDOCKER_ROOT:-/scratch/jundahe/pb-apptainer}
dst="$root/images/${ref//\//__}"; dst="${dst//:/--}/rootfs"
if [ -d "$dst" ]; then echo "already prepared: $dst"; exit 0; fi
module load apptainer/1.5.2 lab/base 2>/dev/null || true
mkdir -p "$(dirname "$dst")"
apptainer build --sandbox "$dst.partial" "docker://$ref"
python3 "$(dirname "$0")/fix_ownership.py" "$dst.partial" "$ref"
mv "$dst.partial" "$dst"
echo "prepared: $dst ($(du -sh "$dst" | cut -f1))"
