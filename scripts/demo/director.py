"""Drives the demo desktop with real (XTest) mouse and keyboard input and records it.

Run by session.sh. Writes $DEMO_OUT/raw.mkv and $DEMO_OUT/events.json (scene
marks, in seconds from the start of the recording). SNAP=1 also saves a
screenshot at every mark, and STOP_AFTER=<mark> ends early: use both to
recalibrate coords.json after a UI change.
"""

import json
import math
import os
import subprocess
import time
from pathlib import Path

from Xlib import XK, X, display
from Xlib.ext import xtest

HERE = Path(__file__).resolve().parent
OUT = Path(os.environ["DEMO_OUT"])
PICS = Path.home() / "Pictures"
C = json.loads((HERE / "coords.json").read_text())
SNAP = os.environ.get("SNAP") == "1"
STOP_AFTER = os.environ.get("STOP_AFTER", "")

d = display.Display()
events: list[dict] = []
t0 = 0.0


def mark(name: str) -> None:
    """Record a scene boundary (captions are timed from these)."""
    events.append({"t": round(time.monotonic() - t0, 2), "event": name})
    if SNAP:
        snap(name)
    if name == STOP_AFTER:
        raise SystemExit


def snap(name: str) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "x11grab",
            "-video_size",
            "1280x720",
            "-i",
            ":99",
            "-frames:v",
            "1",
            str(OUT / f"snap-{name}.png"),
        ],
        check=False,
    )


def pos() -> tuple[int, int]:
    q = d.screen().root.query_pointer()
    return q.root_x, q.root_y


def move(x: float, y: float, dur: float = 0.8) -> None:
    sx, sy = pos()
    steps = max(1, int(dur * 60))
    for i in range(1, steps + 1):
        k = 0.5 - math.cos(math.pi * i / steps) / 2
        xtest.fake_input(d, X.MotionNotify, x=int(sx + (x - sx) * k), y=int(sy + (y - sy) * k))
        d.sync()
        time.sleep(dur / steps)


def jiggle(seconds: float) -> None:
    x, y = pos()
    end = time.monotonic() + seconds
    i = 0
    while time.monotonic() < end:
        i += 1
        xtest.fake_input(d, X.MotionNotify, x=x + (i % 2), y=y)
        d.sync()
        time.sleep(0.05)


def button(b: int, press: bool) -> None:
    xtest.fake_input(d, X.ButtonPress if press else X.ButtonRelease, b)
    d.sync()


def click(b: int = 1) -> None:
    button(b, True)
    time.sleep(0.07)
    button(b, False)


def key(name: str, press: bool | None = None) -> None:
    code = d.keysym_to_keycode(XK.string_to_keysym(name))
    if press is None:
        key(name, True)
        time.sleep(0.05)
        key(name, False)
        return
    xtest.fake_input(d, X.KeyPress if press else X.KeyRelease, code)
    d.sync()


def drag(src: list[int], dst: list[int], dur: float = 1.3, hover: float = 0.5) -> None:
    move(*src, 0.8)
    time.sleep(0.25)
    button(1, True)
    move(src[0] + 14, src[1] + 10, 0.2)  # past the drag threshold
    move(*dst, dur)
    jiggle(hover)
    button(1, False)


def wait_for(path: Path, timeout: float = 60) -> None:
    end = time.monotonic() + timeout
    while time.monotonic() < end and not path.exists():
        time.sleep(0.1)


