# Agent Notes

## The Pi Is The Development Server

The Raspberry Pi (`snapback.local`, SSH details in the gitignored `.env`) is the development server. Any change made to the code here must also be made on the Pi. Keep the two in sync.

- After changing code, deploy it: `scripts/deploy.sh`. It rsyncs the repo to `~/snapback` on the Pi, installs requirements, restarts `snapback.service`, and prints `/api/status`.
- The Pi has no git checkout. Never edit files directly on the Pi; edit here and deploy, or the next deploy will overwrite the edits.
- Check the result after deploying: `scripts/pi-ctl.sh status`, `scripts/pi-ctl.sh logs`, `scripts/pi-ctl.sh ffmpeg-log`.
- `site/` is not copied to the Pi; it is published by GitHub Pages.
- The scripts in `scripts/` are bash. If you source `scripts/pi.sh` for an ad-hoc command, do it inside `bash -c '...'`; from zsh it can't find `.env` and silently falls back to defaults.

## Keep The Marketing Site Current

The marketing page (`site/index.html`, published to www.snapback.video) must describe what the app actually does. When a change adds, removes, or meaningfully changes user-facing functionality, update the site in the same change:

- Feature cards, the "How it works" steps, the hero copy, and the phone mockup should match the real app UI.
- Keep the README feature list and HTTP API section in sync too.
- The README's images in `docs/images/` are screenshots of the site. After changing the site, regenerate them with `python3 scripts/render-readme-images.py` (needs Google Chrome; run outside the sandbox).
- Don't advertise anything that isn't built and deployed yet.
- Images in `site/` must not contain real team, league, or brand logos (see the "Not affiliated" fine print).

## Finish Every Change: Test, Commit, Push, Deploy

The user wants `main` and the Pi to always have the latest code. Whenever you finish a code update, without asking:

1. Run `.venv/bin/python -m pytest -q`; fix failures before going further.
2. Commit with a clear message and push to `main`.
3. Run `scripts/deploy.sh` and check that the service came back up.

Never commit `.env` or captured media. Pushes that touch `site/` publish the marketing site.

## Pi Safety

- `sudo` on the Pi is allowed. Feed the password from `.env` over stdin (`printf '%s\n' "$ssh_password" | pi_ssh "sudo -S -p '' ..."`) so it never appears in a command line or output. Tell the user what you changed.
- Do not delete files on the Pi; move old things to `~/bringup-archive/` instead.
- Captured media lives in `~/snapback-runtime/captures` on the Pi. Never delete it, and never commit media to git.
- Never commit or print the contents of `.env`.
