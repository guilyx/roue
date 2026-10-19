# Demo video

Scripts that record `website/assets/demo.mp4`: a real GNOME Files + Roue session
on a virtual display, driven with real mouse and keyboard input (XTest), then
captioned. Every conversion in the video actually happens.

## Run it

As a normal user (Files refuses to run as root):

```bash
scripts/demo/record.sh        # ~2 minutes -> scripts/demo/out/roue-demo.mp4
```

It uses a throwaway home in `scripts/demo/out/home`, so your own files,
settings and history are never touched.

Then refresh the published copies:

```bash
cp scripts/demo/out/roue-demo.mp4 website/assets/demo.mp4
ffmpeg -i website/assets/demo.mp4 -c:v libvpx-vp9 -b:v 0 -crf 38 -an website/assets/demo.webm
ffmpeg -ss 9.5 -i website/assets/demo.mp4 -frames:v 1 -q:v 3 website/assets/demo-poster.jpg
ffmpeg -ss 4.3 -to 13.2 -i website/assets/demo.mp4 -an /tmp/clip.mp4 && roue gif /tmp/clip.mp4
mv /tmp/clip.gif website/assets/demo.gif   # the README animation, made by Roue itself
```

## Requirements (Ubuntu 24.04)

```bash
sudo apt install xvfb openbox picom feh xterm xdotool x11-xserver-utils \
  nautilus python3-nautilus python3-xlib imagemagick libvips-tools \
  libheif-plugin-libde265 libheif-plugin-x265 pandoc ffmpeg nodejs npm
npm install -g playwright && npx playwright install chromium   # captions and cards
```

## How it fits together

| File | Role |
|---|---|
| `record.sh` | Sample files, Xvfb, D-Bus session, then captions |
| `session.sh` | Compositor, window manager, wallpaper, Files, Roue in the background |
| `director.py` | The scene: moves the mouse, drags, right-clicks, types; logs scene marks |
| `coords.json` | Screen positions for 1280×720 with Nautilus 46 and libadwaita 1.5 |
| `openbox.xml`, `picom.conf` | Window placement, rounded corners and shadows |
| `render_cards.js` | Title card, end card and caption images (Playwright) |
| `post.py` | Cuts, a 2× speed-up while the video encodes, captions, cards |

## After a UI change

Positions in `coords.json` may drift. Record step by step with a screenshot
at each scene mark, check them in `scripts/demo/out/snap-*.png`, and adjust:

```bash
SNAP=1 STOP_AFTER=submenu scripts/demo/record.sh
```
