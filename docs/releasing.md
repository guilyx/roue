# Releasing

This page is for maintainers. It covers the update channel's signing key and
how to cut a release.

## Once: the signing key

Software Updater only trusts Roue's update channel if it's signed. Create the
key once:

```sh
scripts/apt-key.sh
```

It needs `gpg` and the [GitHub CLI](https://cli.github.com) (`gh`), logged in
with admin rights on the repository. It:

1. creates an ed25519 signing key;
2. writes the public key to `packaging/apt/roue-archive-keyring.asc`;
3. stores the private key as the `APT_SIGNING_KEY` secret of the repository;
4. leaves a backup of the private key in `~/roue-apt-signing-key.asc`.

Then:

- **Commit** `packaging/apt/roue-archive-keyring.asc`. Every `.deb` built
  from then on ships the key and the channel's sources file.
- **Move the backup offline** (a password manager, an encrypted drive). If the
  key is lost, every user has to trust a new key by hand.

Until the key exists, nothing breaks: the `.deb` builds without the update
channel, the Website workflow skips `/apt`, and `install.sh` installs the
latest release's `.deb` instead.

## Each release

1. Bump `__version__` in `src/roue/__init__.py`.
2. Move the *Unreleased* notes in `CHANGELOG.md` to a new
   `## [X.Y.Z] - YYYY-MM-DD` section.
3. Commit, tag and push the tag:

   ```sh
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```

The **Release** workflow checks that the tag matches `__version__`, builds the
sdist, the wheel and the `.deb`, writes `SHA256SUMS`, and creates the GitHub
release with the changelog section as notes. It then starts the **Website**
workflow, which downloads the `.deb` files of the last five releases, builds
the signed APT repository with `scripts/apt-repo.sh`, and publishes it under
`https://guilyx.github.io/roue/apt/`. Within a day, Software Updater offers
the new version to everyone who installed the `.deb`.

## Checks that guard the channel

- CI's **Debian package** job runs `scripts/test-update-channel.sh`: with a
  throwaway key, it installs the current `.deb`, publishes a newer build in a
  local signed channel, upgrades with apt, then purges and checks that the
  sources file and the key are gone.
- `tests/test_packaging.py` checks that `install.sh` writes the same sources
  file as the package, so dpkg never asks about it.

## The GNOME helper and new GNOME versions

GNOME refuses to load an extension that doesn't list the running GNOME
version. Each new GNOME release (every March and September) needs its number
added to `shell-version` in
`src/roue/data/gnome-shell/roue@guilyx.github.io/metadata.json` (currently 45
to 50). Check the extension still works in that version before listing it.
