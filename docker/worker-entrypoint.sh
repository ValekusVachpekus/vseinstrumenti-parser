#!/bin/bash
set -e

# Headed Chromium needs an X server; run a virtual one. -ac disables X access
# control so Chromium connects without xauth. Then exec arq as PID 1 so its logs
# stream to `docker logs`.
export DISPLAY="${DISPLAY:-:99}"
rm -f /tmp/.X99-lock
Xvfb "$DISPLAY" -screen 0 1366x768x24 -nolisten tcp -ac >/tmp/xvfb.log 2>&1 &

# Wait for the X server to accept connections.
for _ in $(seq 1 30); do
  if xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then break; fi
  sleep 0.5
done

exec arq app.worker.tasks.WorkerSettings
