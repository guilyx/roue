# Changelog

All notable changes to Roue are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - Unreleased

First public release.

### Added

- **Drop panel** (GTK 4 + libadwaita): preset tiles grouped by kind, dims the
  tiles that can't take the dragged files, progress ring per tile, toasts with
  "Show" and desktop notifications with "Open" / "Show in folder".
- **Ways to open it**: global hotkey (Super+Shift+D on GNOME, set by
  `roue setup`), Shift-drag on X11, the app launcher, `roue panel`.
- **Copied files**: copy files in Files (Ctrl+C), open the panel, click a
  tile. Ctrl+V and Ctrl+O also stage files; type to search, Enter to run.
- **Files (Nautilus) menu**: right-click > "Convert to…" with the presets
  that fit every selected file.
- **Command line**: `roue convert`, the `roue PRESET FILE...` shorthand,
  `list`, `info`, `doctor`, `history`, `undo`, `setup`, `panel`, `quit`.
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

[Unreleased]: https://github.com/guilyx/roue/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/guilyx/roue/releases/tag/v0.1.0
