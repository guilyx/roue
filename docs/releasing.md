# Releasing

This page is for maintainers. It covers the update channel's signing key and
how releases happen.

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

Committing the key is also what starts releases: until it exists, the
Release workflow makes none, so no `.deb` ever goes out without its update
channel. (Local and CI builds still work without it.)

## Each merge is a release

There's nothing to do by hand. After every merge to `main`, the **Release**
workflow runs `scripts/release.py`, which reads the commits since the last
tag ([Conventional Commits](https://www.conventionalcommits.org), see
[Contributing](contributing.md)) and picks the version:

| Commits in the merge | Release |
|---|---|
| `feat!:` or a `BREAKING CHANGE:` footer | major (minor while below 1.0) |
| `feat:` | minor: 0.1.0 → 0.2.0 |
| `fix:`, `perf:`, `revert:` | patch: 0.1.0 → 0.1.1 |
| only `docs:`, `chore:`, `ci:`, `test:`… | none: nothing changed for users |

When there's a release to make, the workflow:

1. writes the version into `pyproject.toml`, `src/roue/__init__.py` and the
   website, and adds a `CHANGELOG.md` section listing the `feat`/`fix`
   commits;
2. commits that as `chore(release): vX.Y.Z`, tags `vX.Y.Z` and pushes both
   to `main`;
3. builds the sdist, the wheel and the `.deb` (with `SHA256SUMS`) and creates
   the GitHub release with the changelog section as notes;
4. starts the **Website** workflow, which downloads the `.deb` files of the
   last five releases, builds the signed APT repository with
   `scripts/apt-repo.sh`, and publishes it under
   `https://guilyx.github.io/roue/apt/`. Within a day, Software Updater
   offers the new version to everyone who installed Roue.

The `.deb` gets its version from `src/roue/__init__.py`;
`packaging/deb/build.sh` also stamps it into the man page and the AppStream
release list.

Good to know:

- **No releases before the key.** Until `packaging/apt/roue-archive-keyring.asc`
  is committed, the workflow skips releasing, so every release can update
  itself. The first run after that releases the version already in the files
  (0.1.0) with its hand-written changelog section.
- **Merges close together** are released one at a time, in order. If a merge
  lands while a release is being pushed, that merge's own run releases both.
- **Protected `main`:** the workflow pushes the release commit with the
  workflow token. If `main` requires pull requests, allow GitHub Actions to
  bypass that rule, or the run stops with an error.
- To release by hand (say, after fixing a failed run), start the **Release**
  workflow from the Actions tab: it releases whatever is unreleased.

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
