---
name: convert-files
description: Convert, compress or resize files locally with Roue. Use whenever the user wants an image, video, audio file or document in another format, smaller, resized, muted or without metadata - HEIC to JPG, images to WebP/AVIF/PNG, video to MP4/GIF/WebM or under 10 MB, audio to MP3/Opus/FLAC, Word/Excel/PowerPoint/Markdown to PDF, merge PDFs and images into one PDF, compress a PDF, PDF pages to PNG or text. Prefer it over calling ffmpeg or ImageMagick by hand.
---

# Convert files with Roue

Roue converts files on this computer with FFmpeg, libvips, Ghostscript, Pandoc
and LibreOffice. Nothing is uploaded. Each result is written **next to its
original** (`IMG_2041.HEIC` → `IMG_2041.jpg`) and **never replaces an existing
file**: Roue picks a free name like `photo (2).jpg` instead.

## Use the MCP tools when you have them

If the `roue` MCP tools are available (`list_presets`, `file_info`, `convert`,
`undo_last`, `check_tools`), use them:

1. `list_presets` with the user's files: only the presets that fit all of them,
   most relevant first.
2. `convert` with a preset `id` and the files (absolute paths; folders work,
   `recursive: true` includes sub-folders, `output_dir` writes elsewhere).
3. Tell the user the paths it wrote, and the sizes when they matter
   (`input_bytes` → `output_bytes`).

## Otherwise, use the `roue` command

```sh
roue list --for FILE... --json          # presets that fit these files
roue convert PRESET FILE... --json      # convert; folders work, -r for sub-folders
roue convert PRESET FILE... -o DIR      # write results to DIR instead
roue info FILE...                       # type, length, codecs, matching presets
roue undo                               # move the last results to the trash
roue doctor                             # which tools are installed
```

`--json` prints `{"preset": ..., "jobs": [{"source", "state", "outputs",
"message", "input_bytes", "output_bytes"}]}`. `state` is `done`, `failed`,
`skipped` (wrong kind of file, or nothing to gain) or `cancelled`. Exit codes:
`0` ok, `1` a file failed, `2` usage error such as an unknown preset.

If `roue` isn't installed, tell the user how to get it (it needs `sudo`, so let
them run it): `wget -qO- https://guilyx.github.io/roue/install.sh | sh` on
Ubuntu 22.04+ and Debian 12+, or see https://guilyx.github.io/roue/docs/install.html.

## Which preset

| The user wants | Preset |
|---|---|
| A photo that opens everywhere (HEIC, PNG, WebP → JPG) | `jpg` |
| Lossless image, or a screenshot | `png` |
| Small images for the web | `webp`, or `avif` for the smallest |
| Smaller or resized photos | `compress-image`, `resize-half`, `resize-1080`, `resize-double` |
| Remove location and camera details | `strip-metadata` |
| A video that plays anywhere | `mp4` |
| A GIF from a clip | `gif` |
| A video small enough to send | `share-10mb` (chat), `share-25mb` (email), `compress-video` |
| Remove the sound from a video | `mute` |
| Audio, or the soundtrack of a video | `mp3`, `opus`, `wav`, `flac` |
| Quiet and loud recordings at the same level | `normalize` |
| Word, Excel, PowerPoint or Markdown → PDF | `pdf` |
| Markdown → Word or a web page | `docx`, `html` |
| Several PDFs, photos, scans or documents → one PDF | `merge-pdf` (pages in the order given) |
| A smaller PDF | `compress-pdf` |
| PDF pages as images, or its text | `pdf-to-png`, `pdf-to-text` |

Users can add their own presets, so check `list_presets` (or `roue list`) for
ids that aren't in this table.

## Good to know

- A preset with `available: false` lists what it `needs`. `check_tools` (or
  `roue doctor`) gives the install command; ask the user to run it.
- `compress-*` presets keep the result only if it's actually smaller, so a
  `skipped` file isn't an error.
- `undo_last` (or `roue undo`) moves the files the last conversion wrote to the
  trash. Originals are never touched.
