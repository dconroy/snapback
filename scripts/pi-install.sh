#!/usr/bin/env bash
# Runs ON THE PI (called by scripts/deploy.sh): venv, dependencies, user service, restart.
set -euo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

if [[ ! -x .venv/bin/python ]]; then
  echo "Creating virtualenv"
  python3 -m venv .venv
fi
.venv/bin/pip install --quiet --disable-pip-version-check -r requirements.txt

unit_dir="$HOME/.config/systemd/user"
mkdir -p "$unit_dir" "$HOME/quickcap-runtime"
sed -e "s#%h/quickcap/#$APP_DIR/#g" \
    -e "s#^WorkingDirectory=%h/quickcap\$#WorkingDirectory=$APP_DIR#" \
    deploy/snapback.service > "$unit_dir/snapback.service"
systemctl --user daemon-reload

# The Phase 1 preview server holds /dev/video0 and port 8080.
if pgrep -f quickcap_preview_server.py > /dev/null; then
  echo "Stopping the Phase 1 preview server"
  pkill -INT -f quickcap_preview_server.py || true
  sleep 2
fi

systemctl --user restart snapback.service

for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8080/api/status > /dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

systemctl --user --no-pager --lines=0 status snapback.service || true
echo
curl -fsS http://127.0.0.1:8080/api/status
echo
