# Contributing

Roue is a community project and contributions of every size are welcome: a
typo fix, a new preset, a bug report with a sample file, a translation, a
packaging recipe for your distribution.

The full guide is in [CONTRIBUTING.md](../CONTRIBUTING.md). The short version:

## Set up

```sh
git clone https://github.com/guilyx/roue
cd roue
make dev      # creates .venv with your system's GTK, installs dev tools
make test     # runs the test suite
make run      # opens the panel from your checkout
```

You need the system packages from [Install](install.md) (FFmpeg, libvips,
GTK 4, libadwaita…). Tests for presets whose tools you don't have are skipped.

## Before you open a pull request

```sh
make lint       # ruff
make typecheck  # mypy (strict on the engine)
make test
```

## Adding a preset

1. Add it to the right file in `src/roue/presets/`.
2. Add a case for it in `tests/test_conversions.py`. The suite checks that
   every built-in preset has one.
3. Run `make site` to refresh the [presets reference](presets.md).

Good presets do one thing, have a short name, a one-line description that
says what you get, and defaults that are right for most people.

## Reporting bugs

Open an [issue](https://github.com/guilyx/roue/issues/new/choose) with:

- what you dropped (type, size; attach a sample if you can),
- the preset,
- what happened, and the output of `roue convert PRESET FILE --verbose`,
- the output of `roue doctor`.

## Code of conduct

Be kind. See [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md).
