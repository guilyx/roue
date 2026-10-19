"""Desktop notifications for the CLI (the GTK app uses GNotification)."""

from __future__ import annotations

import shutil
import subprocess

from .. import APP_ID, APP_NAME


def send(title: str, body: str = "", *, error: bool = False) -> bool:
    exe = shutil.which("notify-send")
    if not exe:
        return False
    cmd = [exe, f"--app-name={APP_NAME}", f"--icon={APP_ID}", title]
    if error:
        cmd.insert(1, "--urgency=normal")
    if body:
        cmd.append(body)
    try:
        return subprocess.run(cmd, capture_output=True, timeout=10, check=False).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False
