# FAQ

## Wayland or X11: what's the difference for me?

| | Wayland (Ubuntu's default) | X11 |
|---|---|---|
| Hotkey (Super+Shift+D) | ✓ | ✓ |
| Copy files, then open the panel | ✓ | ✓ |
| Drag onto the panel | ✓ | ✓ |
| Files right-click menu | ✓ | ✓ |
| Shift-drag pops the panel anywhere | ✗ | ✓ |
| Panel opens next to the pointer | ✗ (centred) | ✓ |

Wayland keeps each app's drags and window positions private, by design. Roue
respects that instead of working around it. `roue doctor` tells you which
session you're in.

## Where do my converted files go?

Next to the original, with the same name and the new extension:
`IMG_2041.HEIC` → `IMG_2041.jpg`. Presets that keep the format add a suffix:
`clip.mov` → `clip (muted).mov`.

To collect everything in one folder, set it in **Preferences > Results**, or
use `roue convert -o FOLDER`.

## Can Roue overwrite a file?

No. If `photo.jpg` exists, you get `photo (2).jpg`, then `photo (3).jpg`, and
so on. Results are written to a hidden temporary folder first and only then
moved into place, in a way that fails instead of replacing a file that
appeared in the meantime. Originals are opened read-only.

## The original folder is read-only. Now what?

Roue saves the result to your **Downloads** folder and tells you so. That
happens with cameras, phones mounted over MTP, ISO images and other read-only
places.

## I converted the wrong thing.

Press **Undo Last Conversion** in the panel's menu, or run `roue undo`. The
results go to the trash; run it again to go one step further back.

## HEIC photos fail with "libvips couldn't convert this image".

Your libheif is missing its HEVC decoder. On Ubuntu and Debian:

```sh
sudo apt install libheif-plugin-libde265
```

## Markdown to PDF: which engine is used?

The first one installed among `typst`, `weasyprint`, `wkhtmltopdf`,
`tectonic`, `xelatex` and `pdflatex`. With none of them, Pandoc writes an ODT
file and LibreOffice prints it to PDF. `roue doctor` shows which one you have.

## Why is a tile greyed out?

A tool it needs isn't installed. Hover the tile to see which, or open
**Preferences > Tools** (or run `roue doctor`) for the exact install command.

## Why is a tile faded while I drag?

It can't take the file you're dragging. The JPG tile fades for a JPG, video
presets fade for a PDF, and so on.

## "Already as small as it gets: the original was kept."

Compression presets only keep a result if it's actually smaller. Your file was
already well compressed, so nothing was written.

## "This video is too long to fit in 10 MB"

At that length, 10 MB leaves too little per second to stay watchable. Roue
tells you how much it would need. Trim the video first, or use **Under 25 MB**.

## Can I add my own conversions?

Yes, in a few lines of YAML. See [Custom presets](custom-presets.md). You can
even wrap any command-line tool.

## Does it work offline?

Yes. Roue never uses the network.

## How do I stop it running in the background?

`roue quit`, or **Quit** in the panel's menu. To never keep it running, turn
off **Preferences > General > Stay in the background**.

## Which desktops are supported?

The panel and command line work on any Linux desktop with GTK 4 and
libadwaita 1.5+. The automatic hotkey setup and the Files menu target GNOME;
on KDE, Xfce and others, add the hotkey by hand
([how](desktop-integration.md#the-hotkey)). Menus for Dolphin, Nemo and Thunar
are planned.

## Is it free?

Yes. Roue is free software under the GPL-3.0-or-later license.
