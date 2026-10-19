# Command line

Everything the wheel and the panel do, the `roue` command does too. Same presets, same
engine, same rules: results go next to the originals, nothing is overwritten.

```text
roue                         open the full panel (or show help without a desktop)
roue PRESET FILE...          shorthand for 'roue convert PRESET FILE...'
roue convert PRESET FILE...  convert files with a preset
roue list                    list presets
roue info FILE...            what Roue sees in a file
roue doctor                  check installed tools and desktop integration
roue history                 recent conversions
roue undo                    move the results of the last conversion to the trash
roue setup                   add the launcher, hotkey and Files menu
roue wheel [FILE...]         open the wheel (the hotkey runs this)
roue panel [FILE...]         open the full panel
roue quit                    stop Roue running in the background
```

## `roue convert`

```sh
roue convert PRESET FILE... [options]
roue PRESET FILE... [options]          # same thing
```

`FILE` can be a folder: Roue converts the files inside it (hidden files are
skipped).

| Option | What it does |
|---|---|
| `-o DIR`, `--output-dir DIR` | Write results to `DIR` instead of next to the originals. |
| `-j N`, `--jobs N` | Run `N` conversions at once. Default: one per CPU core. |
| `-r`, `--recursive` | Include files in sub-folders of folders. |
| `--notify` | Show a desktop notification when done. |
| `--json` | Print results as JSON, for scripts. |
| `-q`, `--quiet` | Only print errors. |
| `-v`, `--verbose` | Show the tool's output when something fails. |

Examples:

```sh
roue jpg ~/Pictures/iPhone/*.HEIC
roue share-10mb screen-recording.mov
roue webp -o ~/site/img -j 8 ~/photos
roue pdf report.docx slides.pptx notes.md
```

Output, one line per file:

```text
✓ IMG_2041.HEIC → IMG_2041.jpg (2.1 MB)
✓ IMG_2042.HEIC → IMG_2042.jpg (1.8 MB)
- photo.jpg: 'JPG' doesn't work on this image.
✗ broken.heic: libvips couldn't convert this image.
2 files converted · 4.6 MB saved · 1 failed · 1 skipped
```

`✓` done, `-` skipped (wrong kind of file, or nothing to gain), `✗` failed.

### JSON output

```sh
roue convert gif clip.mov --json
```

```json
{"preset": "gif", "jobs": [{"source": "/home/me/clip.mov", "state": "done",
  "outputs": ["/home/me/clip.gif"], "message": "", "input_bytes": 32575,
  "output_bytes": 192263}]}
```

`state` is one of `done`, `failed`, `skipped`, `cancelled`.

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Everything converted (or was skipped). |
| `1` | At least one file failed. |
| `2` | Usage error, like an unknown preset id. |
| `130` | Interrupted with Ctrl+C. Running conversions are stopped and cleaned up. |

## `roue list`

| Option | What it does |
|---|---|
| `--for FILE...` | Only presets that take all these files. |
| `--group GROUP` | Only `image`, `video`, `audio`, `document` or `custom`. |
| `--all` | Include presets turned off in Preferences. |
| `--json` | Machine-readable list, with `accepts`, `rejects` and `available`. |

## `roue info`

```sh
roue info clip.mov
```

```text
clip.mov
  type     video/quicktime (video)
  size     32.6 KB
  length   2.0 s
  video    h264 320x240
  audio    aac
  presets  mp4, gif, webm, share-10mb, share-25mb, compress-video, mute, mp3, opus, wav, flac
```

## `roue doctor`

Lists every tool with its path or "not installed", the presets that can't run
and what they need, the command that installs everything missing, and the state
of the drop panel (GTK), the hotkey and the Files menu.

## `roue history` and `roue undo`

`roue history` shows recent conversions (`-n 20` for more). The last 50 are
kept in `~/.local/state/roue/history.jsonl`.

`roue undo` moves the results of the most recent conversion to the trash. Run
it again to go one step further back. Originals are never touched, and
nothing is deleted: restore from the trash if you change your mind.

## `roue setup`

Hooks Roue into your desktop, for your user only.

| Option | What it does |
|---|---|
| `--binding KEYS` | Hotkey to set, default `<Super><Shift>d`. It runs `roue wheel`. |
| `--no-hotkey` | Don't set the hotkey. |
| `--no-nautilus` | Don't add the Files right-click menu. |
| `--restart-files` | Restart Files so the menu shows up right away. |
| `--remove` | Undo everything `roue setup` did. |

Parts already installed by your package are left alone.

## `roue wheel`

```sh
roue wheel                     # the wheel, as a small window to drop files on
roue wheel a.png b.png         # the wheel at the pointer, for these files
```

Without files, this is what the hotkey runs. It also picks up files you copied
in Files with Ctrl+C. With files, the wheel opens at the pointer showing the
presets that fit them: click a slice to convert, or **More…** for the panel.
See [Desktop integration](desktop-integration.md#the-wheel).

## `roue panel`

```sh
roue panel                     # open the full panel
roue panel a.png b.png         # open it with these files ready ("pick a tile")
roue panel --preferences       # open Preferences
```

## Environment

| Variable | What it does |
|---|---|
| `NO_COLOR` | Turn off colours. |
| `XDG_CONFIG_HOME` | Where `roue/settings.yaml` and `roue/presets/` live (default `~/.config`). |
| `XDG_STATE_HOME` | Where the history lives (default `~/.local/state`). |
| `ROUE_DISABLE_TOOLS` | Pretend tools are missing, like `vips,pandoc`. Handy to test fallbacks. |
