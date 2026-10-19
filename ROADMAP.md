# Roadmap

Roue's goal: **converting a file on Linux should take one drop.** Hold a key,
drop a file on a tile, done. No dialogs, no editors, no uploads.

What we won't build: full editors (timelines, image canvases), cloud
features, accounts or telemetry. Everything stays local.

Want something here sooner? 👍 the matching issue, or open a
[preset request](https://github.com/guilyx/roue/issues/new?template=preset_request.yml).

## ✅ 0.1 — first release

- [x] Engine with no GTK: presets as YAML, parallel job queue, cancellation,
      progress from FFmpeg and Ghostscript, plain-English errors
- [x] Never overwrite: free names (`photo (2).jpg`), hidden scratch folders,
      Downloads fallback for read-only folders
- [x] 27 presets across images, video, audio and documents (HEIC → JPG,
      under 10/25 MB, video → GIF, office → PDF, strip metadata...)
- [x] Drop panel (GTK 4 + libadwaita): grouped tiles, dims tiles that don't
      fit, progress rings, search, copied-files staging, toasts, notifications
- [x] Hotkey (GNOME custom shortcut, `roue setup`), X11 Shift-drag
- [x] Files (Nautilus) right-click "Convert to…", routed through the app
- [x] CLI: `convert`, shorthand, `list`, `info`, `doctor`, `history`, `undo`
- [x] Custom presets, including raw commands with `{in}` / `{out}`
- [x] Preferences: hotkey, output folder, notifications, parallel jobs,
      preset toggles, tools check
- [x] `.deb`, AppStream metadata, man page, CI, website and docs

## 🚧 1.0 — public launch

**Conversions**

- [ ] Hardware video encoding when available (VAAPI, NVENC), software fallback
- [ ] Trim: a tiny start/end dialog, the one preset that opens a window
- [ ] Remove background (optional model download, runs offline after)
- [ ] OCR for PDFs without a text layer (Tesseract)
- [ ] Merge PDFs and images → one PDF (multi-file drops into one result)
- [ ] Favicon / app icon set from one image

**Panel and desktop**

- [ ] First-run onboarding: what it does, set your hotkey, try it on a sample
- [ ] Tray icon (Ayatana AppIndicator): open panel, recent, preferences
- [ ] XDG GlobalShortcuts portal for the hotkey (KDE, newer GNOME)
- [ ] Pin mode: keep the panel as a small shelf docked to a screen edge
- [ ] Recent conversions with re-run

**Packaging**

- [ ] Flatpak and Flathub listing
- [ ] AppImage
- [ ] PPA / apt repository

## 🔭 Later

- [ ] GNOME Shell extension for Shift-drag on Wayland (extensions can see drags)
- [ ] Nemo, Dolphin and Thunar menus
- [ ] Preset import/export and a community preset gallery
- [ ] Per-preset output rules (fixed folder, replace original with trash backup)
- [ ] Panel under the pointer on Wayland, if compositors ever allow it

## Success metrics

| What | Target |
|---|---|
| Hotkey → panel visible | < 150 ms with Roue running in the background |
| Image conversion | < 1 s for a typical photo |
| First conversion for a new user | < 60 s from install |
| Data loss bugs | Zero. Never overwrite, never delete without the trash |
