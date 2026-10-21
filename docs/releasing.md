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

## Once: let the workflow open pull requests

In the repository's **Settings → Actions → General → Workflow permissions**,
tick **Allow GitHub Actions to create and approve pull requests**.
release-please needs it to open the release pull request.

## Each release: merge the release pull request

Releases are automatic, driven by [Conventional Commits](https://www.conventionalcommits.org)
(see [Contributing](contributing.md)):

1. Merge pull requests as usual. After each merge to `main`, the **Release**
   workflow runs [release-please](https://github.com/googleapis/release-please),
   which keeps one pull request open, titled `chore: release X.Y.Z`. It bumps
   the version (`pyproject.toml`, `src/roue/__init__.py`, the website) and adds
   the changelog section, both computed from the commits since the last
   release: `fix:` → patch, `feat:` → minor (while below 1.0), `feat!:` →
   major. `docs:`, `chore:`, `ci:` and `test:` commits don't make a release
   on their own.
2. When you want to ship, **merge that pull request**. That's the release:
   the workflow tags `vX.Y.Z`, creates the GitHub release, builds the sdist,
   the wheel and the `.deb` (with `SHA256SUMS`) and attaches them.
3. It then starts the **Website** workflow, which downloads the `.deb` files of
   the last five releases, builds the signed APT repository with
   `scripts/apt-repo.sh`, and publishes it under
   `https://guilyx.github.io/roue/apt/`. Within a day, Software Updater offers
   the new version to everyone who installed Roue.

The release pull request is made with the workflow's token, so GitHub doesn't
run CI on it. That's fine: it only changes version numbers and the changelog,
and every commit it lists was checked when it merged.

The `.deb` gets its version from `src/roue/__init__.py`. `packaging/deb/build.sh`
also stamps it into the man page and the AppStream release list.

### The first release

release-please starts counting from 0.1.0 (`.release-please-manifest.json`),
and 0.1.0 itself is the one release made by hand. After `scripts/apt-key.sh`
(so 0.1.0 already carries the update channel):

```sh
git tag v0.1.0 && git push origin v0.1.0
```

A pushed `vX.Y.Z` tag goes through the same publish steps, with the matching
`CHANGELOG.md` section as release notes. You can also use it to re-publish a
release by hand.

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
