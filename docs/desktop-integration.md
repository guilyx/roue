# Desktop integration

Roue has three front doors: the **wheel** (opened by the hotkey, by Shift-drag
on X11, or from the Files menu), the **Files right-click menu**, and the
**command line**. This page covers how they plug into your desktop.

## The wheel

The wheel is a ring of slices, one per preset. It shows up to seven presets
that fit your files best, most relevant first, and a last slice, **More…**,
that opens the full panel with every preset.

It comes in two forms:

- **At the pointer**, over a lightly dimmed screen, when Roue already knows
  the files: **Convert with Roue…** in Files, or Shift-drag on X11. Click a
  slice to convert. Click outside the wheel, press **Esc**, or switch to
  another window to cancel.
- **As a small round window** you drop files onto, when you press the hotkey.
  It starts with a handful of popular presets and re-arranges itself to fit
  the file you drag over it. Files you copied with **Ctrl+C** are picked up
  when it opens (once per copy), and **Ctrl+V** reads the clipboard again.
  Click a slice with no files to pick some with a file chooser.

After you pick a slice, the wheel closes and the conversion runs in the
background. A notification says when it's done.

| Key | Action |
|---|---|
| Arrows, Tab | Move between slices |
| Enter, Space | Pick the highlighted slice |
| 1–8 | Pick a slice directly (1 is the top one, then clockwise) |
| Ctrl+V | Use copied files |
| Esc | Close the wheel |

On Wayland, the wheel at the pointer sits on a see-through layer that covers
the screen: the desktop doesn't let apps place windows, but it does tell a
window under the pointer where the pointer is. GNOME paints black behind
full-screen windows, so on Wayland that layer is a maximised window (the top
bar and the dock stay visible). It closes as soon as another window takes
focus, so it never lingers invisibly over your desktop.

On X11 the hotkey's wheel opens centred on the pointer and stays on top. On
GNOME's Wayland session the [GNOME helper](#the-gnome-helper) does the same;
on other Wayland desktops the desktop decides where it goes.

## The GNOME helper

Wayland apps can't keep a window above the others, or open it at the
pointer. On GNOME, a small Shell extension does both for Roue's wheel:

- the hotkey's wheel opens centred on the pointer;
- the wheel stays above the window you drag from (otherwise clicking a file
  in a maximised Files window would hide it).

It touches only Roue's wheel window, nothing else. Its id is
`roue@guilyx.github.io`. The `.deb` installs it; `roue setup`, **Set Up
Roue** or **Preferences > General** turn it on. GNOME 42–44 (Ubuntu 22.04,
Debian 12) need an older extension format: there, turning it on also puts a
copy in that format in `~/.local/share/gnome-shell/extensions/`. GNOME only
discovers new extensions when your session starts, so after a fresh install it
starts the next time you log in.

Without it Roue still works: the wheel opens where GNOME puts new windows, and
**Ctrl+C**, then the hotkey, avoids dragging altogether. Turn it off in
**Preferences > General** or in GNOME's Extensions app.

## The hotkey

**Super+Shift+D** opens the wheel.

Wayland doesn't let apps grab keys for themselves, so Roue registers an
ordinary custom shortcut, exactly like the ones you'd create in Settings, that
runs `roue wheel`.

### GNOME (and Ubuntu, Pop!_OS)

`roue setup` sets it for you. Pick another combination with:

```sh
roue setup --binding '<Super><Alt>c'
```

You'll find it in **Settings > Keyboard > Keyboard Shortcuts > Custom
Shortcuts** as "Roue: open the wheel". Turn it on or off from
**Preferences > General** in Roue.

### KDE Plasma

**System Settings > Shortcuts > Add New > Command or Script**. Command:
`roue wheel`. Shortcut: **Meta+Shift+D**.

### Xfce

**Settings > Keyboard > Application Shortcuts > Add**. Command: `roue wheel`.

### Cinnamon, MATE, others

Add a custom shortcut running `roue wheel` in your keyboard settings.
`roue setup` prints these instructions when it can't set the key itself.

Prefer the full panel? Point the shortcut at `roue panel` instead.

## The panel

The full panel shows every preset as a tile, grouped into Images, Video, Audio
and Documents. Open it with the wheel's **More…** slice, from the app
launcher, or with `roue panel`.

- **Drop** files on a tile. Tiles that can't take them fade out while you drag.
- **Copy, then open**: files you copied in Files (Ctrl+C) are picked up when
  the panel opens. Click a tile to convert them. **Ctrl+V** pastes them again.
- **Click** a tile with nothing staged to pick files with a file chooser.
- **Type** to search ("discord", "gps", "gif"…). **Enter** runs the first match.
- **Esc** hides the panel. Conversions keep going; a notification tells you
  when they're done.

| Shortcut | Action |
|---|---|
| Ctrl+O | Choose files |
| Ctrl+V | Use copied files |
| Ctrl+F | Search presets |
| Enter | Run the first matching preset |
| Esc, Ctrl+W | Hide the panel |

### Why the drop targets don't close when you click elsewhere

On Wayland, starting a drag in Files gives Files the focus. If the hotkey's
wheel, or the panel, closed when it lost focus, it would vanish exactly when
you need it. So it stays open until you press **Esc**, drop something, or
close it.

