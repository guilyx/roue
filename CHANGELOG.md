# Changelog

All notable changes to Roue are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - Unreleased

First public release.

### Added

- **The wheel**: a radial menu with the (up to) seven presets that fit your
  files best, plus **More…** for the full panel. It opens at the pointer from
  the Files menu and from Shift-drag on X11, and as a small round window to
  drop files on from the hotkey. Keyboard: arrows/Tab, Enter, 1–8, Esc. A
  desktop notification ("Open" / "Show in Folder") says when the conversion
  is done.
- **Ways to open it**: global hotkey (Super+Shift+D on GNOME, set by
  `roue setup`, runs `roue wheel`), Shift-drag on X11 (the wheel springs open
  around the pointer; release Shift, then drop), `roue wheel [FILE...]`.
- **Full panel** (GTK 4 + libadwaita): every preset as a tile grouped by kind,
  dims the tiles that can't take the dragged files, progress ring per tile,
  search, toasts with "Show". Opens from the wheel's **More…**, the app
  launcher and `roue panel`.
- **Copied files**: copy files in Files (Ctrl+C), press the hotkey, click a
  slice. In the panel, Ctrl+V and Ctrl+O also stage files; type to search,
  Enter to run.
- **Files (Nautilus) menu**: right-click > "Convert with Roue…" opens the
  wheel at the pointer with the presets that fit every selected file.
- **Command line**: `roue convert`, the `roue PRESET FILE...` shorthand,
  `list`, `info`, `doctor`, `history`, `undo`, `setup`, `wheel`, `panel`,
  `quit`.
  `--json` output and meaningful exit codes for scripts.
- **27 built-in presets**:
  - Images: JPG, PNG, WebP, AVIF, half size, 1080 px wide, double size,
    compress, remove metadata.
  - Video: MP4, GIF, WebM, under 10 MB, under 25 MB, smaller video, mute.
  - Audio: MP3, Opus, WAV, FLAC, even out volume (EBU R128).
  - Documents: PDF (office files and Markdown), Word, web page, compress PDF,
    PDF pages to PNG, PDF to text.
- **Custom presets** as YAML in `~/.config/roue/presets`, including a
  `command` backend with `{in}` / `{out}` placeholders.
- **Safety**: results never overwrite anything (`photo (2).jpg`), read-only
  folders fall back to Downloads, "compress" presets keep the original when
  the result isn't smaller, undo moves results to the trash.
- **Batch**: several files and folders per drop, converted in parallel.
- **Preferences**: hotkey, Shift-drag, output folder, notifications, parallel
  jobs, enable/disable presets, and a tools check with the install command.
- **Plain-English errors**, such as "This video has no audio track to
  extract.", with the tool output available via `--verbose`.
- Packaging: `.deb`, AppStream metadata, man page, `roue setup` for pipx and
  source installs.
- **One-command install** on Ubuntu and Debian:
  `wget -qO- https://guilyx.github.io/roue/install.sh | sh` adds the update
  channel, installs the package and runs `roue setup`. It uses `wget`: stock
  Ubuntu doesn't include `curl`.
- **Updates through Software Updater**: a signed APT channel published on the
  website from the last five releases. The `.deb` ships its sources file (a
  conffile: delete it to opt out) and key. `roue doctor` says whether it's
  set up. Roue itself still never uses the network.
- **Set Up Roue**: a first-launch dialog, also in the main menu, with one
  button per thing that isn't ready: the Files menu (installs
  `python3-nautilus`, restarts Files), the hotkey, the GNOME helper, and
  missing conversion tools (installed with apt after a password prompt).
- **GNOME helper**: an optional GNOME Shell extension (shipped in the `.deb`,
  turned on by `roue setup`, Set Up Roue or Preferences) that keeps the wheel
  above other windows and opens the hotkey's wheel at the pointer on Wayland.
- **GNOME on Wayland**, checked in a real GNOME Shell session: the wheel at the
  pointer sits on a maximised see-through layer (GNOME paints black behind
  full-screen windows), opens at the pointer even when the first pointer
  event comes late, and closes when another window takes focus. The hotkey's
  wheel picks up files copied with Ctrl+C once it has focus, as Wayland
  requires.
- **Ubuntu 25.10 and 26.04**: the Files menu supports Nautilus 49+ and its
  4.1 extension API. Tested on Ubuntu 26.04 with GNOME 50 and Python 3.14.
- Notification clicks pass GNOME's activation token on to the app they open,
  so it may come to the front.

### Fixed

- The symbolic icon showed as a dot in GNOME Shell: it is now drawn with
  fills only.
- The PDF preset no longer looks ready when only Pandoc is installed: it
  needs LibreOffice, or Pandoc with a PDF engine.
- `roue setup` checks for `python3-nautilus` with the `.deb` too, and only
  asks you to restart Files when Files started before the menu was installed.

[Unreleased]: https://github.com/guilyx/roue/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/guilyx/roue/releases/tag/v0.1.0
