#!/usr/bin/env bash
# Copy this checkout to the Pi, install dependencies, and restart Snapback.
# Usage: scripts/deploy.sh            (settings come from .env, see .env.example)
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/pi.sh"

echo "==> Copying files to $PI:$PI_DIR"
pi_ssh "mkdir -p '$PI_DIR'"
pi_rsync -az --delete \
  --exclude '.git/' \
  --exclude '.venv/' \
  --exclude '.env' \
  --exclude '__pycache__/' \
  --exclude '.pytest_cache/' \
  --exclude '.DS_Store' \
  --exclude '.github/' \
  --exclude 'site/' \
  "$REPO_ROOT/" "$PI:$PI_DIR/"

echo "==> Installing and restarting on the Pi"
pi_ssh "bash '$PI_DIR/scripts/pi-install.sh'"

echo "==> Done: http://$PI_HOST:8080/"
