#!/usr/bin/env bash
set -euo pipefail

cloud_repository_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$cloud_repository_root"
python3 -c 'import sys; assert sys.version_info >= (3, 12), "Python >=3.12 is required"'
if [[ ! -x .venv/bin/python ]]; then
    python3 -m venv .venv
fi
.venv/bin/python -m pip install --disable-pip-version-check -e '.[dev]'
.venv/bin/python -m pip check
.venv/bin/python -c 'import dynamic_subject_agent, pytest, keyring, sqlite3; print("Python development dependencies ready")'

# Linux development uses offline providers and the loopback HTTP adapter.
# The optional Windows desktop extra and live provider credentials are not needed.
# No dependency lockfile exists; retain the repository's declared version bounds.
