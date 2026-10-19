"""Assemble the demo: title card, captioned recording (with one sped-up wait), end card.

Usage: python3 post.py OUT_DIR   (reads raw.mkv, events.json and the rendered PNGs)
"""

import json
import subprocess
import sys
from pathlib import Path

P = Path(sys.argv[1])
ev = {e["event"]: e["t"] for e in json.loads((P / "events.json").read_text())}
FPS, W, H, BAND = 30, 1280, 800, 80
TITLE, END, XF1, XF2 = 2.8, 3.6, 0.5, 0.6

# (start, end, speed) in raw recording time
segments = [
    (0.6, ev["converting-mid"] + 0.3, 1.0),
    (ev["converting-mid"] + 0.3, ev["converted"] - 0.4, 2.0),  # waiting on the encode
    (ev["converted"] - 0.4, ev["end"] + 0.4, 1.0),
]


def out_time(t: float) -> float:
    acc = 0.0
    for a, b, speed in segments:
        if t <= b:
            return acc + max(0.0, t - a) / speed
        acc += (b - a) / speed
    return acc


main_dur = out_time(segments[-1][1])
captions = [
    ("A", 0.8, ev["hotkey"]),
    ("B", ev["hotkey"], ev["drag"]),
    ("C", ev["drag"], ev["rightclick"]),
    ("D", ev["rightclick"], ev["converting"]),
    ("E", ev["converting"], ev["shiftdrag"]),
    ("G", ev["shiftdrag"], ev["wheel-popped"] + 0.4),
    ("H", ev["wheel-popped"] + 0.4, ev["cli"]),
    ("I", ev["cli"], ev["end"] + 0.4),
]


def still(name: str, dur: float) -> list[str]:
    """A PNG looped into a video input."""
    return ["-loop", "1", "-framerate", str(FPS), "-t", f"{dur:.3f}", "-i", str(P / name)]


inputs = ["-i", str(P / "raw.mkv")]
inputs += still("title.png", TITLE) + still("end.png", END) + still("mark.png", main_dur)
for cid, *_ in captions:
    inputs += still(f"cap-{cid}.png", main_dur)

f = []
for i, (a, b, speed) in enumerate(segments):
    f.append(f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=(PTS-STARTPTS)/{speed}[s{i}]")
f.append(
    "".join(f"[s{i}]" for i in range(len(segments)))
    + f"concat=n={len(segments)}:v=1:a=0,fps={FPS},pad={W}:{H}:0:0:color=0x0d0f17[m0]"
)
f.append(f"[m0][3:v]overlay=x=22:y={H - BAND}+({BAND}-h)/2[m1]")
label = "m1"
for k, (_cid, a, b) in enumerate(captions):
    s, e = out_time(a), out_time(b)
    idx = 4 + k
    f.append(
        f"[{idx}:v]format=rgba,fade=t=in:st={s:.3f}:d=0.3:alpha=1,"
        f"fade=t=out:st={max(s, e - 0.3):.3f}:d=0.3:alpha=1[c{k}]"
    )
    nxt = f"m{k + 2}"
    f.append(
        f"[{label}][c{k}]overlay=x=(W-w)/2:y={H - BAND}+({BAND}-h)/2:"
        f"enable='between(t,{s:.3f},{e:.3f})'[{nxt}]"
    )
    label = nxt
norm = f"fps={FPS},format=yuv420p,settb=AVTB,setsar=1"
f.append(f"[{label}]{norm}[main]")
f.append(f"[1:v]{norm}[title]")
f.append(f"[2:v]{norm}[end]")
f.append(f"[title][main]xfade=transition=fade:duration={XF1}:offset={TITLE - XF1:.3f}[x1]")
f.append(
    f"[x1][end]xfade=transition=fade:duration={XF2}:offset={TITLE - XF1 + main_dur - XF2:.3f},"
    "format=yuv420p[out]"
)
out = P / "roue-demo.mp4"
cmd = [
    "ffmpeg",
    "-v",
    "error",
    "-y",
    *inputs,
    "-filter_complex",
    ";".join(f),
    "-map",
    "[out]",
    "-c:v",
    "libx264",
    "-preset",
    "slow",
    "-crf",
    "21",
    "-pix_fmt",
    "yuv420p",
    "-movflags",
    "+faststart",
    str(out),
]
subprocess.run(cmd, check=True)
print(f"main {main_dur:.1f}s, total ~{TITLE - XF1 + main_dur - XF2 + END:.1f}s -> {out}")
