#!/bin/sh
# Install Roue on Ubuntu or Debian:
#
#   wget -qO- https://guilyx.github.io/roue/install.sh | sh
#
# Adds Roue's signed update channel (so Software Updater keeps Roue up to
# date), installs the roue package with apt, then sets up the hotkey and the
# Files menu for you. Read it first if you like: it only touches
# /etc/apt/sources.list.d/roue.sources and /usr/share/keyrings/roue-archive-keyring.gpg
# besides what apt installs.
set -eu

SITE="https://guilyx.github.io/roue"
SOURCES=/etc/apt/sources.list.d/roue.sources
KEYRING=/usr/share/keyrings/roue-archive-keyring.gpg

say() { printf '\033[1m%s\033[0m\n' "$*"; }
fail() { printf 'roue install: %s\n' "$*" >&2; exit 1; }

[ "$(uname -s)" = Linux ] || fail "Roue runs on Linux."
command -v apt-get >/dev/null 2>&1 || fail "this script needs apt (Ubuntu, Debian). Other systems: $SITE/docs/install.html"
# Ubuntu ships wget, not curl; take whichever is there.
if command -v wget >/dev/null 2>&1; then
    fetch() { wget -qO "$2" "$1"; }
elif command -v curl >/dev/null 2>&1; then
    fetch() { curl -fsSL -o "$2" "$1"; }
else
    fail "this script needs wget or curl."
fi

# Python 3.10+, GTK 4.6+ and libadwaita 1.1+: Ubuntu 22.04, Debian 12 and newer.
if [ -r /etc/os-release ]; then
    # shellcheck source=/dev/null
    . /etc/os-release
    case "${ID:-}:${VERSION_ID:-}" in
        ubuntu:[0-9].*|ubuntu:1[0-9].*|ubuntu:2[01].*|debian:[0-9]|debian:[0-9].*|debian:1[01]|debian:1[01].*)
            fail "Roue needs Ubuntu 22.04 or Debian 12 or newer (found ${PRETTY_NAME:-unknown})." ;;
    esac
fi

if [ "$(id -u)" -eq 0 ]; then
    SUDO=""
    [ -n "${SUDO_USER:-}" ] || say "Running as root: run 'roue setup' as yourself afterwards."
else
    command -v sudo >/dev/null 2>&1 || fail "sudo is missing: run this as root."
    SUDO="sudo"
    say "Roue needs your password to install with apt."
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# apt-get as root. Software Updater (PackageKit) refreshes apt's package lists
# in the background, and apt-get fails at once while it does: only the dpkg
# lock has a timeout. So wait for the other program, up to 5 minutes.
apt_get() {
    waited=0
    until $SUDO apt-get -o DPkg::Lock::Timeout=300 "$@" 2>"$tmp/apt-errors"; do
        # "E: " isn't translated, and the error names the lock file.
        if [ "$waited" -ge 300 ] || ! grep -q '^E: .*/lock' "$tmp/apt-errors"; then
            cat "$tmp/apt-errors" >&2
            return 1
        fi
        [ "$waited" -gt 0 ] || say "Another program is using apt (Software Updater?). Waiting for it to finish…"
        sleep 5
        waited=$((waited + 5))
    done
    cat "$tmp/apt-errors" >&2
}

if fetch "$SITE/apt/roue-archive-keyring.gpg" "$tmp/keyring.gpg"; then
    say "Adding Roue's update channel"
    $SUDO install -m 0644 "$tmp/keyring.gpg" "$KEYRING"
    cat > "$tmp/roue.sources" <<EOF
# Roue's update channel: Software Updater installs new Roue versions from here.
# Installed by the roue package. To stop updates from Roue, delete this file.
Types: deb
URIs: $SITE/apt/
Suites: ./
Signed-By: $KEYRING
EOF
    # Same text as the file the package ships, so dpkg doesn't ask about it.
    $SUDO install -m 0644 "$tmp/roue.sources" "$SOURCES"
    apt_get update
    say "Installing Roue"
    apt_get install -y -o Dpkg::Options::=--force-confdef roue
else
    # No update channel published yet: take the newest release instead.
    say "Downloading the latest release"
    fetch https://api.github.com/repos/guilyx/roue/releases/latest "$tmp/latest.json" ||
        fail "couldn't reach GitHub. See $SITE/docs/install.html"
    url=$(sed -n 's/.*"browser_download_url": *"\([^"]*_all\.deb\)".*/\1/p' "$tmp/latest.json" |
        head -n 1)
    [ -n "$url" ] || fail "couldn't find a release to install. See $SITE/docs/install.html"
    fetch "$url" "$tmp/roue.deb"
    chmod 0644 "$tmp/roue.deb"
    chmod 0755 "$tmp"
    say "Installing Roue"
    apt_get install -y "$tmp/roue.deb"
fi

# Hotkey, Files menu, GNOME helper: per user, so not as root.
if [ "$(id -u)" -ne 0 ]; then
    roue setup || true
elif [ -n "${SUDO_USER:-}" ]; then
    sudo -u "$SUDO_USER" roue setup || true
fi

say "Done. Open Roue from your apps, or right-click files in Files > Convert with Roue…"
