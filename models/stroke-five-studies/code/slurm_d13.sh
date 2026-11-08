#!/bin/bash
# D13 三场景建模 Slurm 作业脚本
# 用法: sbatch -J d13_full  slurm_d13.sh full
#       sbatch -J d13_dedup slurm_d13.sh dedup
#SBATCH --partition=CPU
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=32
#SBATCH --mem=32G
#SBATCH --time=03:00:00
#SBATCH --output=slurm_%x_%j.out
#SBATCH --error=slurm_%x_%j.err

set -euo pipefail
TAG=${1:?用法: slurm_d13.sh full|dedup}
ROOT=$HOME/D13_20261107

echo "=== D13 job start $(date -Is) tag=$TAG host=$(hostname) ==="
source "$ROOT/venv/bin/activate"
cd "$ROOT"
python model_d13_server.py \
  --data "$ROOT/data.csv" \
  --out "$ROOT/results/$TAG" \
  --tag "$TAG" \
  --bootstrap 250 \
  --n-jobs 32
echo "=== D13 job done $(date -Is) exit=$? ==="
