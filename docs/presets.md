# Presets

A preset is one tile in the panel, one entry in the Files menu, and one id on
the command line. Roue ships with the presets below. You can turn any of them
off in **Preferences > Presets**, change them, or [add your own](custom-presets.md).

Run `roue list` to see them on your machine, or `roue list --for FILE` to see
the ones that fit a file.

## Built-in presets

<!-- presets:start -->
### Images

| Id | Name | Takes | Gives | What it does |
|---|---|---|---|---|
| `jpg` | JPG | any image except JPG | `.jpg` | Photos that open everywhere. Transparent areas become white. |
| `png` | PNG | any image except PNG | `.png` | Lossless, keeps transparency. Good for screenshots and graphics. |
| `webp` | WebP | any image except WebP, SVG | `.webp` | Small files for the web, with transparency. |
| `avif` | AVIF | any image except AVIF, SVG | `.avif` | Next-generation format, the smallest files at the same quality. |
| `resize-half` | Half size | any image except SVG, GIF | same format, ` (50%)` | Scale the image down to 50%. |
| `resize-1080` | 1080 px wide | any image except SVG, GIF | same format, ` (1080px)` | Shrink wide images to 1080 pixels across. Smaller images are left as is. |
| `resize-double` | Double size | any image except GIF | `.png`, ` (2x)` | Scale up to 200%. Vector images are re-rendered sharp. |
| `compress-image` | Compress | any image except SVG, GIF | `.jpg`, ` (compressed)`, only if smaller | Smaller JPG at quality 75. Kept only if it's actually smaller. |
| `strip-metadata` | Remove metadata | JPG, PNG, WebP, HEIC, HEIF, AVIF, TIFF | same format, ` (clean)` | Drop location, camera and date details before sharing. |

### Video

| Id | Name | Takes | Gives | What it does |
|---|---|---|---|---|
| `mp4` | MP4 | any video | `.mp4` | H.264 + AAC, plays on every phone, browser and chat app. |
| `gif` | GIF | any video | `.gif` | Looping GIF at 15 fps, up to 720 px wide. Great for READMEs. |
| `webm` | WebM | any video except WebM | `.webm` | VP9 + Opus, open formats for the web. |
| `share-10mb` | Under 10 MB | any video | `.mp4`, ` (10MB)` | Fits free chat upload limits (Discord). Sized with a two-pass encode. |
| `share-25mb` | Under 25 MB | any video | `.mp4`, ` (25MB)` | Fits most email attachment limits. |
| `compress-video` | Smaller video | any video | `.mp4`, ` (small)`, only if smaller | 720p H.264 at a lower bitrate. Kept only if it's actually smaller. |
| `mute` | Mute | any video | same format, ` (muted)` | Remove the sound. The picture is copied untouched, so it's instant. |

### Audio

| Id | Name | Takes | Gives | What it does |
|---|---|---|---|---|
| `mp3` | MP3 | any audio, any video except MP3 | `.mp3` | Plays anywhere. Also pulls the soundtrack out of a video. |
| `opus` | Opus | any audio, any video | `.opus` | Tiny files that keep voices clear. Ideal for voice notes and podcasts. |
| `wav` | WAV | any audio, any video except WAV | `.wav` | Uncompressed audio for editors and samplers. |
| `flac` | FLAC | any audio, any video except FLAC | `.flac` | Lossless and smaller than WAV. |
| `normalize` | Even out volume | any audio | same format, ` (normalized)` | Normalise loudness (EBU R128) so quiet and loud recordings match. |

### Documents

| Id | Name | Takes | Gives | What it does |
|---|---|---|---|---|
| `pdf` | PDF | DOC, RTF, old Office files, DOCX/XLSX/PPTX, OpenDocument, Markdown, reStructuredText, Org, plain text, CSV | `.pdf` | Word, Excel, PowerPoint, LibreOffice and Markdown files to PDF. |
| `docx` | Word | ODT, RTF, DOC, Markdown, reStructuredText, Org, HTML | `.docx` | Markdown, OpenDocument and RTF to .docx. |
| `html` | Web page | Markdown, reStructuredText, Org | `.html` | Markdown to a single self-contained HTML file. |
| `compress-pdf` | Compress PDF | PDF | `.pdf`, ` (compressed)`, only if smaller | Shrink scans and image-heavy PDFs for email. Kept only if smaller. |
| `pdf-to-png` | Pages to PNG | PDF | folder of `.png`, ` (pages)` | One PNG image per page, in a new folder. |
| `pdf-to-text` | Text | PDF | `.txt` | Pull the text out of a PDF (no OCR yet). |
<!-- presets:end -->

## How a preset decides what it takes

Each preset lists MIME patterns it **accepts**, like `image/*`, and some it
**rejects**, like `image/jpeg` for the JPG preset (converting a JPG to JPG
would be pointless).

- Roue works out a file's type from its extension first, then from its
  content when the extension is unknown.
- When you drop several files, a tile lights up only if it takes **all** of them.
  In the Files menu, the same rule picks which presets to list.
- Presets for the file's own kind come first: a video lists video presets
  before the audio ones that can extract its soundtrack.
- If a drop mixes kinds, files the preset can't take are **skipped** with a
  note, and the rest are converted.

## Where results go

Results land **next to the original**, named after it:

- A different format keeps the name: `IMG_2041.HEIC` → `IMG_2041.jpg`.
- A same-format preset adds a **suffix**: `photo.png` → `photo (50%).png`.
- If the name is taken, Roue counts up: `photo (2).jpg`, `photo (3).jpg`…
  Nothing is ever overwritten.
- **Folder presets** (like Pages to PNG) create a new folder:
  `report (pages)/page-001.png`.
- If the original's folder is read-only (a camera, a mounted disk image),
  results go to your **Downloads** folder instead, and Roue says so.
- You can send every result to one folder in **Preferences > Results**, or with
  `roue convert -o FOLDER`.

## "Only if smaller"

Compression presets are marked **only if smaller**. If the result isn't
smaller than the original, Roue throws it away and tells you the original was
kept. You never end up with a "compressed" file that's bigger.

## Turning presets off

**Preferences > Presets** has a switch for every preset. Turned-off presets
disappear from the panel and the Files menu. They still work from the command
line, and `roue list --all` shows them.

The same list lives in `~/.config/roue/settings.yaml`:

```yaml
disabled_presets:
  - webm
  - pdf-to-text
```
