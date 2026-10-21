"""The installer and the update channel."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_installer_writes_the_same_sources_file_as_the_package() -> None:
    # dpkg asks about a conffile that differs from what's already on disk.
    script = (ROOT / "website" / "install.sh").read_text()
    body = re.search(r'cat > "\$tmp/roue.sources" <<EOF\n(.*?)\nEOF\n', script, re.S)
    assert body
    site = re.search(r'^SITE="(.*)"$', script, re.M)
    keyring = re.search(r"^KEYRING=(.*)$", script, re.M)
    assert site and keyring
    text = body.group(1).replace("$SITE", site.group(1)).replace("$KEYRING", keyring.group(1))
    assert text + "\n" == (ROOT / "packaging" / "apt" / "roue.sources").read_text()


def _run_apt_get(tmp_path: Path, failures: str) -> subprocess.CompletedProcess[str]:
    """Run the installer's apt_get with a fake apt-get that fails with ``failures`` first."""
    script = (ROOT / "website" / "install.sh").read_text()
    function = re.search(r"^apt_get\(\) \{\n.*?^\}\n", script, re.S | re.M)
    assert function
    (tmp_path / "failures").write_text(failures)
    fake = tmp_path / "apt-get"
    fake.write_text(
        "#!/bin/sh\n"
        f'echo call >> "{tmp_path}/calls"\n'
        f'line=$(head -n 1 "{tmp_path}/failures")\n'
        '[ -n "$line" ] || exit 0\n'
        f'sed -i 1d "{tmp_path}/failures"\n'
        'echo "$line" >&2\n'
        "exit 100\n"
    )
    fake.chmod(0o755)
    harness = (
        'set -eu\nsay() { echo "$*"; }\nsleep() { :; }\nSUDO=""\n'
        f'tmp="{tmp_path}"\n{function.group(0)}apt_get update\n'
    )
    return subprocess.run(
        ["sh", "-c", harness],
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"},
        check=False,
    )


def test_installer_waits_while_software_updater_holds_apt(tmp_path: Path) -> None:
    busy = (
        "E: Could not get lock /var/lib/apt/lists/lock. It is held by process 2264 (packagekitd)\n"
    )
    proc = _run_apt_get(tmp_path, busy * 2)
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "calls").read_text().count("call") == 3
    assert proc.stdout.count("Waiting") == 1


def test_installer_fails_at_once_on_other_apt_errors(tmp_path: Path) -> None:
    proc = _run_apt_get(tmp_path, "E: Unable to locate package roue\n")
    assert proc.returncode != 0
    assert (tmp_path / "calls").read_text().count("call") == 1
    assert "Unable to locate package roue" in proc.stderr


def _run_installer(tmp_path: Path, *, roue_channel_works: bool) -> subprocess.CompletedProcess[str]:
    """Run install.sh with stand-ins for apt-get, sudo, install, wget and roue.

    The full apt-get update fails, as it does when another repository is broken.
    """
    fakes = {
        "apt-get": (
            f'echo "$*" >> "{tmp_path}/apt-get.log"\n'
            'case "$*" in\n'
            f"  *sourcelist=*) exit {0 if roue_channel_works else 100} ;;\n"
            "  *update*) echo \"E: The repository 'https://pkgs.netbird.io/debian stable"
            " Release' no longer has a Release file.\" >&2; exit 100 ;;\n"
            "esac\n"
        ),
        "sudo": 'exec "$@"\n',
        "install": "",  # not the system's keyring and sources folders
        "wget": 'echo key > "$2"\n',
        "roue": "",
    }
    for name, body in fakes.items():
        fake = tmp_path / name
        fake.write_text("#!/bin/sh\n" + body)
        fake.chmod(0o755)
    return subprocess.run(
        ["sh", str(ROOT / "website" / "install.sh")],
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"},
        check=False,
    )


def test_installer_gets_past_other_broken_repositories(tmp_path: Path) -> None:
    proc = _run_installer(tmp_path, roue_channel_works=True)
    assert proc.returncode == 0, proc.stderr
    calls = (tmp_path / "apt-get.log").read_text().splitlines()
    assert len(calls) == 3
    assert calls[0].endswith(" update")
    assert "sourcelist=/etc/apt/sources.list.d/roue.sources" in calls[1]
    assert "List-Cleanup=0" in calls[1]  # keeps the other repositories' lists
    assert calls[2].endswith(" roue")
    assert "pkgs.netbird.io" in proc.stderr


def test_installer_stops_when_roues_channel_fails(tmp_path: Path) -> None:
    proc = _run_installer(tmp_path, roue_channel_works=False)
    assert proc.returncode != 0
    assert not any("install" in c for c in (tmp_path / "apt-get.log").read_text().splitlines())
