#!/bin/bash
# Pull every task image (task_cleanroom_v6) into the pbdocker sandbox store, sequentially.
#   sbatch scripts/prep_all_images.slurm
#SBATCH -p normal
#SBATCH --qos=normal
#SBATCH -J pb-prep-images
#SBATCH -n 1
#SBATCH -c 4
#SBATCH --mem=16G
#SBATCH -t 1-00:00:00
#SBATCH -o /scratch/jundahe/programbench-experiments/logs/prep-images-%j.out
set -uo pipefail
module load lab/base apptainer/1.5.2
cd /scratch/jundahe/programbench-experiments
for d in /scratch/jundahe/ProgramBench/src/programbench/data/tasks/*/; do
  iid=$(basename "$d"); [[ $iid == testorg__* ]] && continue
  echo "=== $(date '+%F %T') $iid"
  scripts/prep_image.sh "$iid" || echo "FAILED: $iid"
done
echo "=== done $(date '+%F %T')"; du -sh /scratch/jundahe/pb-apptainer/images
