#!/usr/bin/env bash
# End-to-end check of Roue's update channel, with a throwaway signing key:
# install this version's .deb, publish a newer build in a local signed
# channel, let apt upgrade to it, then purge. CI runs it; it changes the
# system's packages, so run it in a container or VM.
#
# Needs gpg, apt-ftparchive (apt-utils), python3, and root or sudo.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SUDO=""
[[ $(id -u) -eq 0 ]] || SUDO="sudo"
WORK="$(mktemp -d)"  # short path: gpg's socket must fit in 108 bytes
PORT="$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"
cleanup() {
    [[ -n "${SERVER:-}" ]] && kill "$SERVER" 2>/dev/null
    gpgconf --kill gpg-agent 2>/dev/null || true
    rm -rf "$WORK"
}
trap cleanup EXIT

export GNUPGHOME="$WORK/gnupg"
mkdir -m 0700 "$GNUPGHOME"
gpg --batch --quiet --passphrase '' --quick-gen-key "Roue test key" ed25519 sign 1d

# Two builds of this checkout, signed by the test key: now and "next".
mkdir "$WORK/src" "$WORK/debs"
git -C "$ROOT" ls-files -co --exclude-standard -- . ':!website/assets' |
    tar -C "$ROOT" -cf - -T - | tar -C "$WORK/src" -xf -
gpg --batch --armor --export > "$WORK/src/packaging/apt/roue-archive-keyring.asc"
version="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$WORK/src/src/roue/__init__.py")"
next="$(python3 -c 'import sys; v = sys.argv[1].split("."); v[-1] = str(int(v[-1]) + 1); print(".".join(v))' "$version")"
"$WORK/src/packaging/deb/build.sh" "$WORK/debs"
sed -i "s/^__version__ = .*/__version__ = \"$next\"/" "$WORK/src/src/roue/__init__.py"
"$WORK/src/packaging/deb/build.sh" "$WORK/debs"

APT_SIGNING_KEY="$(gpg --batch --armor --export-secret-keys)" \
    "$ROOT/scripts/apt-repo.sh" "$WORK/debs" "$WORK/site/apt"
python3 -m http.server --bind 127.0.0.1 --directory "$WORK/site" "$PORT" >/dev/null 2>&1 &
SERVER=$!
sleep 1

chmod -R a+rX "$WORK/debs"
$SUDO apt-get install -y "$WORK/debs/roue_${version}_all.deb"
grep -q "guilyx.github.io/roue/apt" /etc/apt/sources.list.d/roue.sources
# Point the channel at the local copy (the package ships the real URL).
$SUDO sed -i "s|https://guilyx.github.io/roue/apt/|http://127.0.0.1:$PORT/apt/|" \
    /etc/apt/sources.list.d/roue.sources
only_roue=(-o Dir::Etc::sourcelist=/etc/apt/sources.list.d/roue.sources
    -o Dir::Etc::sourceparts=- -o APT::Get::List-Cleanup=0)
$SUDO apt-get "${only_roue[@]}" update 2>&1 | tee "$WORK/update.log"
if grep -qiE "^(W|E):" "$WORK/update.log"; then
    echo "error: apt complained about the channel" >&2
    exit 1
fi
apt list --upgradable 2>/dev/null | grep -q "^roue/.* $next all"
$SUDO apt-get install -y --only-upgrade -o Dpkg::Options::=--force-confold roue
test "$(roue --version)" = "roue $next"

$SUDO apt-get purge -y roue
test ! -e /etc/apt/sources.list.d/roue.sources
test ! -e /usr/share/keyrings/roue-archive-keyring.gpg
echo "Update channel OK: $version -> $next over signed apt"
