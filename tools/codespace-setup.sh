#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
mkdir -p data
echo 'Setup finished. The speech model downloads on first start; this may take several minutes.'
