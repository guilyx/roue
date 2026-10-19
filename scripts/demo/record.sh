#!/bin/bash
# Records the demo video. See README.md in this folder for requirements.
#   scripts/demo/record.sh            full recording + captions -> scripts/demo/out/roue-demo.mp4
#   SNAP=1 STOP_AFTER=menu record.sh  screenshots of each step, to recalibrate coords.json
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)
if [ "$(id -u)" = 0 ]; then
  echo "Run this as a normal user: Files (Nautilus) refuses to run as root." >&2
  exit 1
fi
export DEMO_OUT=$here/out
rm -rf "$DEMO_OUT" && mkdir -p "$DEMO_OUT/home/.local/bin"

# A throwaway home: the demo never touches your files, settings or history.
cat > "$DEMO_OUT/home/.local/bin/roue" <<SHIM
#!/bin/sh
if [ -x "$repo/.venv/bin/roue" ]; then exec "$repo/.venv/bin/roue" "\$@"; fi
PYTHONPATH="$repo/src" exec python3 -m roue "\$@"
SHIM
chmod +x "$DEMO_OUT/home/.local/bin/roue"
"$here/make_samples.sh" "$DEMO_OUT/home/Pictures" "$DEMO_OUT/wallpaper.png"

export HOME=$DEMO_OUT/home XDG_CONFIG_HOME=$DEMO_OUT/home/.config XDG_DATA_HOME=$DEMO_OUT/home/.local/share
export XDG_STATE_HOME=$DEMO_OUT/home/.local/state XDG_CACHE_HOME=$DEMO_OUT/home/.cache
export PATH=$HOME/.local/bin:$PATH PYTHONPATH=$repo/src DISPLAY=:99
Xvfb :99 -screen 0 1280x720x24 -nolisten tcp >/dev/null 2>&1 &
xvfb=$!
trap 'kill $xvfb 2>/dev/null' EXIT
sleep 1
dbus-run-session -- bash "$here/session.sh"

if [ -z "${STOP_AFTER:-}" ]; then
  NODE_PATH=${NODE_PATH:-$(npm root -g 2>/dev/null)} node "$here/render_cards.js" "$DEMO_OUT" "$repo/src/roue/data/icons/io.github.guilyx.Roue.svg"
  python3 "$here/post.py" "$DEMO_OUT"
fi
