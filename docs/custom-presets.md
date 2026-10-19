# Custom presets

Presets are data, not code. A preset is a few lines of YAML in
`~/.config/roue/presets/`. Drop a file there, reopen the panel, and your tile
is there, in the Files menu and on the command line too.

**Preferences > Presets > Open presets folder** creates the folder for you,
with a commented example.

## Your first preset

`~/.config/roue/presets/thumbnail.yaml`:

```yaml
id: thumbnail
name: Thumbnail
description: 320 px wide WebP, for blog posts.
group: image
icon: image-x-generic-symbolic
accepts: ["image/*"]
output_ext: webp
suffix: " (thumb)"
backend: image
params:
  width: 320
  quality: 80
```

Check it loaded, then use it:

```sh
roue list --group image
roue thumbnail cover.png      # → cover (thumb).webp
```

If a file has a mistake, Roue keeps working and tells you what's wrong: in
**Preferences > Presets**, and as a warning from every `roue` command.

## One file, several presets

```yaml
presets:
  - id: jpg-small
    name: Small JPG
    accepts: ["image/*"]
    output_ext: jpg
    suffix: " (small)"
    backend: image
    params: { width: 1280, quality: 70 }

  - id: voice-note
    name: Voice note
    accepts: ["audio/*", "video/*"]
    output_ext: opus
    backend: ffmpeg
    params: { video: false, audio_codec: libopus, audio_bitrate: 32k }
```

## Changing a built-in preset

Give your preset the **same id** as a built-in one. Yours wins. For example,
to make GIFs at 24 fps:

```yaml
id: gif
name: GIF
group: video
icon: media-playlist-repeat-symbolic
accepts: ["video/*"]
output_ext: gif
backend: ffmpeg
params: { mode: gif, fps: 24, max_width: 960 }
```

