## What this changes

<!-- One or two sentences. Link the issue: "Closes #123". -->

## How to test it

<!-- Commands or steps a reviewer can follow, e.g. `roue gif clip.mov`. -->

## Checklist

- [ ] `make check` passes (ruff, mypy, pytest)
- [ ] New or changed presets have a case in `tests/test_conversions.py`
- [ ] User-facing errors are plain English (no raw tool output)
- [ ] Docs updated if behaviour changed (`docs/`, `README.md`, `CHANGELOG.md`)
- [ ] Nothing leaves the user's machine (no network calls, no telemetry)
