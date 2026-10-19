# Roue documentation

Roue is a drag-and-drop file converter for the Linux desktop. Drop a file on a
tile, get the file you wanted next to the original. Everything runs on your
computer, with tools you already trust: FFmpeg, libvips, Ghostscript, Pandoc
and LibreOffice.

## Start here

- **[Getting started](getting-started.md)**: install, then your first
  conversion in under a minute.
- **[Install](install.md)**: packages, from source, and what each tool is for.

## Use it

- **[Presets](presets.md)**: every built-in tile, what it takes and what it gives.
- **[Custom presets](custom-presets.md)**: write your own in a few lines of YAML.
- **[Command line](cli.md)**: `roue convert`, `roue list`, `roue doctor` and friends.
- **[Desktop integration](desktop-integration.md)**: the hotkey, the Files menu,
  Shift-drag on X11, and D-Bus.

## Good to know

- **[Privacy](privacy.md)**: what Roue does (and never does) with your files.
- **[FAQ](faq.md)**: Wayland vs X11, where files go, undo, HEIC, PDF engines.

## Hack on it

- **[Architecture](architecture.md)**: one engine, three front doors.
- **[Contributing](contributing.md)**: set up a dev environment, run the tests,
  add a preset.

## The rules Roue lives by

1. **Never overwrite.** Results get a new name, like `photo (2).jpg`. Originals
   are never touched.
2. **Never upload.** No network, no accounts, no telemetry.
3. **No dialogs.** Every preset does one thing with good defaults.
4. **Plain words.** Errors say what happened, like
   "This video has no audio track to extract", not a stack trace.
