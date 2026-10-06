#!/usr/bin/env bash
# Shared helpers: load .env and run ssh/rsync against the Pi.
# Source this file; don't run it directly.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "$REPO_ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  . "$REPO_ROOT/.env"
  set +a
fi

PI_USER="${ssh_user:-pi}"
PI_HOST="${ssh_host:-snapback.local}"
PI_PORT="${ssh_port:-22}"
PI_DIR="${remote_dir:-/home/$PI_USER/snapback}"
PI="$PI_USER@$PI_HOST"

SSH_OPTS=(-p "$PI_PORT" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10)

if [[ -n "${ssh_password:-}" ]]; then
  # Feed the password to ssh without sshpass. SSH keys, if set up, are still tried first.
  export SNAPBACK_SSH_PASSWORD="$ssh_password"
  export SSH_ASKPASS="$REPO_ROOT/scripts/askpass.sh"
  export SSH_ASKPASS_REQUIRE=force
  export DISPLAY="${DISPLAY:-:0}"
fi

pi_ssh() {
  ssh "${SSH_OPTS[@]}" "$PI" "$@"
}

pi_rsync() {
  rsync -e "ssh ${SSH_OPTS[*]}" "$@"
}
