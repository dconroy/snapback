# Running As A Service

Snapback can run as a systemd **user** service, `snapback.service`, so it keeps running in the background and restarts on crash. No sudo is needed to install it.

## Install

From your clone on the Pi:

```sh
cd ~/snapback
scripts/pi-install.sh
```

This creates `.venv` if needed, installs `requirements.txt`, writes `~/.config/systemd/user/snapback.service` from `deploy/snapback.service`, (re)starts the service, and prints `/api/status`. Run it again after pulling updates.

User services only keep running after you log out if lingering is enabled for your user:

```sh
loginctl show-user "$USER" -p Linger   # should print Linger=yes
sudo loginctl enable-linger "$USER"    # if it doesn't
```

## Where Things Live

- Optional settings: `~/snapback-runtime/snapback.env` (`SNAPBACK_*=value` lines). Restart after editing.
- Media and buffer: `~/snapback-runtime/captures`, `~/snapback-runtime/buffer`.
- Logs: `journalctl --user-unit snapback`; ffmpeg warnings in `~/snapback-runtime/buffer/ffmpeg-buffer.log`.
- Port: 8080.

## Commands

```sh
systemctl --user status snapback
systemctl --user restart snapback
journalctl --user-unit snapback -f
```

Running by hand for debugging (stop the service first, since only one process can hold `/dev/video0`):

```sh
systemctl --user stop snapback
cd ~/snapback && .venv/bin/python -m snapback serve
```

## Start At Boot

The service is not enabled at boot by default. To opt in:

```sh
systemctl --user enable snapback      # undo: systemctl --user disable snapback
```

With lingering on, enabled user services start at boot without anyone logging in.
