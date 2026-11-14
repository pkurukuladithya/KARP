#!/usr/bin/env bash
# Launch complete KARP demonstration in simulation mode on Linux
set -e
cd "$(dirname "$0")/.."
echo "[INFO] Starting KARP Simulation Environment..."
exec python3 scripts/run_simulation.py "$@"
