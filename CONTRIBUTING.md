# Contributing to Roue

Thanks for helping! Roue is small on purpose, so most contributions are
quick: a new preset, a clearer error message, a fix for a file that didn't
convert.

**Quick links:** [open issues](https://github.com/guilyx/roue/issues) ·
[good first issues](https://github.com/guilyx/roue/labels/good%20first%20issue) ·
[roadmap](ROADMAP.md) · [architecture](https://guilyx.github.io/roue/docs/architecture.html)

## Set up (5 minutes)

You need Ubuntu 24.04+ (or any distro with GTK 4.14+ and libadwaita 1.5+).

```bash
# 1. System packages: GTK bindings and the conversion tools
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 python3-venv \
  ffmpeg libvips-tools libheif-plugin-libde265 ghostscript pandoc imagemagick
# optional: libreoffice-writer (document tests), python3-nautilus, python3-xlib

# 2. A virtualenv that can see PyGObject, with Roue installed in editable mode
git clone https://github.com/guilyx/roue && cd roue
make dev

# 3. Check everything works
make check          # ruff + mypy + pytest
.venv/bin/roue doctor
```

`make help` lists every target. The ones you'll use most:

| Command | Does |
|---|---|
| `make test` | Full test suite (real conversions for every preset) |
| `make test-fast` | Skips slow ones (LibreOffice, two-pass video) |
| `make lint` / `make fmt` | Ruff checks / auto-fix and format |
| `make typecheck` | Mypy (strict) on the engine, CLI and integrations |
| `make run` | Open the drop panel from your checkout |
| `make site` | Build the website and docs |
| `make deb` | Build `dist/roue_<version>_all.deb` |

Tests skip (not fail) when a tool isn't installed. CI installs everything,
so nothing is skipped there.

## Project layout

```
src/roue/
├── engine/          # No GTK. Pure Python, fully tested.
│   ├── presets.py   #   YAML presets: loading, validation, matching
│   ├── runner.py    #   Parallel job queue, cancellation, never-overwrite commit
│   ├── output.py    #   File naming, scratch folders, read-only fallback
│   ├── detect.py    #   MIME types and ffprobe details
│   ├── tools.py     #   External tools and how to install them
│   ├── history.py   #   Recent conversions and undo (to the trash)
│   └── backends/    #   ffmpeg, image (vips/ImageMagick), document, ghostscript, command
├── presets/         # Built-in presets, one YAML file per group
├── ui/              # GTK 4 + libadwaita: panel, tiles, preferences
├── integrations/    # Hotkey, Files menu, notifications, X11 Shift-drag
├── data/            # Desktop file, D-Bus service, icons, Nautilus extension
└── cli.py           # The `roue` command
tests/               # pytest; sample media is generated at test time
docs/  website/      # Documentation and the landing page
packaging/           # .deb build script and man page
```

**The one architectural rule:** the panel, the Files menu and the CLI are thin
front doors. Conversion logic lives in `engine/`, which never imports GTK.

## Add a preset

Most presets are just YAML. Say you want "Instagram square":

1. Add it to the right file in `src/roue/presets/` (e.g. `10-image.yaml`).
   Use an existing backend and its `params` (documented at the top of each
   `engine/backends/*.py`). Give it a `description`, a symbolic `icon`, and a
   `suffix` if the output could share the original's extension.
2. Add a case to `CASES` in `tests/test_conversions.py`: the sample to use
   and the expected output name. `test_every_builtin_preset_has_a_case` fails
   until you do.
3. Run `make test` and try it for real: `.venv/bin/roue your-id some-file`.
4. Mention it in `CHANGELOG.md` under *Unreleased*.

Need behaviour no backend has? Add a `params` option to the closest backend,
or a new `mode`, with a unit test.

## Error messages

People see these, so they're part of the UI:

- Plain words, no jargon, no raw tool output: *"This video has no audio
  track to extract."*
- Say what to do when you can (`hint=`): *"Install it with: sudo apt install ffmpeg"*.
- Put tool output in `details=`; it's shown with `--verbose` and in bug reports.

## Working on the panel

```bash
make run                                  # or: .venv/bin/roue panel
GTK_DEBUG=interactive .venv/bin/roue panel  # GTK inspector
.venv/bin/roue quit                        # stop the background instance
```

Roue is single-instance: if it's already running (it stays in the background
by default), `roue panel` talks to the running copy. Run `roue quit` after
changing UI code.

To test without touching your session, run a nested GNOME Shell (GNOME 45+):

```bash
dbus-run-session -- gnome-shell --nested --wayland   # GNOME 49+: --devkit
# then, in another terminal:
WAYLAND_DISPLAY=wayland-1 .venv/bin/roue panel
```

For X11 Shift-drag, use an X11 session or `Xephyr :2 & DISPLAY=:2 ...`.

## Commits and pull requests

- [Conventional Commits](https://www.conventionalcommits.org): `feat: add
  instagram-square preset`, `fix(ffmpeg): keep sample rate when normalizing`,
  `docs: ...`, `test: ...`, `chore: ...`.
- One topic per PR. Small is great.
- Before pushing: `make check`.
- The PR template has a short checklist. CI runs lint, types, the full test
  suite with every tool installed, the website build and a `.deb` install test.

## Ground rules

- **Local only.** No network calls, no telemetry, no accounts. Ever.
- **Never overwrite or delete user files.** Undo moves results to the trash.
- **No full editors.** Small one-off dialogs are fine (like a future trim dialog).

By contributing you agree that your work is licensed under
[GPL-3.0-or-later](LICENSE), and to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
