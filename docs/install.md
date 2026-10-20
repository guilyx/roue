# Install

Roue needs Linux, Python 3.12+, and GTK 4.12+ with libadwaita 1.5+ for the
wheel and the panel.
Ubuntu 24.04, Debian 13, Fedora 40 and newer all qualify. The command line and
the conversion engine work without GTK.

Tested on Ubuntu 24.04 (GNOME 46, Wayland) and Ubuntu 26.04 (GNOME 50,
Python 3.14).

## Ubuntu and Debian: one command

```sh
wget -qO- https://guilyx.github.io/roue/install.sh | sh
```

It asks for your password, then:

1. Adds Roue's signed update channel:
   `/etc/apt/sources.list.d/roue.sources` and
   `/usr/share/keyrings/roue-archive-keyring.gpg`.
2. Installs the `roue` package with apt, which pulls in FFmpeg and libvips.
3. Runs `roue setup` for you: the Files menu, the **Super+Shift+D** hotkey and,
   on GNOME, the GNOME helper.

Want to read it first? Open
[install.sh](https://guilyx.github.io/roue/install.sh) in your browser, or
download it and run it with `sh install.sh`. (Ubuntu ships `wget`, not `curl`.)

## Ubuntu and Debian: the .deb by hand

Download `roue_<version>_all.deb` from the
[releases page](https://github.com/guilyx/roue/releases/latest), then:

```sh
sudo apt install ./roue_<version>_all.deb
```

Double-clicking the file may also work, depending on your Ubuntu version's
App Center. The package installs the app, the launcher, the D-Bus service, the
Files right-click menu, the GNOME helper and Roue's update channel.

## First launch: Set Up Roue

Open Roue from your apps. The first time, **Set Up Roue** shows what's ready
and offers one button for each thing that isn't:

- **Right-click in Files**: installs `python3-nautilus` if it's missing, or
  restarts Files so **Convert with Roue…** shows up (Files' windows close).
- **Keyboard shortcut**: sets **Super+Shift+D** to open the wheel.
- **Wheel on top, at the pointer** (GNOME on Wayland): turns on the
  [GNOME helper](desktop-integration.md#the-gnome-helper).
- **Conversion tools**: one **Install** button per missing tool. It asks for
  your password, then installs the package with apt. LibreOffice (Office
  documents to PDF) is a large download: skip it if you don't need it.

Open it again any time from the panel's main menu: **Set Up Roue…**. In a
terminal, `roue setup` does the same, minus the tools.

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

## Updates

The `.deb` adds Roue's update channel, so **Software Updater** offers new
versions of Roue next to your other updates. In a terminal:

```sh
sudo apt update && sudo apt upgrade
```

`roue doctor` shows whether the channel is set up.

Roue itself never checks for updates and never contacts the network: apt
does the checking, as for any other Ubuntu app.

**Opt out**: delete `/etc/apt/sources.list.d/roue.sources`. Upgrades don't
bring it back.

**Install updates automatically**: Ubuntu's unattended upgrades only take
security updates by default. To let them install Roue too, create
`/etc/apt/apt.conf.d/52roue-unattended` with:

```text
Unattended-Upgrade::Origins-Pattern { "origin=Roue"; };
```

**pipx installs**: `pipx upgrade roue`.

## Uninstall

```sh
roue setup --remove      # your hotkey, GNOME helper and the files roue setup added
sudo apt purge roue      # if you used the .deb: also removes the update channel
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
