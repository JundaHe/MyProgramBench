#!/bin/bash
# Run DeepSeek Harness (dsh) agent episodes on ProgramBench tasks.
#   sbatch --export=ALL,FILTER='abishekvashok__cmatrix',MODEL=deepseek/deepseek-v4-flash,BASE_URL=https://openrouter.ai/api/v1,OUT=/scratch/jundahe/pb-runs/dsh-smoke,HARD_TIMEOUT=2700 scripts/dsh_run.slurm
#SBATCH -p long
#SBATCH --qos=long
#SBATCH -J pb-dsh
#SBATCH -n 1
#SBATCH -c 8
#SBATCH --mem=32G
#SBATCH -t 7-00:00:00
#SBATCH -o /scratch/jundahe/ProgramBench/experiments/logs/dsh-%j.out
set -uo pipefail
module load lab/base apptainer/1.5.2
export PATH=$HOME/.local/bin:$PATH
export PBDOCKER_PROXY_DIR=/scratch/jundahe/pb-apptainer/proxy/$SLURM_JOB_ID
S=/scratch/jundahe/ProgramBench/experiments/scripts
echo "HOST=$(hostname) JOB=$SLURM_JOB_ID MODEL=${MODEL:-} BASE_URL=${BASE_URL:-} OUT=${OUT:-} FILTER=${FILTER:-} WORKERS=${WORKERS:-1}"
python3 "$S/dsh_programbench.py" "${OUT:?}" --key-file "${KEY_FILE:-$HOME/.openrouter_key}" --model "${MODEL:-deepseek/deepseek-v4-flash}" \
  ${BASE_URL:+--base-url "$BASE_URL"} ${FILTER:+--filter "$FILTER"} ${TASKS_FILE:+--tasks-file "$TASKS_FILE"} --workers "${WORKERS:-1}" \
  --workflow "${WORKFLOW:-required}" --wall-time-seconds "${WALL_TIME:-21600}" --hard-timeout-seconds "${HARD_TIMEOUT:-23400}" ${REDO:+--redo}
echo "done $(date '+%F %T')"
