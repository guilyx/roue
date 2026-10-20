# Privacy

Short version: **your files never leave your computer.**

## What Roue does

- Runs conversion tools (FFmpeg, libvips, Ghostscript, Pandoc, LibreOffice)
  **on your machine**, on the files you drop.
- Writes results next to your originals, or to the folder you chose.
- Keeps a small list of your last 50 conversions (file paths and preset names)
  in `~/.local/state/roue/history.jsonl`, so **Undo** and **Recent
  Conversions** work. Delete the file any time.
- Saves your settings in `~/.config/roue/settings.yaml`.

## What Roue never does

- **No network.** Roue doesn't open a single connection. It works the same with
  Wi-Fi off.
- **No uploads**, no "cloud conversion", no third-party APIs.
- **No accounts.**
- **No telemetry, analytics or crash reporting.** We don't know you use it, and
  we like it that way.
- **No surprises with your files.** It never overwrites or deletes anything.
  Undo moves results to the trash, where you can restore them.

## Privacy presets

**Remove metadata** (`strip-metadata`) drops the location, camera model, dates
and other details hidden inside photos before you share them. The picture is
rotated upright first, so it still looks right without its orientation tag.

## This website

The website is static HTML hosted on GitHub Pages. It loads no trackers, no
analytics and no third-party fonts or scripts. GitHub may keep standard server
logs; see GitHub's privacy statement.

## Custom presets

A [custom preset](custom-presets.md) with the `command` backend runs whatever
program you put in it. That's your call: Roue runs it locally, without a shell,
only on the files you drop.

## Found a problem?

See [SECURITY.md](../SECURITY.md) to report it privately.
