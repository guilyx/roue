#!/usr/bin/env bash
# Build Roue's APT channel (a flat, signed repository) from .deb files.
#
# Usage: scripts/apt-repo.sh <dir-with-debs> <output-dir>
#
# Signs with the armored private key in $APT_SIGNING_KEY. Without it the
# repository is built unsigned, which apt refuses: fine for a dry run only.
# Needs apt-ftparchive (apt-utils) and gpg.
set -euo pipefail

DEBS="${1:?usage: apt-repo.sh <dir-with-debs> <output-dir>}"
OUT="${2:?usage: apt-repo.sh <dir-with-debs> <output-dir>}"
KEEP="${KEEP_VERSIONS:-5}"  # older versions stay downloadable for rollbacks

mkdir -p "$OUT"
# Newest versions first, so `head` keeps the most recent ones.
mapfile -t debs < <(find "$DEBS" -maxdepth 1 -name 'roue_*_all.deb' -printf '%f\n' | sort -rV | head -n "$KEEP")
if [[ ${#debs[@]} -eq 0 ]]; then
    echo "error: no roue_*_all.deb in $DEBS" >&2
    exit 1
fi
for deb in "${debs[@]}"; do
    cp "$DEBS/$deb" "$OUT/"
done

cd "$OUT"
rm -f InRelease Release Release.gpg
# SHA-256 and SHA-512 only: newer apt warns about MD5 and SHA-1.
hashes=(-o APT::FTPArchive::MD5=false -o APT::FTPArchive::SHA1=false)
apt-ftparchive "${hashes[@]}" packages . > Packages
gzip -9nkf Packages
# Written outside, or Release would list a hash of itself.
apt-ftparchive "${hashes[@]}" \
    -o APT::FTPArchive::Release::Origin=Roue \
    -o APT::FTPArchive::Release::Label=Roue \
    -o APT::FTPArchive::Release::Description="Roue, a drag-and-drop file converter" \
    release . > ../Release.tmp
mv ../Release.tmp Release

if [[ -z "${APT_SIGNING_KEY:-}" ]]; then
    echo "warning: APT_SIGNING_KEY isn't set: the repository is unsigned" >&2
    exit 0
fi
export GNUPGHOME
GNUPGHOME="$(mktemp -d)"
trap 'rm -rf "$GNUPGHOME"' EXIT
gpg --batch --quiet --import <<<"$APT_SIGNING_KEY"
key="$(gpg --batch --list-secret-keys --with-colons | awk -F: '/^fpr:/ {print $10; exit}')"
gpg --batch --yes --local-user "$key" --digest-algo SHA512 --clearsign -o InRelease Release
gpg --batch --yes --local-user "$key" --digest-algo SHA512 -abs -o Release.gpg Release
gpg --batch --export "$key" > roue-archive-keyring.gpg
gpg --batch --armor --export "$key" > roue-archive-keyring.asc
echo "Signed with $key: ${debs[*]}"
