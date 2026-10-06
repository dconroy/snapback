#!/usr/bin/env bash
# Everyday control of Snapback on the Pi, from your Mac.
# Usage: scripts/pi-ctl.sh status|logs [N]|ffmpeg-log|restart|stop|start|ssh
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/pi.sh"

case "${1:-status}" in
  status)
    pi_ssh "systemctl --user --no-pager --lines=0 status snapback.service; echo; curl -fsS http://127.0.0.1:8080/api/status; echo"
    ;;
  logs)
    pi_ssh "journalctl --user-unit snapback.service --no-pager -n ${2:-100}"
    ;;
  ffmpeg-log)
    pi_ssh "tail -n ${2:-50} ~/snapback-runtime/buffer/ffmpeg-buffer.log"
    ;;
  start | stop | restart)
    pi_ssh "systemctl --user $1 snapback.service"
    ;;
  ssh)
    ssh "${SSH_OPTS[@]}" -t "$PI"
    ;;
  *)
    echo "usage: $0 status|logs [N]|ffmpeg-log [N]|restart|stop|start|ssh" >&2
    exit 2
    ;;
esac
