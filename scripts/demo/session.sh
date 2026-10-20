#!/bin/bash
# Runs inside dbus-run-session on the Xvfb display: compositor, window manager,
# wallpaper, Files and Roue (in the background), then the director.
here=$(cd "$(dirname "$0")" && pwd)
export GSK_RENDERER=cairo XCURSOR_THEME=Adwaita XCURSOR_SIZE=24 GTK_A11Y=none NO_AT_BRIDGE=1
export XDG_SESSION_TYPE=x11
picom --config "$here/picom.conf" >/dev/null 2>&1 &
sleep 0.5
xsetroot -cursor_name left_ptr
openbox --config-file "$here/openbox.xml" >"$DEMO_OUT/openbox.log" 2>&1 &
sleep 1
feh --no-fehbg --bg-fill "$DEMO_OUT/wallpaper.png"  # after openbox, or it's wiped
roue setup --no-hotkey >/dev/null 2>&1
# Notifications, styled like GNOME's (needs the icon roue setup installs).
sed "s|@ICONS@|$XDG_DATA_HOME/icons/hicolor/scalable/apps|" "$here/dunstrc" >"$DEMO_OUT/dunstrc"
dunst -config "$DEMO_OUT/dunstrc" >/dev/null 2>&1 &
gsettings set org.gnome.nautilus.preferences default-folder-viewer 'icon-view' 2>/dev/null
nautilus --new-window "$HOME/Pictures" >"$DEMO_OUT/nautilus.log" 2>&1 &
roue gui --gapplication-service >"$DEMO_OUT/roue.log" 2>&1 &
sleep 5
python3 "$here/director.py"
