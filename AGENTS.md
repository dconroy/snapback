# Agent Notes

## The Pi Is The Development Server

The Raspberry Pi (`snapback.local`, SSH details in the gitignored `.env`) is the development server. Any change made to the code here must also be made on the Pi. Keep the two in sync.

- After changing code, deploy it: `scripts/deploy.sh`. It rsyncs the repo to `~/snapback` on the Pi, installs requirements, restarts `snapback.service`, and prints `/api/status`.
- The Pi has no git checkout. Never edit files directly on the Pi; edit here and deploy, or the next deploy will overwrite the edits.
- Check the result after deploying: `scripts/pi-ctl.sh status`, `scripts/pi-ctl.sh logs`, `scripts/pi-ctl.sh ffmpeg-log`.
- Docs-only or `site/` changes don't need a deploy (`site/` is not copied to the Pi; it is published by GitHub Pages).
- Run `.venv/bin/python -m pytest -q` locally before deploying.

## Pi Safety

- Do not run `sudo` on the Pi. Give the user the command to run themselves.
- Do not delete files on the Pi; move old things to `~/bringup-archive/` instead.
- Captured media lives in `~/snapback-runtime/captures` on the Pi. Never delete it, and never commit media to git.
- Never commit or print the contents of `.env`.
