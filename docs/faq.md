# FAQ

## Wayland or X11: what's the difference for me?

| | Wayland (Ubuntu's default) | X11 |
|---|---|---|
| Hotkey (Super+Shift+D) opens the wheel | ✓ | ✓ |
| Files right-click → wheel at the pointer | ✓ | ✓ |
| Copy files, then press the hotkey | ✓ | ✓ |
| Drag onto the wheel or the panel | ✓ | ✓ |
| Shift-drag opens the wheel around the pointer | ✗ | ✓ |
| The hotkey's wheel opens at the pointer, on top | GNOME, with the [GNOME helper](desktop-integration.md#the-gnome-helper) | ✓ |

Wayland keeps each app's drags and window positions private, by design. Roue
respects that instead of working around it; on GNOME, the optional GNOME
helper asks the desktop itself to place the wheel. `roue doctor` tells you
which session you're in. Ubuntu 25.10 and newer only have Wayland.

## Why isn't my preset on the wheel?

The wheel holds up to seven presets: the ones that fit your files best, most
relevant first. The rest are one click away under **More…**, which opens the
full panel. Presets whose tools aren't installed, and presets you turned off
in **Preferences > Presets**, are left off the wheel.

## The wheel shows up in a plain square window

Its see-through look needs a compositing desktop (GNOME, KDE and most others
have one, always on under Wayland). Without one, Roue shows the wheel in a
small ordinary window instead. Everything else works the same.

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

## Why is a tile greyed out in the panel?

A tool it needs isn't installed. Hover the tile to see which, or open
**Preferences > Tools** (or run `roue doctor`) for the exact install command.

## Why is a tile faded while I drag onto the panel?

It can't take the file you're dragging. The JPG tile fades for a JPG, video
presets fade for a PDF, and so on. The wheel goes one step further: it only
shows slices that fit the file.

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

Yes. Roue never uses the network. Updates come through apt, like your other
apps ([Updates](install.md#updates)).

## How do I update Roue?

If you installed the `.deb` or used the install command, Software Updater
offers new versions. `sudo apt update && sudo apt upgrade` works too. With
pipx: `pipx upgrade roue`.

## How do I stop it running in the background?

`roue quit`, or **Quit** in the panel's main menu. To never keep it running, turn
off **Preferences > General > Stay in the background**.

## Which desktops are supported?

The wheel, the panel and the command line work on any Linux desktop with GTK 4
and libadwaita 1.5+. The automatic hotkey setup and the Files menu target GNOME;
on KDE, Xfce and others, add the hotkey by hand
([how](desktop-integration.md#the-hotkey)). Menus for Dolphin, Nemo and Thunar
are planned.

## Is it free?

Yes. Roue is free software under the GPL-3.0-or-later license.
