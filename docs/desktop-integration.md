# Desktop integration

Roue has three front doors: the **drop panel**, the **Files right-click
menu**, and the **command line**. This page covers how the first two plug into
your desktop.

## The hotkey

The panel opens with **Super+Shift+D**.

Wayland doesn't let apps grab keys for themselves, so Roue registers an
ordinary custom shortcut, exactly like the ones you'd create in Settings, that
runs `roue panel`.

### GNOME (and Ubuntu, Pop!_OS)

`roue setup` sets it for you. Pick another combination with:

```sh
roue setup --binding '<Super><Alt>c'
```

You'll find it in **Settings > Keyboard > Keyboard Shortcuts > Custom
Shortcuts** as "Roue: open drop panel". Turn it on or off from
**Preferences > General** in Roue.

### KDE Plasma

**System Settings > Shortcuts > Add New > Command or Script**. Command:
`roue panel`. Shortcut: **Meta+Shift+D**.

### Xfce

**Settings > Keyboard > Application Shortcuts > Add**. Command: `roue panel`.

### Cinnamon, MATE, others

Add a custom shortcut running `roue panel` in your keyboard settings.
`roue setup` prints these instructions when it can't set the key itself.

## The panel

- **Drop** files on a tile. Tiles that can't take them fade out while you drag.
- **Copy, then open**: files you copied in Files (Ctrl+C) are picked up when
  the panel opens. Click a tile to convert them. **Ctrl+V** pastes them again.
- **Click** a tile with nothing staged to pick files with a file chooser.
- **Type** to search ("discord", "gps", "gif"…). **Enter** runs the first match.
- **Esc** hides the panel. Conversions keep going; a notification tells you
  when they're done.

| Shortcut | Action |
|---|---|
| Super+Shift+D | Open the panel |
| Ctrl+O | Choose files |
| Ctrl+V | Use copied files |
| Ctrl+F | Search presets |
| Enter | Run the first matching preset |
| Esc, Ctrl+W | Hide the panel |

### Why the panel doesn't close when you click elsewhere

On Wayland, starting a drag in Files gives Files the focus. If the panel
closed when it lost focus, it would vanish exactly when you need it. So it
stays open until you press **Esc**, drop something, or close it.

### Dragging onto a covered panel (GNOME)

If a maximised window covers the panel, start dragging your file, press
**Super** to open the Activities overview, hover the Roue window until it comes
forward, then drop. Or skip the drag: **Ctrl+C**, **Super+Shift+D**, click.

### Staying in the background

After the first open, Roue keeps running quietly so the hotkey shows the panel
instantly. Turn this off in **Preferences > General > Stay in the background**,
or stop it any time with `roue quit` (or **Quit** in the main menu).

## Shift-drag (X11 only)

On an X11 session, hold **Shift** while dragging any file, from any app. The
panel pops up next to the pointer and stays on top. Drop on a tile; let go
anywhere else and it hides again.

It works by noticing when a drag starts on the X server, so it needs
`python3-xlib` (pulled in by the `.deb`). Turn it off in
**Preferences > General > Shift-drag**.

Wayland keeps each app's drags private by design, so no app can see a drag
start elsewhere. There, use the hotkey or the Files menu.

## Files (Nautilus) right-click menu

Right-click files and open **Convert to…**. You get up to six presets that fit
every selected file, most relevant first, and **More…** to open the panel with
those files ready.

- Needs the Nautilus Python extension host: `python3-nautilus` on
  Debian/Ubuntu, `nautilus-python` on Fedora, `python-nautilus` on Arch.
- The `.deb` installs the extension system-wide. Otherwise `roue setup` adds it
  to `~/.local/share/nautilus-python/extensions/`.
- Restart Files once to load it: `nautilus -q`.
- Folders and remote locations without a local path don't get the menu.

Conversions started from the menu run inside the Roue app, so progress and
notifications match the panel. If the app can't start, the menu falls back to
`roue convert --notify`.

Nemo, Dolphin and Thunar menus are on the [roadmap](https://github.com/guilyx/roue/blob/main/ROADMAP.md).

## Notifications

When a conversion finishes and the panel isn't in front, you get a desktop
notification with **Open** and **Show in folder**. Turn them off in
**Preferences > Results**.

## D-Bus

Roue is a single-instance app with the id `io.github.guilyx.Roue`. The
`.deb` (or `roue setup`) installs a D-Bus service file, so calling it starts
the app when it isn't running.

Actions you can trigger from scripts:

| Action | Parameter | What it does |
|---|---|---|
| `show-panel` | none | Open the panel. |
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

They live under `/usr/share` with the `.deb`, or under `~/.local/share` with
`roue setup`. `roue setup --remove` deletes the ones it added.
