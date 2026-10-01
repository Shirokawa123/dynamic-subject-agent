#!/usr/bin/env bash
set -euo pipefail

cloud_repository_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$cloud_repository_root"
if [[ $# -gt 1 ]]; then
    printf 'Usage: bash scripts/cloud/check_lab.sh [http://127.0.0.1:PORT]\n' >&2
    exit 2
fi
if [[ $# -eq 1 ]]; then
    cloud_lab_base="$1"
else
    cloud_lab_port=$(.venv/bin/python -c 'import re; from pathlib import Path; print(re.search(r"127\.0\.0\.1:(\d+)", Path(".scratch/cloud-onboarding-lab.log").read_text()).group(1))')
    cloud_lab_base="http://127.0.0.1:$cloud_lab_port"
fi
.venv/bin/python scripts/cloud/smoke_http.py "$cloud_lab_base"