def window_origin(title: str) -> tuple[int, int]:
    out = subprocess.run(
        [
            "xdotool",
            "search",
            "--onlyvisible",
            "--name",
            f"^{title}$",
            "getwindowgeometry",
            "--shell",
        ],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    vals = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    return int(vals["X"]), int(vals["Y"])


def type_text(text: str) -> None:
    subprocess.run(["xdotool", "type", "--delay", "45", text], check=False)


def main() -> None:
    global t0
    xtest.fake_input(d, X.MotionNotify, x=880, y=560)
    d.sync()
    rec = subprocess.Popen(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "x11grab",
            "-framerate",
            "30",
            "-video_size",
            "1280x720",
            "-draw_mouse",
            "1",
            "-i",
            ":99",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "14",
            "-pix_fmt",
            "yuv420p",
            str(OUT / "raw.mkv"),
        ],
        stdin=subprocess.PIPE,
    )
    t0 = time.monotonic() + 0.25  # ffmpeg start-up
    try:
        scenes()
    except SystemExit:
        pass
    finally:
        time.sleep(0.5)
        rec.communicate(b"q", timeout=30)
        (OUT / "events.json").write_text(json.dumps(events, indent=1))


def scenes() -> None:
    time.sleep(1.0)
    mark("intro")
    time.sleep(2.2)

    # 1. The hotkey opens the panel.
    mark("hotkey")
    time.sleep(0.9)
    subprocess.Popen(["roue", "panel"])
    time.sleep(1.9)

    # 2. Drag a phone photo from Files onto the JPG tile.
    mark("drag")
    drag(C["heic_a"], C["tile_jpg"])
    move(*C["rest"], 0.6)  # out of the way, so no tooltip pops up
    mark("dropped")
    wait_for(PICS / "IMG_2041.jpg", 15)
    time.sleep(2.6)

    # 3. Right-click a screen recording > Convert to… > Under 10 MB.
    mark("rightclick")
    move(*C["mov"], 0.9)
    time.sleep(0.2)
    click(3)
    time.sleep(1.0)
    mark("menu")
    move(*C["menu_convert"], 0.7)
    time.sleep(0.3)
    click(1)
    time.sleep(0.9)
    mark("submenu")
    move(*C["menu_10mb"], 0.6)
    time.sleep(0.4)
    click(1)
    mark("converting")
    time.sleep(1.5)
    mark("converting-mid")
    wait_for(PICS / "Screen recording (10MB).mp4", 90)
    mark("converted")
    time.sleep(2.6)

    # 4. Esc hides the panel.
    mark("esc")
    move(*C["panel_status"], 0.7)
    click(1)
    time.sleep(0.3)
    key("Escape")
    time.sleep(1.4)

    # 5. X11: hold Shift while dragging, the panel comes to you.
    mark("shiftdrag")
    move(*C["heic_b"], 0.8)
    time.sleep(0.3)
    key("Shift_L", True)
    time.sleep(0.25)
    button(1, True)
    move(C["heic_b"][0] + 14, C["heic_b"][1] + 10, 0.2)
    move(*C["shift_waypoint"], 0.7)
    jiggle(0.9)
    mark("panel-popped")
    key("Shift_L", False)
    time.sleep(0.2)
    px, py = window_origin("Roue")
    move(px + C["strip_offset"][0], py + C["strip_offset"][1], 0.9)
    jiggle(0.5)
    mark("pre-drop")
    button(1, False)
    move(px + 300, py + 640, 0.5)
    mark("shiftdropped")
    wait_for(PICS / "IMG_2047 (clean).HEIC", 20)  # same case as the original
    time.sleep(2.4)

    # 6. Same presets from the terminal.
    mark("cli")
    rc = HERE / "bashrc"
    subprocess.Popen(
        [
            "xterm",
            "-fa",
            "DejaVu Sans Mono",
            "-fs",
            "12",
            "-b",
            "18",
            "-geometry",
            "86x14",
            "-bg",
            "#16161e",
            "-fg",
            "#e6e6ef",
            "-cr",
            "#e6e6ef",
            "-title",
            "Terminal",
            "-e",
            "bash",
            "--rcfile",
            str(rc),
        ]
    )
    time.sleep(1.4)
    type_text('roue gif "Screen recording.mov"\n')
    wait_for(PICS / "Screen recording.gif", 60)
    time.sleep(1.2)
    type_text("roue list --for IMG_2041.HEIC | head -5\n")
    time.sleep(2.8)
    mark("end")
    time.sleep(0.5)


if __name__ == "__main__":
    main()
