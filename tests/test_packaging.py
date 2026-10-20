"""The update channel: the installer and the package must agree."""

from __future__ import annotations

import re
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