The built-in definitions are in
[`src/roue/presets/`](https://github.com/guilyx/roue/tree/main/src/roue/presets):
copy one as a starting point.

## Keys

| Key | Required | What it does |
|---|---|---|
| `id` | yes | Lowercase letters, digits and dashes, like `video-to-gif`. Used on the command line. |
| `name` | yes | The tile label. Keep it short. |
| `backend` | yes | `image`, `ffmpeg`, `document`, `ghostscript` or `command`. |
| `accepts` | yes | MIME patterns this preset takes: `image/*`, `application/pdf`… |
| `output_ext` | yes | Extension of the result, like `mp4`, or `same` to keep the original's. |
| `description` | no | One line, shown as the tooltip and in menus. |
| `group` | no | `image`, `video`, `audio`, `document`, or `custom` (default). |
| `icon` | no | A symbolic icon name from your icon theme. |
| `rejects` | no | MIME patterns to leave out, like `image/jpeg` for a JPG preset. |
| `suffix` | no | Added to the file name, like `" (small)"`. Needed when `output_ext` is `same`. |
| `output` | no | `file` (default) or `folder` for presets that write several files. |
| `only_if_smaller` | no | `true` throws the result away if it isn't smaller than the original. |
| `keywords` | no | Extra words for the panel's search box. |
| `params` | no | Settings for the backend, see below. |

## Backend parameters

### `image` (libvips, or ImageMagick as a fallback)

| Param | Example | What it does |
|---|---|---|
| `quality` | `85` | Lossy quality, 1–100, for JPG, WebP, AVIF, HEIC. |
| `width` | `1080` | Shrink to this width. Smaller images are left as is. |
| `scale` | `0.5`, `2` | Resize by a factor. SVGs are re-rendered at the new size. |
| `strip` | `true` | Remove metadata (location, camera, dates). The image is rotated upright first. |
| `tool` | `imagemagick` | Force `vips` or `imagemagick`. |

The output format comes from `output_ext`. Transparent areas become white in JPG.

### `ffmpeg` (video and audio)

Set `mode` to pick what happens. The default is `transcode`.

**`transcode`**: re-encode to the output format.

| Param | Example | What it does |
|---|---|---|
| `video` | `false` | Drop the picture: audio-only output (MP3, Opus…). |
| `mute` | `true` | Drop the sound. |
| `video_codec` | `libx264`, `libvpx-vp9`, `copy` | Video encoder. `copy` keeps the picture untouched (instant). |
| `crf` | `23` | Quality for the video encoder: lower is better and bigger. |
| `speed` | `medium`, `fast` | Encoder preset (`-preset`). |
| `max_height` | `720` | Shrink taller videos to this height. |
| `fps` | `30` | Change the frame rate. |
| `pix_fmt` | `yuv420p` | Pixel format (default `yuv420p`, plays everywhere). |
| `audio_codec` | `aac`, `libmp3lame`, `libopus`, `flac` | Audio encoder. |
| `audio_bitrate` | `128k` | Audio bitrate. |
| `audio_quality` | `2` | Variable-quality audio (`-q:a`), used instead of the bitrate. |
| `sample_rate` | `48000` | Audio sample rate. |
| `normalize` | `true` | Even out loudness (EBU R128, −16 LUFS). |
| `extra_args` | `["-tune", "film"]` | Extra FFmpeg arguments, added before the output. |

**`gif`**: palette-optimised looping GIF.

| Param | Default | What it does |
|---|---|---|
| `fps` | `15` | Frames per second. |
| `max_width` | `720` | Shrink wider videos to this width. |

**`target-size`**: two-pass H.264 encode that fits a size.

| Param | Default | What it does |
|---|---|---|
| `target_size_mb` | required | Size limit, in MB (1 MB = 1,000,000 bytes). |
| `max_height` | `720` | Shrink taller videos to this height. |
| `audio_kbps` | `96` | Audio bitrate. Lowered to 48 kbps for long videos. |
| `max_video_kbps` | `2500` (≤ 720p) or `5000` | Short clips don't need more than this. |
| `speed` | `medium` | Encoder preset. |

If a video is too long to fit, Roue says how big it would need to be, instead
of producing something unwatchable.

### `document` (LibreOffice and Pandoc)

No params: the output format is `output_ext` (`pdf`, `docx`, `html`, `odt`…).
Office files go through LibreOffice. Markdown, reStructuredText, Org, plain
text and HTML go through Pandoc.

### `ghostscript` (PDFs)

| Param | Example | What it does |
|---|---|---|
| `mode` | `compress`, `images`, `text` | What to do with the PDF. |
| `quality` | `screen`, `ebook`, `printer`, `prepress` | For `compress`: lower is smaller. Default `ebook`. |
| `dpi` | `150` | For `images`: resolution of each page. Use with `output: folder` and `output_ext: png` or `jpg`. |

### `command` (anything else)

Run any program. `params.command` is a list of words (or a single string,
split like a shell would). These placeholders are filled in:

| Placeholder | Value |
|---|---|
| `{in}` | The input file. |
| `{out}` | The file to write. Roue moves it next to the original afterwards. |
| `{outdir}` | A folder to write into, for presets with `output: folder`. |
| `{stem}` | The input file name without its extension. |

No shell is involved, so file names with spaces or quotes are safe and need
no quoting.

```yaml
id: ocr-pdf
name: Searchable PDF
description: Add a text layer to scanned PDFs.
group: document
accepts: ["application/pdf"]
output_ext: pdf
suffix: " (ocr)"
backend: command
params:
  command: ["ocrmypdf", "--skip-text", "{in}", "{out}"]
```

```yaml
id: split-audio
name: Split in 10 min
group: audio
accepts: ["audio/*"]
output_ext: mp3
output: folder
suffix: " (parts)"
backend: command
params:
  command: ["ffmpeg", "-i", "{in}", "-f", "segment", "-segment_time", "600",
            "-c", "copy", "{outdir}/part-%03d.mp3"]
```

The command must exit with status 0 and write a non-empty `{out}` (or at
least one file in `{outdir}`). If it fails, Roue shows "The command for
'Searchable PDF' failed." and keeps the tool's output for
`roue convert --verbose`.

## Sharing presets

A preset is a plain file: share it as a gist, or open a pull request to add it
to the built-ins. See [Contributing](contributing.md).