### Dragging onto a covered window (GNOME)

With the [GNOME helper](#the-gnome-helper) on, the wheel stays on top, so this
doesn't happen to it. If a maximised window covers the panel, start dragging
your file, press **Super** to open the Activities overview, hover the Roue
window until it comes forward, then drop. Or skip the drag: **Ctrl+C**,
**Super+Shift+D**, click a slice.

### Staying in the background

After the first open, Roue keeps running quietly so the hotkey shows the wheel
instantly. Turn this off in **Preferences > General > Stay in the background**,
or stop it any time with `roue quit` (or **Quit** in the panel's main menu).

## Shift-drag (X11 only)

On an X11 session, hold **Shift** while dragging any file, from any app. The
wheel springs open around the pointer, with the presets that fit that file.
**Release Shift**, then drop on a slice; let go anywhere else and it goes away
again.

Why release Shift? To file managers, Shift means "move this file". Roue only
ever copies, so it refuses a drop while Shift is held instead of letting the
source app think the file was moved. The middle of the wheel says
"Release Shift to drop" until you do.

It works by noticing when a drag starts on the X server, so it needs
`python3-xlib` (pulled in by the `.deb`). Turn it off in
**Preferences > General > Shift-drag**.

Wayland keeps each app's drags private by design, so no app can see a drag
start elsewhere. There, use the Files menu or the hotkey. GNOME 49 and newer
(Ubuntu 25.10, 26.04) have no X11 session at all, so Shift-drag is for X11
sessions of Xfce, MATE, Cinnamon and the like.

## Files (Nautilus) right-click menu

Right-click files and choose **Convert with Roue…**. The wheel opens at the
pointer with the presets that fit every selected file, most relevant first.
The item only appears when at least one preset fits.

- Needs the Nautilus Python extension host: `python3-nautilus` on
  Debian/Ubuntu, `nautilus-python` on Fedora, `python-nautilus` on Arch.
- The `.deb` installs the extension system-wide. Otherwise `roue setup` adds it
  to `~/.local/share/nautilus-python/extensions/`.
- Works with all three Files extension APIs: 3.0 (Nautilus 42, Ubuntu 22.04),
  4.0 (Nautilus 43–48, Ubuntu 24.04) and 4.1 (Nautilus 49+, Ubuntu 25.10 and 26.04).
- Restart Files once to load it: `nautilus -q`, or the **Restart Files**
  button in **Set Up Roue**. Files' open windows close.
- Folders and remote locations without a local path don't get the menu.

The menu asks the Roue app (over D-Bus, starting it if needed) to show the
wheel, so the wheel, progress and notifications all come from one place. It
passes along an activation token so the desktop lets the wheel come to the
front. If the app can't be reached, the menu runs `roue wheel` instead.

Nemo, Dolphin and Thunar menus are on the [roadmap](https://github.com/guilyx/roue/blob/main/ROADMAP.md).

## Notifications

When a conversion finishes and the panel isn't in front (always the case
after the wheel), you get a desktop notification with **Open** and
**Show in Folder**. Clicking it shows the result in Files. Roue passes on the
activation token GNOME sends with the click, so the app it opens is allowed to
come to the front. Turn notifications off in **Preferences > Results**.

## D-Bus

Roue is a single-instance app with the id `io.github.guilyx.Roue`. The
`.deb` (or `roue setup`) installs a D-Bus service file, so calling it starts
the app when it isn't running.

Actions you can trigger from scripts:

| Action | Parameter | What it does |
|---|---|---|
| `show-wheel` | none | Open the wheel to drop files on (what the hotkey does). |
| `wheel-files` | `as` (paths) | Open the wheel at the pointer for these files. |
| `show-panel` | none | Open the full panel. |
| `stage-files` | `as` (paths) | Open the panel with these files ready. |
| `run-preset` | `(sas)` (preset id, paths) | Convert files in the background. |
| `quit` | none | Stop Roue. |

```sh
gdbus call --session --dest io.github.guilyx.Roue \
  --object-path /io/github/guilyx/Roue \
  --method org.gtk.Actions.Activate \
  run-preset "[<('jpg', ['/home/me/IMG_2041.HEIC'])>]" "{}"
```

## Files Roue installs

| File | Purpose |
|---|---|
| `applications/io.github.guilyx.Roue.desktop` | App launcher |
| `dbus-1/services/io.github.guilyx.Roue.service` | Start on demand over D-Bus |
| `icons/hicolor/scalable/apps/io.github.guilyx.Roue.svg` | Icon |
| `nautilus-python/extensions/roue_nautilus.py` | Files menu |
| `gnome-shell/extensions/roue@guilyx.github.io/` | GNOME helper |

They live under `/usr/share` with the `.deb`, or under `~/.local/share` with
`roue setup`. `roue setup --remove` deletes the ones it added, turns the GNOME
helper off and removes the hotkey.

The `.deb` also adds Roue's update channel,
`/etc/apt/sources.list.d/roue.sources`, with its key in
`/usr/share/keyrings/roue-archive-keyring.gpg`. See
[Updates](install.md#updates).
