# Getting started

Five minutes from zero to your first conversion. You'll use all three ways in:
the wheel (with the hotkey), the Files right-click menu, and the terminal.

## 1. Install

On Ubuntu 24.04+ or Debian 13+, one command installs Roue and keeps it up
to date through Software Updater:

```sh
wget -qO- https://guilyx.github.io/roue/install.sh | sh
```

It also runs `roue setup`, which adds the **Super+Shift+D** hotkey (it opens
the wheel). The app launcher and the Files menu come with the package. The
first time you open Roue, **Set Up Roue** shows anything left to do.

On another distribution, see [Install](install.md). Then check everything is
in place:

```sh
roue doctor
```

`roue doctor` lists each conversion tool with a ✓ or ✗, how many presets are
ready, and the exact command to install what's missing.

## 2. Your first drop

1. Press **Super+Shift+D**. The wheel opens: a ring of slices, one per preset,
   with a starter set (JPG, WebP, MP4, GIF, Under 10 MB, MP3, PDF) and
   **More…**.
2. Drag a file from Files (or your desktop) over the wheel. The slices change
   to the presets that fit that file, best first: a photo gets JPG, PNG, WebP…
3. Drop it on a slice, say **JPG**. The wheel closes and the conversion runs.
4. The result appears **next to the original**: `IMG_2041.HEIC` gives
   `IMG_2041.jpg`. A notification says when it's done, with **Open** and
   **Show in Folder** buttons.

Press **Esc** to put the wheel away. Roue stays ready in the background, so
the next **Super+Shift+D** is instant.

### No room to drag? Copy instead

On Wayland, when Files is maximised, it covers the wheel as soon as you click
it. Copying is faster anyway:

1. Select files in Files and press **Ctrl+C**.
2. Press **Super+Shift+D**. The wheel picks up the copied files and shows the
   presets that fit them.
3. Click a slice. Done.

Copied files are used once: the next time you press the hotkey, the wheel
starts empty again. Press **Ctrl+V** in the wheel to use the clipboard again.

The wheel works from the keyboard too: the arrow keys or **Tab** move between
slices, **Enter** picks one, **1**–**8** pick a slice directly, **Esc** closes.

### Every preset: More…

The wheel shows up to seven presets, the ones that fit your files best. The
last slice, **More…**, opens the full panel with every preset, grouped into
Images, Video, Audio and Documents, with your files ready to go. In the panel
you can type to search presets, then press **Enter** to run the first match.

### On X11: Shift-drag

On an X11 session, hold **Shift** while dragging any file. The wheel springs
open around the pointer. Release Shift, then drop on a slice, or let go
anywhere else to put it away.

## 3. Right-click in Files

Select one or more files in Files, right-click, and choose
**Convert with Roue…**. The wheel opens right at the pointer, with the presets
that fit *all* selected files, the most relevant first. Click a slice; click
outside the wheel (or press **Esc**) to cancel.

Select 40 photos, pick **WebP**, and you get one notification at the end:
"WebP: 40 files converted · 212.0 MB saved".

If the menu item doesn't show up, restart Files once:

```sh
nautilus -q
```

## 4. The command line

The same presets, from a terminal or a script:

```sh
roue list                       # every preset, grouped
roue list --for clip.mov        # only the ones that fit this file
roue convert gif clip.mov       # convert
roue gif clip.mov               # same thing, shorter
roue share-10mb *.mp4 -o ~/out  # many files, results in another folder
```

Each finished file prints one line:

```text
✓ clip.mov → clip.gif (192.3 KB)
✗ silent.mp4: This video has no audio track to extract.
```

Made a mistake? Move the results of the last conversion to the trash:

```sh
roue undo
```

## Where to next

- Browse the [presets](presets.md).
- Make [your own preset](custom-presets.md) in five lines of YAML.
- Tune Roue in **Preferences** (the panel's main menu, or `roue panel --preferences`).
