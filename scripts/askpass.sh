#!/bin/sh
# Used as SSH_ASKPASS by scripts/pi.sh so ssh/rsync can log in with the password from .env.
printf '%s\n' "$SNAPBACK_SSH_PASSWORD"
