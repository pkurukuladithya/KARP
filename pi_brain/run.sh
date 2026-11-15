#!/usr/bin/env bash
# Start KARP Pi Brain. Any flags are passed to main.py, e.g.:
#   ./run.sh --fullscreen
#   ./run.sh --web 8080
#   ./run.sh --headless --web 8080
cd "$(dirname "$0")"
if [ -f .venv/bin/activate ]; then
  # shellcheck disable=SC1091
  . .venv/bin/activate
fi
# Window on the Pi's own screen even when started from SSH
if [ -z "$DISPLAY" ] && [ -z "$WAYLAND_DISPLAY" ] && [[ " $* " != *" --headless "* ]]; then
  export DISPLAY=:0
fi
exec python3 main.py "$@"
