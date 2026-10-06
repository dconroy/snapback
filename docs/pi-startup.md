# Pi Startup

Snapback runs on the Pi as a systemd **user** service, `snapback.service`, for the `pi` user. It is installed and restarted by `scripts/deploy.sh` from the Mac. It is **not enabled at boot**.

## How It Is Set Up

- Code: `~/quickcap` (copied by rsync; there is no git checkout on the Pi).
- Virtualenv: `~/quickcap/.venv`.
- Unit file: `~/.config/systemd/user/snapback.service`, generated from `deploy/snapback.service`.
- Optional settings: `~/quickcap-runtime/snapback.env` (`QUICKCAP_*=value` lines).
- Media and buffer: `~/quickcap-runtime/captures`, `~/quickcap-runtime/buffer`.
- Logs: `journalctl --user-unit snapback.service`; ffmpeg warnings in `~/quickcap-runtime/buffer/ffmpeg-buffer.log`.
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
cd ~/quickcap && .venv/bin/python -m quickcap serve
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
/home/pi/start_quickcap_preview.sh                 # serves http://quikcap.local:8080/
pgrep -af '/home/pi/quickcap_preview_server.py'    # is it running?
tail -f ~/quickcap-runtime/preview.log
```

`~/quickcap-dev` on the Pi is an older manual copy of the capture engine from Phase 2. It is not used by the service and can be deleted.
