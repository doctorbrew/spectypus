#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$project_root"
campaign="${1:-results/slsn_ztf_overnight_20261031}"
if [ "$#" -gt 0 ]; then shift; fi
runtime="$campaign/runtime"
if [ ! -f "$runtime/run_saved_campaign.py" ]; then
  echo "Missing frozen runtime: $runtime. Prepare the campaign before launching." >&2
  exit 2
fi
runtime="$(cd "$runtime" && pwd)"
export PYTHONPATH="$runtime"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONUNBUFFERED=1
runner_python="${SPECTYPUS_PYTHON:-python}"
if [ "$(uname -s)" = Darwin ]; then
  exec /usr/bin/caffeinate -ims "$runner_python" "$runtime/run_saved_campaign.py" "$campaign" "$@"
else
  exec "$runner_python" "$runtime/run_saved_campaign.py" "$campaign" "$@"
fi
