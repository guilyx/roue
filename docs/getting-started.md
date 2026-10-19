# Getting started

Five minutes from zero to your first conversion. You'll use all three ways in:
the drop panel, the Files right-click menu, and the terminal.

## 1. Install

On Ubuntu or Debian, grab `roue_0.1.0_all.deb` from the
[latest release](https://github.com/guilyx/roue/releases/latest), then:

```sh
sudo apt install ./roue_0.1.0_all.deb
roue setup
```

`roue setup` adds the **Super+Shift+D** hotkey. The app launcher and the Files
menu come with the package.

On another distribution, see [Install](install.md). Then check everything is
in place:

```sh
roue doctor
```

`roue doctor` lists each conversion tool with a ✓ or ✗, how many presets are
ready, and the exact command to install what's missing.

## 2. Your first drop

1. Press **Super+Shift+D**. The drop panel opens, with tiles grouped into
   Images, Video, Audio and Documents.
2. Drag a file from Files (or your desktop) onto the panel.
   Tiles that can't take that file fade out.
3. Drop it on a tile, say **JPG**. A ring fills while it works.
4. The result appears **next to the original**: `IMG_2041.HEIC` gives
   `IMG_2041.jpg`. A toast offers **Show** to open the folder.

Press **Esc** to hide the panel. Roue stays ready in the background, so the
next **Super+Shift+D** is instant.

### No room to drag? Copy instead

On Wayland, when Files is maximised, it covers the panel as soon as you click
it. Copying is faster anyway:

1. Select files in Files and press **Ctrl+C**.
2. Press **Super+Shift+D**. The panel picks up the copied files:
   "Copied: IMG_2041.HEIC · pick a tile".
3. Click a tile. Done.

You can also type to search presets, then press **Enter** to run the first
match: **Ctrl+C**, **Super+Shift+D**, type `gif`, **Enter**.

### On X11: Shift-drag

On an X11 session, hold **Shift** while dragging any file. The panel pops up
next to the pointer. Release Shift, then drop on a tile, or let go anywhere
else to dismiss it.

## 3. Right-click in Files

Select one or more files in Files, right-click, and open **Convert to…**.
The menu lists the presets that fit *all* selected files, the most relevant
first. **More…** opens the panel with those files ready to go.

Select 40 photos, pick **WebP**, and you get one notification at the end:
"WebP: 40 files converted · 212.0 MB saved".

If the menu doesn't show up, restart Files once:

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
- Tune the panel in **Preferences** (main menu, or `roue panel --preferences`).
