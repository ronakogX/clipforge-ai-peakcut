#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -z "${CODESPACE_NAME:-}" ]]; then
  echo 'This launcher is for a private GitHub Codespace. For local use: python -m studio.server.'
  exit 1
fi
mkdir -p data
if [[ -f data/server.pid ]] && kill -0 "$(cat data/server.pid)" 2>/dev/null; then
  echo 'CLIPFORGE is already running.'
  exit 0
fi
export PEAKCUT_HOST=0.0.0.0 PEAKCUT_PORT=8765 PEAKCUT_ACCOUNTS=0
export PEAKCUT_PUBLIC_URL="https://${CODESPACE_NAME}-8765.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
export PEAKCUT_JOB_WORKERS=1 PEAKCUT_ASR_THREADS=2 PEAKCUT_ASR_COPIES=1 PEAKCUT_RENDER_THREADS=2
export PEAKCUT_RENDER_WORKERS=1
export PEAKCUT_MAX_UPLOAD_MB=2048 PEAKCUT_UPLOAD_PART_MB=10 PEAKCUT_MAX_VIDEO_HOURS=12
export PEAKCUT_UPDATE_CHECK=0 PEAKCUT_FOLLOW_URL=''
export PEAKCUT_REPO_URL=https://github.com/ronakogX/clipforge-ai-peakcut
nohup .venv/bin/python -u -m studio.server > data/server.log 2>&1 &
echo "$!" > data/server.pid
echo "Open port 8765 from the Ports tab: ${PEAKCUT_PUBLIC_URL}/app"
echo 'Keep port visibility Private. No app account is needed; GitHub protects this private workspace.'
echo 'Stop the Codespace when finished to preserve your included quota. Download clips before deleting it.'
