# Pi Startup

Snapback runs on the Pi as a systemd **user** service, `snapback.service`, for the `pi` user. It is installed and restarted by `scripts/deploy.sh` from the Mac. It is **not enabled at boot**.

## How It Is Set Up

- Code: `~/snapback` (copied by rsync; there is no git checkout on the Pi).
- Virtualenv: `~/snapback/.venv`.
- Unit file: `~/.config/systemd/user/snapback.service`, generated from `deploy/snapback.service`.
- Optional settings: `~/snapback-runtime/snapback.env` (`SNAPBACK_*=value` lines).
- Media and buffer: `~/snapback-runtime/captures`, `~/snapback-runtime/buffer`.
- Logs: `journalctl --user-unit snapback.service`; ffmpeg warnings in `~/snapback-runtime/buffer/ffmpeg-buffer.log`.
- Port: 8080, the same port the Phase 1 preview server used. They can't run together anyway, since both need `/dev/video0`.

User services keep running after you log out because lingering is enabled for `pi` (`loginctl show-user pi -p Linger` → `yes`). It was already on when Snapback was first deployed. If a reimage turns it off, run `sudo loginctl enable-linger pi`.

## Commands

From the Mac, using `.env` for SSH details:

```sh
scripts/deploy.sh
scripts/pi-ctl.sh status | logs [N] | ffmpeg-log [N] | start | stop | restart | ssh
```

On the Pi directly:

```sh
systemctl --user status snapback
systemctl --user restart snapback
journalctl --user-unit snapback -f
```

Running by hand for debugging (stop the service first):

```sh
systemctl --user stop snapback
cd ~/snapback && .venv/bin/python -m snapback serve
```

## Opt In: Start At Boot

Only do this if you want Snapback running after every reboot:

```sh
systemctl --user enable snapback      # undo: systemctl --user disable snapback
```

With lingering on, enabled user services start at boot without anyone logging in.

## Phase 1 Preview Server

The temporary `@reboot` cron hook that launched the Phase 1 diagnostic preview server has been removed. `scripts/pi-install.sh` stops the preview server on each deploy. To use the preview again, stop Snapback first:

```sh
systemctl --user stop snapback
python3 ~/snapback/tools/preview_server.py --port 8080   # http://snapback.local:8080/, Ctrl-C to stop
```

Older bring-up files (the Phase 2 engine copy and the original preview script) were moved to `~/bringup-archive/` on the Pi. Nothing uses them, and they can be deleted.
