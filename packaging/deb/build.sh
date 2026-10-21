#!/usr/bin/env bash
# Build dist/roue_<version>_all.deb from this checkout.
#
# Usage: packaging/deb/build.sh [output-dir]
#
# Needs dpkg-deb, python3 (>= 3.10), gzip and gpg. The package installs the
# pure-Python roue package into /usr/lib/python3/dist-packages and the
# desktop integration (launcher, D-Bus service, icons, Files menu, GNOME
# helper extension) under /usr/share. Icon and desktop caches are refreshed
# by dpkg triggers.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HERE="$ROOT/packaging/deb"
OUT="${1:-$ROOT/dist}"
PYTHON="${PYTHON:-python3}"

VERSION="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$ROOT/src/roue/__init__.py")"
if [[ -z "$VERSION" ]]; then
    echo "error: couldn't read __version__ from src/roue/__init__.py" >&2
    exit 1
fi

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
PKG="$STAGE/roue"
SITE="$PKG/usr/lib/python3/dist-packages"
SHARE="$PKG/usr/share"
DOC="$SHARE/doc/roue"

echo "Building roue $VERSION"

# 1. The Python package (pure Python, data files live inside it).
mkdir -p "$SITE"
cp -r "$ROOT/src/roue" "$SITE/roue"
find "$SITE" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "$SITE" -name '*.py[co]' -delete

# 2. The launcher.
install -d "$PKG/usr/bin"
cat > "$PKG/usr/bin/roue" <<'EOF'
#!/usr/bin/python3
import sys

from roue.cli import main

sys.exit(main())
EOF
chmod 0755 "$PKG/usr/bin/roue"

# 3. Desktop integration, rendered by the same code 'roue setup' uses.
PYTHONPATH="$ROOT/src" "$PYTHON" - "$SHARE" <<'EOF'
import sys
from pathlib import Path

from roue.integrations import gnome_shell
from roue.integrations.desktop import install_desktop_files, install_nautilus_extension

base = Path(sys.argv[1])
install_desktop_files("/usr/bin/roue", base=base, refresh=False)
install_nautilus_extension("/usr/bin/roue", base=base)
gnome_shell.install(base=base)
EOF
# Belt and braces: caches belong to dpkg triggers, never ship them.
rm -f "$SHARE/applications/mimeinfo.cache" "$SHARE/icons/hicolor/icon-theme.cache"

# Software centres show the AppStream release list. Releases only bump the
# version number, so list this version here if it isn't yet.
STAMP="${SOURCE_DATE_EPOCH:-$(git -C "$ROOT" log -1 --format=%ct 2>/dev/null || date +%s)}"
install -d "$SHARE/metainfo"
"$PYTHON" - "$ROOT/data/io.github.guilyx.Roue.metainfo.xml" "$VERSION" \
    "$(date -u -d "@$STAMP" +%F)" > "$SHARE/metainfo/io.github.guilyx.Roue.metainfo.xml" <<'EOF'
import sys

path, version, day = sys.argv[1:]
text = open(path, encoding="utf-8").read()
if f'<release version="{version}"' not in text:
    entry = f'<releases>\n    <release version="{version}" date="{day}"/>'
    text = text.replace("<releases>", entry, 1)
sys.stdout.write(text)
EOF

# 4. The update channel: Software Updater then offers new Roue versions.
# Only once the signing key exists (scripts/apt-key.sh), or apt would fail.
KEYRING="$ROOT/packaging/apt/roue-archive-keyring.asc"
if [[ -f "$KEYRING" ]]; then
    install -Dm0644 "$ROOT/packaging/apt/roue.sources" "$PKG/etc/apt/sources.list.d/roue.sources"
    install -d "$SHARE/keyrings"
    gpg --batch --dearmor < "$KEYRING" > "$SHARE/keyrings/roue-archive-keyring.gpg"
    # Debian's own packages mustn't add APT sources; a third-party app that
    # updates itself through APT has to (as Chrome and VS Code do).
    install -d "$SHARE/lintian/overrides"
    echo "roue: package-installs-apt-sources [etc/apt/sources.list.d/roue.sources]" \
        > "$SHARE/lintian/overrides/roue"
else
    echo "note: no packaging/apt/roue-archive-keyring.asc: building without the update channel"
fi

# 5. Docs and man page.
install -Dm0644 "$HERE/copyright" "$DOC/copyright"
cat > "$STAGE/changelog" <<CHANGELOG
roue ($VERSION) unstable; urgency=medium

  * Upstream release $VERSION.
    Release notes: https://github.com/guilyx/roue/blob/main/CHANGELOG.md

 -- guilyx <guilyx@users.noreply.github.com>  $(LC_ALL=C date -R -u -d "@$STAMP")
CHANGELOG
gzip -9nc "$STAGE/changelog" > "$DOC/changelog.gz"
install -d "$SHARE/man/man1"
sed "s/\"roue [0-9][0-9.]*\"/\"roue $VERSION\"/" "$ROOT/packaging/man/roue.1" |
    gzip -9nc > "$SHARE/man/man1/roue.1.gz"

# 6. Control files.
find "$PKG" -type d -exec chmod 0755 {} +
find "$PKG" -type f ! -path "$PKG/usr/bin/*" -exec chmod 0644 {} +
install -d "$PKG/DEBIAN"
SIZE="$(du -sk --exclude=DEBIAN "$PKG" | cut -f1)"
sed -e "s/@VERSION@/$VERSION/" -e "s/@INSTALLED_SIZE@/$SIZE/" "$HERE/control.in" > "$PKG/DEBIAN/control"
if [[ -f "$PKG/etc/apt/sources.list.d/roue.sources" ]]; then
    echo "/etc/apt/sources.list.d/roue.sources" > "$PKG/DEBIAN/conffiles"
    chmod 0644 "$PKG/DEBIAN/conffiles"
fi
install -m0755 "$HERE/postinst" "$PKG/DEBIAN/postinst"
install -m0755 "$HERE/prerm" "$PKG/DEBIAN/prerm"
(cd "$PKG" && find usr -type f -exec md5sum {} + | sort -k2) > "$PKG/DEBIAN/md5sums"
chmod 0644 "$PKG/DEBIAN/control" "$PKG/DEBIAN/md5sums"

mkdir -p "$OUT"
DEB="$OUT/roue_${VERSION}_all.deb"
dpkg-deb --root-owner-group -Zxz --build "$PKG" "$DEB" >/dev/null
echo "Built $DEB"
