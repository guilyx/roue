"""scripts/release.py: the version each merge releases, and its changelog."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "release", Path(__file__).resolve().parents[1] / "scripts" / "release.py"
)
assert spec and spec.loader
release = importlib.util.module_from_spec(spec)
sys.modules["release"] = release  # dataclasses look their module up there
spec.loader.exec_module(release)
Commit = release.Commit


def commits(*subjects: str) -> list:
    return [Commit(f"{i:040d}", s) for i, s in enumerate(subjects)]


@pytest.mark.parametrize(
    ("version", "subjects", "expected"),
    [
        ("0.1.0", ["fix: keep sample rate"], "0.1.1"),
        ("0.1.0", ["fix: a", "feat(ui): wheel"], "0.2.0"),
        ("0.1.3", ["feat!: new preset format"], "0.2.0"),  # breaking stays minor below 1.0
        ("1.4.2", ["refactor!: drop the panel"], "2.0.0"),
        ("1.4.2", ["perf: faster thumbnails"], "1.4.3"),
        ("0.1.0", ["docs: typo", "chore(deps): bump actions", "ci: lint"], None),
        ("0.1.0", ["Merge pull request #9 from x/y", "Update README.md"], None),
        ("0.1.0", ["chore(release): v0.1.1", "docs: x"], None),
    ],
)
def test_bump(version: str, subjects: list[str], expected: str | None) -> None:
    assert release.bump(version, commits(*subjects)) == expected


def test_breaking_footer_counts() -> None:
    footer = Commit("a" * 40, "feat: new config", "BREAKING CHANGE: settings moved")
    assert release.bump("1.0.0", [footer]) == "2.0.0"


def test_notes_group_by_kind_and_skip_the_rest() -> None:
    text = release.notes(
        commits("feat(cli): roue info", "fix: odd sizes", "docs: x", "feat: wheel")
    )
    assert text.index("### Added") < text.index("### Fixed")
    assert "- **cli:** roue info ([0000000](" in text
    assert "docs" not in text


def test_changelog_section_goes_above_the_newest_release() -> None:
    changelog = (
        "# Changelog\n\nIntro.\n\n## [0.1.0] - 2026-10-21\n\nFirst.\n\n"
        "[0.1.0]: https://github.com/guilyx/roue/releases/tag/v0.1.0\n"
    )
    updated = release.add_changelog_section(changelog, "0.2.0", "2026-11-01", "### Added\n\n- x")
    assert updated.index("## [0.2.0] - 2026-11-01") < updated.index("## [0.1.0]")
    assert updated.endswith(
        "[0.2.0]: https://github.com/guilyx/roue/releases/tag/v0.2.0\n"
        "[0.1.0]: https://github.com/guilyx/roue/releases/tag/v0.1.0\n"
    )
    assert updated.startswith("# Changelog\n\nIntro.\n")
    assert release.changelog_section(updated, "0.2.0") == "### Added\n\n- x"
    assert release.changelog_section(updated, "0.1.0") == "First."


def test_first_release_dates_its_section() -> None:
    changelog = "# Changelog\n\n## [0.1.0] - Unreleased\n\nFirst.\n"
    assert "## [0.1.0] - 2026-11-01\n" in release.date_section(changelog, "0.1.0", "2026-11-01")


def test_versions_live_where_set_version_looks() -> None:
    root = Path(__file__).resolve().parents[1]
    assert 'version = "' in (root / "pyproject.toml").read_text()
    assert (
        "Version " + release.current_version() + " ·" in (root / "website/index.html").read_text()
    )
    assert release.changelog_section((root / "CHANGELOG.md").read_text(), release.current_version())
