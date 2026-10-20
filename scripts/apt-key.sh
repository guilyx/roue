#!/usr/bin/env bash
# One-time setup for maintainers: create the key that signs Roue's APT channel.
#
# Writes the public key to packaging/apt/roue-archive-keyring.asc (commit it:
# every .deb then ships it, so installs pick up updates) and stores the
# private key as the APT_SIGNING_KEY secret of the GitHub repository (needs
# the gh CLI, logged in with admin rights on the repo).
#
# Keep the private key safe: losing it means every user must re-trust a new
# key by hand. The script also leaves a backup copy you should move offline.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PUBLIC="$ROOT/packaging/apt/roue-archive-keyring.asc"
BACKUP="${1:-$HOME/roue-apt-signing-key.asc}"

if [[ -e "$PUBLIC" ]]; then
    echo "error: $PUBLIC exists already. Rotating keys is a manual job." >&2
    exit 1
fi
command -v gh >/dev/null || { echo "error: install the gh CLI first" >&2; exit 1; }

export GNUPGHOME
GNUPGHOME="$(mktemp -d)"
trap 'rm -rf "$GNUPGHOME"' EXIT
gpg --batch --passphrase '' --quick-gen-key "Roue APT repository <guilyx@users.noreply.github.com>" ed25519 sign 10y
key="$(gpg --batch --list-secret-keys --with-colons | awk -F: '/^fpr:/ {print $10; exit}')"

gpg --batch --armor --export "$key" > "$PUBLIC"
(umask 077 && gpg --batch --armor --export-secret-keys "$key" > "$BACKUP")
gh secret set APT_SIGNING_KEY --repo guilyx/roue < "$BACKUP"

echo
echo "Key $key"
echo "  public:  $PUBLIC  (commit this)"
echo "  private: GitHub secret APT_SIGNING_KEY, backup in $BACKUP (move it offline)"
