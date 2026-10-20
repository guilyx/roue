# Architecture

**One engine, three front doors.** The wheel (and the full panel behind its
**More…**), the Files menu and the command line are thin layers over the same
engine. No conversion logic lives in UI code.

```text
            ┌──────────────┐  ┌─────────────────┐  ┌──────────────┐
            │ Wheel, panel │  │ Files (Nautilus) │  │   roue CLI   │
            │ GTK 4 + Adw  │  │  menu extension  │  │   argparse   │
            └──────┬───────┘  └────────┬────────┘  └──────┬───────┘
                   │      D-Bus actions│                  │
                   ▼                   ▼                  ▼
            ┌───────────────────────────────────────────────────┐
            │  engine (no GTK)                                  │
            │  presets · detect · runner · output · history     │
            │  backends: image, ffmpeg, document, ghostscript,  │
            │            command                                │
            └──────────────────────┬────────────────────────────┘
                                   ▼
               ffmpeg · vips · gs · pandoc · soffice · your tools
```

## Layout

```text
src/roue/
├── engine/            pure Python, fully tested, no GTK imports
│   ├── presets.py     preset model, YAML loader, validation, matching
│   ├── detect.py      MIME types, file kinds, ffprobe media info
│   ├── runner.py      job queue, parallelism, cancellation, progress
│   ├── output.py      naming, scratch folders, never-overwrite commit
│   ├── history.py     recent conversions, undo to trash
│   ├── settings.py    ~/.config/roue/settings.yaml
│   ├── tools.py       which tools exist, how to install them
│   └── backends/      one module per family of tools
├── presets/           built-in presets, as YAML
├── radial.py          wheel geometry and which presets it shows (no GTK)
├── ui/                the GTK 4 / libadwaita app (wheel, panel, preferences)
├── integrations/      hotkey, desktop files, notifications, X11 Shift-drag
├── data/              .desktop and D-Bus templates, icons, Files extension
└── cli.py             the roue command
```

## Presets are data

A preset is a YAML mapping: what it accepts, the output extension, a backend
and its params. Adding a conversion usually means adding YAML, not code. The
loader validates every field and turns mistakes into plain sentences;
broken user presets are reported, never fatal.

## The runner

`Runner.submit(preset, paths)` returns a `Batch` of `Job`s and runs them on a
thread pool (one worker per CPU core by default). Video jobs also take a slot
from a smaller semaphore, because each FFmpeg already uses every core.

For each job the runner:

1. checks the file exists and the preset accepts its MIME type (otherwise the
   job is **skipped**, not failed);
2. checks the tools are installed (otherwise a `MissingToolError` with the
   install command);
3. picks the destination folder (next to the original, the chosen folder, or
   Downloads when the original's folder is read-only);
4. creates a hidden scratch folder **inside the destination**, so the final move
   is instant and on the same filesystem;
5. runs the backend, which writes `result.<ext>` (or files in `out/`);
6. commits the result and removes the scratch folder, whatever happened.

Callbacks (`on_update`, `on_batch_done`) fire from worker threads. The GTK app
hops back to its main loop with `GLib.idle_add`.

Cancelling a job kills the tool's whole process group, and the scratch folder
goes with it: no half-written files are left behind.

## Never overwrite

Results are committed with `os.link(tmp, target)`, which fails if `target`
exists, even if it appeared a millisecond ago. Where hard links aren't
supported (FAT drives, some network shares), the result is copied into a file
opened with exclusive create (`open(target, "xb")`). On a clash, the next name
is tried: `photo (2).jpg`, `photo (3).jpg`…

Undo moves results to the freedesktop.org trash (through `gio trash`, or a
built-in implementation). Nothing is ever deleted outright.

## Errors in plain words

Every engine error is a `RoueError` with a short `message` for people, an
optional `hint` (like the install command) and `details` (the tool's raw
output, shown with `--verbose`). Common tool failures are recognised and
translated: "No space left on device" becomes "The disk is full."

## Backends

| Backend | Tools | Notes |
|---|---|---|
| `image` | `vips`, else `magick`/`convert` | Input is passed through a symlink so `[...]` in file names isn't parsed as options. |
| `ffmpeg` | `ffmpeg`, `ffprobe` | Progress from `-progress pipe:1`. Two-pass sizing for `target-size`. |
| `document` | `soffice`, `pandoc` | Isolated LibreOffice profile per job, so it works while LibreOffice is open. |
| `ghostscript` | `gs` | Page progress from Ghostscript's output. |
| `command` | anything | No shell. Placeholders `{in}`, `{out}`, `{outdir}`, `{stem}`. |

## The app

The GTK app is a single-instance `Adw.Application` (`io.github.guilyx.Roue`).
The hotkey runs `roue wheel`, which forwards to the running instance over
D-Bus, and the D-Bus service file starts it on demand. The Files extension
calls the app's `wheel-files` action with the selected paths (and an
activation token, so the wheel may take focus), falling back to `roue wheel`
when the app can't be reached.

The wheel (`ui/wheel.py`) is one view in two windows: a transparent
full-screen layer that centres the wheel on the pointer when the files are
known (on Wayland the pointer position arrives with the first pointer event
on that layer), and a small round window to drop files on for the hotkey.
Which presets it shows, and where each slice sits, is plain Python in
`radial.py`, tested without a display. After a pick, the wheel closes and the
app sends a notification when the batch is done.

On X11, a background thread watches for `XdndSelection` ownership changes
(every drag source takes it when a drag starts) through XFixes, then polls the
pointer for Shift and opens the wheel around it. Wayland deliberately offers
nothing like this.

## Tests

`pytest` runs every built-in preset on generated sample files (no binary
fixtures in the repo), plus unit tests for naming, presets, the runner,
history, settings, the wheel's geometry and the CLI. GTK tests (the panel, the
wheel, the Files extension) run under a virtual display in CI
(`xvfb-run pytest`). Tests skip when a tool is missing; CI installs
everything so nothing is skipped there.
