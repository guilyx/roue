# Install

Roue needs Linux, Python 3.12+, and GTK 4 with libadwaita 1.5+ for the wheel
and the panel.
Ubuntu 24.04, Debian 13, Fedora 40 and newer all qualify. The command line and
the conversion engine work without GTK.

## Ubuntu and Debian (.deb)

Download `roue_0.1.0_all.deb` from the
[releases page](https://github.com/guilyx/roue/releases/latest), then:

```sh
sudo apt install ./roue_0.1.0_all.deb
roue setup
```

The package installs the app, the launcher, the D-Bus service and the Files
right-click menu, and pulls in FFmpeg and libvips. `roue setup` only adds your
personal hotkey (**Super+Shift+D**, which opens the wheel).

## Any distribution, from source

Install the dependencies with your package manager. On Ubuntu:

```sh
sudo apt install ffmpeg libvips-tools ghostscript python3-gi python3-gi-cairo \
  gir1.2-gtk-4.0 gir1.2-adw-1 python3-nautilus libheif-plugin-libde265 pipx
```

Then install Roue for your user and hook it into the desktop:

```sh
pipx install --system-site-packages git+https://github.com/guilyx/roue
roue setup
```

`--system-site-packages` lets Roue use your distribution's PyGObject and GTK.
`roue setup` writes the launcher, the D-Bus service, the icon and the Files
extension under `~/.local/share`, and sets the hotkey on GNOME.

Other package names:

| Tool | Fedora | Arch | openSUSE |
|---|---|---|---|
| FFmpeg | `ffmpeg-free` | `ffmpeg` | `ffmpeg` |
| libvips | `vips-tools` | `libvips` | `vips` |
| ImageMagick (fallback) | `ImageMagick` | `imagemagick` | `ImageMagick` |
| Ghostscript | `ghostscript` | `ghostscript` | `ghostscript` |
| Pandoc | `pandoc` | `pandoc` | `pandoc` |
| LibreOffice | `libreoffice` | `libreoffice-fresh` | `libreoffice` |
| PyGObject (with cairo), GTK 4, libadwaita | `python3-gobject gtk4 libadwaita` | `python-gobject python-cairo gtk4 libadwaita` | `python3-gobject-cairo typelib-1_0-Gtk-4_0 typelib-1_0-Adw-1` |
| Files extension host | `nautilus-python` | `python-nautilus` | `python3-nautilus` |

## What each tool does

Roue drives existing command-line tools. Install the ones you need. Presets
whose tools are missing stay off the wheel, and their tiles in the panel are
greyed out with a hint.

| Tool | Used for | Needed by |
|---|---|---|
| FFmpeg (+ ffprobe) | video and audio | MP4, GIF, WebM, Under 10/25 MB, Mute, MP3, Opus, WAV, FLAC… |
| libvips | fast images, HEIC, AVIF | JPG, PNG, WebP, AVIF, resizes, metadata removal |
| ImageMagick | images, when libvips is missing | same as libvips (AVIF output may not work) |
| Ghostscript | PDFs | Compress PDF, Pages to PNG, Text |
| Pandoc | Markdown, reStructuredText, Org | Word, Web page, PDF from Markdown |
| LibreOffice | office documents | PDF from DOCX, XLSX, PPTX, ODT… |

**HEIC photos** need the HEVC decoder plugin for libheif. On Ubuntu and
Debian: `sudo apt install libheif-plugin-libde265`. Writing **AVIF** needs the
AV1 encoder plugin: `sudo apt install libheif-plugin-aomenc`.

**Markdown to PDF** uses the first PDF engine it finds (`typst`, `weasyprint`,
`wkhtmltopdf`, `tectonic`, `xelatex`, `pdflatex`). With none installed, Pandoc
writes an ODT file and LibreOffice prints it to PDF.

## Check your setup

```sh
roue doctor
```

It shows every tool, which presets are ready, and one command to install
everything that's missing.

## Update

- `.deb`: install the new release the same way.
- pipx: `pipx upgrade roue`.

## Uninstall

```sh
roue setup --remove      # removes the hotkey and the files roue setup added
sudo apt remove roue     # if you used the .deb
pipx uninstall roue      # if you used pipx
```

Your settings live in `~/.config/roue/` and your history in
`~/.local/state/roue/`. Delete them too for a clean slate.

## For contributors

```sh
git clone https://github.com/guilyx/roue
cd roue
make dev     # virtualenv with your system's GTK, plus dev tools
make test    # the test suite
make site    # build this website into website/
```

See [Contributing](contributing.md).
