#!/bin/bash
# Gold-evaluate every task whose image is prepared, in rounds, until the image-prep job (PREP_JOB) is
# gone and nothing is pending. Instances that already have an eval.json are skipped by programbench.
#   sbatch --export=ALL,PREP_JOB=5502 scripts/gold_eval_loop.slurm
#SBATCH -p normal
#SBATCH --qos=normal
#SBATCH -J pb-gold-all
#SBATCH -n 1
#SBATCH -c 24
#SBATCH --mem=52G   # QoS cap: 72G per user in total; the image-prep job holds 16G
#SBATCH -t 1-00:00:00
#SBATCH -o /scratch/jundahe/ProgramBench/experiments/logs/gold-eval-all-%j.out
set -uo pipefail
module load lab/base apptainer/1.5.2
export PATH=$HOME/.local/bin:$PATH
export HF_HOME=/scratch/jundahe/huggingface
export PROGRAMBENCH_DOCKER_EXECUTABLE=/scratch/jundahe/ProgramBench/experiments/scripts/pbdocker
export PROGRAMBENCH_DOCKER_RUN_TIMEOUT=1800 PROGRAMBENCH_DOCKER_CP_TIMEOUT=1800
export PBDOCKER_EXPOSE_REFERENCE=1
S=/scratch/jundahe/ProgramBench/experiments/scripts
echo "HOST=$(hostname) JOB=$SLURM_JOB_ID CPUS=$SLURM_CPUS_PER_TASK WORKERS=${WORKERS:-3} DOCKER_CPUS=${DOCKER_CPUS:-8}"
cd /scratch/jundahe/ProgramBench
while true; do
  filter=$("$S/pending_tasks.py")
  if [ "$filter" = "^$" ]; then
    if [ -n "${PREP_JOB:-}" ] && squeue -j "$PREP_JOB" -h -o %T | grep -q .; then echo "$(date '+%F %T') nothing pending, prep job still running"; sleep 120; continue; fi
    echo "$(date '+%F %T') done"; break
  fi
  echo "=== $(date '+%F %T') round: $filter" | cut -c1-300
  uv run programbench eval /scratch/jundahe/pb-runs/gold --filter "$filter" -o /scratch/jundahe/pb-runs/gold-eval \
    --docker-cpus "${DOCKER_CPUS:-8}" -w "${WORKERS:-3}" -b 1
done
