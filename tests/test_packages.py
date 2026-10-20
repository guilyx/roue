from __future__ import annotations

import pytest

from roue.engine import tools
from roue.integrations import packages


def test_missing_capabilities_follow_the_installed_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROUE_DISABLE_TOOLS", "vips,imagemagick,libreoffice")
    tools.which.cache_clear()
    titles = [c.title for c in packages.missing()]
    assert "Images" in titles and "Office documents to PDF" in titles


def test_apt_packages_and_command() -> None:
    names = packages.apt_packages(["libreoffice", "ffmpeg", "ffprobe"])
    assert names == ["libreoffice-writer", "libreoffice-calc", "libreoffice-impress", "ffmpeg"]
    argv = packages.install_argv(["ffmpeg"])
    assert argv[:3] == ["pkexec", "apt-get", "install"] and argv[-1] == "ffmpeg"
