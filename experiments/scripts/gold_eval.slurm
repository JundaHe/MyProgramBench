#!/bin/bash
# Evaluate the gold (reference-binary) run for a subset of tasks.
#   sbatch --export=ALL,FILTER='abishekvashok__cmatrix'[,FORCE=1,WORKERS=n] scripts/gold_eval.slurm
# FILTER: regex on instance_id (default all). WORKERS: instances in parallel (default 1); DOCKER_CPUS: xdist
# workers per container (default 8) — request -c WORKERS*DOCKER_CPUS. Use scripts/pending_tasks.py for FILTER.
#SBATCH -p debug
#SBATCH --qos=debug
#SBATCH -J pb-gold
#SBATCH -n 1
#SBATCH -c 8
#SBATCH --mem=32G
#SBATCH -t 02:00:00
#SBATCH -o /scratch/jundahe/programbench-experiments/logs/gold-eval-%j.out
set -euo pipefail
module load lab/base apptainer/1.5.2
export PATH=$HOME/.local/bin:$PATH
export HF_HOME=/scratch/jundahe/huggingface
export PROGRAMBENCH_DOCKER_EXECUTABLE=/scratch/jundahe/programbench-experiments/scripts/pbdocker
export PROGRAMBENCH_DOCKER_RUN_TIMEOUT=1800 PROGRAMBENCH_DOCKER_CP_TIMEOUT=1800
export PBDOCKER_EXPOSE_REFERENCE=1
export PBDOCKER_PROXY_DIR=/scratch/jundahe/pb-apptainer/proxy/$SLURM_JOB_ID
echo "HOST=$(hostname) JOB=$SLURM_JOB_ID CPUS=$SLURM_CPUS_PER_TASK FILTER=${FILTER:-}"
cd /scratch/jundahe/ProgramBench
uv run programbench eval /scratch/jundahe/pb-runs/gold \
  --filter "${FILTER:-}" -o "${OUT:-/scratch/jundahe/pb-runs/gold-eval}" \
  --docker-cpus "${DOCKER_CPUS:-8}" -w "${WORKERS:-1}" -b "${BRANCH_WORKERS:-1}" ${FORCE:+--force}
