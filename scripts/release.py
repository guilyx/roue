"""Work out the next release from the commits since the last tag, and stamp it.

Usage: python scripts/release.py [--github-output FILE]

The Release workflow runs this after every merge to main. Commit messages
follow Conventional Commits and decide the version:

- ``feat!:`` or a ``BREAKING CHANGE:`` footer: major (0.x too: 0.3.0 → 1.0.0)
- ``feat:``: minor
- ``fix:``, ``perf:``, ``revert:``: patch
- anything else (``docs:``, ``chore:``, ``ci:``, ``test:``...): no release

With a release to make, it writes the version into ``pyproject.toml``,
``src/roue/__init__.py`` and the website, adds a ``CHANGELOG.md`` section,
and writes the notes to ``release-notes.md``. The very first release (no tag
yet) ships the version already in the files, with its hand-written notes.
Nothing is committed or tagged here: the workflow does that.
"""

from __future__ import annotations

import argparse
import datetime
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_URL = "https://github.com/guilyx/roue"
SECTIONS = {"feat": "Added", "fix": "Fixed", "perf": "Changed", "revert": "Changed"}
SUBJECT = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]*)\))?(?P<bang>!)?: (?P<text>.+)$")


@dataclass(frozen=True)
class Commit:
    sha: str
    subject: str
    body: str = ""

    @property
    def parsed(self) -> re.Match[str] | None:
        return SUBJECT.match(self.subject)

    @property
    def kind(self) -> str | None:
        match = self.parsed
        return match["type"] if match else None

    @property
    def breaking(self) -> bool:
        match = self.parsed
        return bool(match and match["bang"]) or "BREAKING CHANGE:" in self.body

    @property
    def is_release(self) -> bool:
        match = self.parsed
        return bool(match and match["type"] == "chore" and match["scope"] == "release")


def bump(version: str, commits: list[Commit]) -> str | None:
    """The next version, or None when nothing user-facing changed."""
    major, minor, patch = (int(part) for part in version.split("."))
    relevant = [c for c in commits if not c.is_release]
    if any(c.breaking for c in relevant):
        return f"{major + 1}.0.0"
    if any(c.kind == "feat" for c in relevant):
        return f"{major}.{minor + 1}.0"
    if any(c.kind in ("fix", "perf", "revert") for c in relevant):
        return f"{major}.{minor}.{patch + 1}"
    return None


def notes(commits: list[Commit]) -> str:
    """Changelog entries, grouped like Keep a Changelog."""
    groups: dict[str, list[str]] = {}
    for commit in commits:
        match = commit.parsed
        if (
            not match
            or commit.is_release
            or (match["type"] not in SECTIONS and not commit.breaking)
        ):
            continue
        section = (
            "Changed"
            if commit.breaking and match["type"] not in SECTIONS
            else SECTIONS[match["type"]]
        )
        text = match["text"]
        if match["scope"]:
            text = f"**{match['scope']}:** {text}"
        if commit.breaking:
            text = f"**Breaking:** {text}"
        groups.setdefault(section, []).append(
            f"- {text} ([{commit.sha[:7]}]({REPO_URL}/commit/{commit.sha}))"
        )
    order = ["Added", "Changed", "Fixed"]
    return "\n\n".join(
        f"### {name}\n\n" + "\n".join(groups[name]) for name in order if name in groups
    )


def add_changelog_section(changelog: str, version: str, day: str, body: str) -> str:
    """Insert ``## [version] - day`` above the newest release, and its link."""
    section = f"## [{version}] - {day}\n\n{body}\n\n"
    first = changelog.find("\n## [")
    if first == -1:
        changelog = changelog.rstrip("\n") + "\n\n" + section.rstrip("\n") + "\n"
    else:
        changelog = changelog[: first + 1] + section + changelog[first + 1 :]
    link = f"[{version}]: {REPO_URL}/releases/tag/v{version}\n"
    refs = re.search(r"^\[\d+\.\d+\.\d+\]: ", changelog, re.M)
    if refs:
        return changelog[: refs.start()] + link + changelog[refs.start() :]
    return changelog.rstrip("\n") + "\n\n" + link


def changelog_section(changelog: str, version: str) -> str | None:
    # A section ends at the next release or at the link list at the bottom.
    end = r"(?=^## \[|^\[\d+\.\d+\.\d+\]: |\Z)"
    match = re.search(rf"^## \[{re.escape(version)}\][^\n]*\n(.*?){end}", changelog, re.M | re.S)
    return match.group(1).strip() if match else None


def date_section(changelog: str, version: str, day: str) -> str:
    return re.sub(
        rf"^## \[{re.escape(version)}\].*$",
        f"## [{version}] - {day}",
        changelog,
        count=1,
        flags=re.M,
    )


def set_version(version: str) -> None:
    edits = {
        "src/roue/__init__.py": (r'^__version__ = "[^"]*"$', f'__version__ = "{version}"'),
        "pyproject.toml": (r'^version = "[^"]*"$', f'version = "{version}"'),
        "website/index.html": (r"Version \d+\.\d+\.\d+ ·", f"Version {version} ·"),
    }
    for name, (pattern, replacement) in edits.items():
        path = ROOT / name
        text, count = re.subn(
            pattern, replacement, path.read_text(encoding="utf-8"), count=1, flags=re.M
        )
        if count != 1:
            raise SystemExit(f"error: couldn't find the version in {name}")
        path.write_text(text, encoding="utf-8")


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout


def last_tag() -> str | None:
    try:
        return git("describe", "--tags", "--abbrev=0", "--match", "v[0-9]*").strip() or None
    except subprocess.CalledProcessError:
        return None


def commits_since(tag: str) -> list[Commit]:
    log = git("log", "--no-merges", "--format=%H%x1f%s%x1f%b%x1e", f"{tag}..HEAD")
    commits = []
    for record in log.split("\x1e"):
        if record.strip():
            sha, subject, body = [*record.strip("\n").split("\x1f"), "", ""][:3]
            commits.append(Commit(sha, subject, body))
    return commits


def current_version() -> str:
    text = (ROOT / "src/roue/__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__ = "([^"]*)"$', text, re.M)
    if not match:
        raise SystemExit("error: no __version__ in src/roue/__init__.py")
    return match.group(1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--github-output", type=Path, help="append version=… and tag=… here")
    args = parser.parse_args()

    changelog_path = ROOT / "CHANGELOG.md"
    changelog = changelog_path.read_text(encoding="utf-8")
    day = datetime.datetime.now(datetime.UTC).date().isoformat()
    tag = last_tag()
    if tag is None:
        # First release: ship what the files say, with the hand-written notes.
        version = current_version()
        body = changelog_section(changelog, version)
        if body is None:
            raise SystemExit(f"error: CHANGELOG.md has no section for {version}")
        changelog_path.write_text(date_section(changelog, version, day), encoding="utf-8")
    else:
        commits = commits_since(tag)
        new = bump(tag.removeprefix("v"), commits)
        if new is None:
            print(f"Nothing to release since {tag}: no feat, fix or breaking commits.")
            return 0
        version, body = new, notes(commits)
        set_version(version)
        changelog_path.write_text(
            add_changelog_section(changelog, version, day, body), encoding="utf-8"
        )

    (ROOT / "release-notes.md").write_text(body + "\n", encoding="utf-8")
    print(f"Releasing {version}")
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as out:
            out.write(f"version={version}\ntag=v{version}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
