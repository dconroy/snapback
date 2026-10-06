# Pi Startup

QuickCap does not auto-start on boot. Nothing in this repo installs or enables a service.

## Run The App Manually

```sh
cd ~/quickcap
python3 -m venv .venv                         # first time only
.venv/bin/pip install -r requirements.txt     # first time / after pulls that change it
.venv/bin/python -m quickcap serve            # http://quikcap.local:8000/
```

To keep it running after you log out without a service, use `tmux` or:

```sh
nohup .venv/bin/python -m quickcap serve >> ~/quickcap-runtime/quickcap.log 2>&1 &
```

Stop it with Ctrl-C (or `pkill -INT -f 'quickcap serve'`). That stops the buffer ffmpeg too.

## Optional: systemd Service (Not Installed)

A template unit is in `deploy/quickcap.service`. It assumes the repo is at `/home/pi/quickcap`, the venv is at `.venv`, and the user is `pi`. Review it, then install only if you want it:

```sh
sudo cp deploy/quickcap.service /etc/systemd/system/quickcap.service
sudo systemctl daemon-reload
sudo systemctl start quickcap          # run now
journalctl -u quickcap -f              # logs
sudo systemctl enable quickcap         # ONLY if you want it on every boot
```

Remove it again:

```sh
sudo systemctl disable --now quickcap
sudo rm /etc/systemd/system/quickcap.service
sudo systemctl daemon-reload
```

Do not run the service and a manual `quickcap serve` at the same time. The second one cannot get port 8000 or the capture device lock.

## Phase 1 Preview Server

The temporary `@reboot` cron hook that launched the Phase 1 diagnostic preview server has been removed. The preview server and QuickCap cannot run at the same time because both read `/dev/video0`.

The preview startup script is still on the Pi for manual use:

```sh
#!/bin/sh
set -eu

mkdir -p "$HOME/quickcap-runtime"

if pgrep -f '/home/pi/quickcap_preview_server.py' >/dev/null 2>&1; then
  exit 0
fi

exec /usr/bin/python3 /home/pi/quickcap_preview_server.py \
  --host 0.0.0.0 \
  --port 8080 \
  --device /dev/video0 \
  --input-format mjpeg \
  --video-size 1920x1080 \
  --framerate 60 \
  --preview-fps 15 \
  >> "$HOME/quickcap-runtime/preview.log" 2>&1
```

```sh
crontab -l                                         # confirm no boot hook
pgrep -af '/home/pi/quickcap_preview_server.py'    # is it running?
/home/pi/start_quickcap_preview.sh                 # start it
tail -f ~/quickcap-runtime/preview.log             # logs
```
