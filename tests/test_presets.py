from __future__ import annotations

from pathlib import Path

import pytest

from roue.engine.errors import PresetError
from roue.engine.presets import GROUPS, load_preset_file, load_presets, parse_preset

MINIMAL = {
    "id": "to-thing",
    "name": "Thing",
    "backend": "image",
    "accepts": ["image/*"],
    "output_ext": "png",
}


def test_builtin_presets_load_and_are_valid() -> None:
    registry = load_presets(include_user=False)
    assert len(registry) >= 25
    ids = [p.id for p in registry]
    assert len(ids) == len(set(ids))
    for preset in registry:
        assert preset.builtin
        assert preset.group in GROUPS
        assert preset.description, f"{preset.id} needs a description"
        assert preset.icon.endswith("-symbolic"), f"{preset.id} needs a symbolic icon"
        if preset.output_ext == "same" or preset.only_if_smaller:
            # Same-format results need a suffix to be told apart from the original.
            assert preset.suffix or preset.output_ext != "same"


def test_order_follows_groups() -> None:
    groups = [p.group for p in load_presets(include_user=False)]
    order = list(GROUPS)
    assert groups == sorted(groups, key=order.index)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"id": "Bad Id"}, "lowercase"),
        ({"backend": "nope"}, "unknown backend"),
        ({"output_ext": ".tar.gz"}, "output_ext"),
        ({"accepts": []}, "at least one"),
        ({"output": "zip"}, "output must be"),
        ({"suffix": "a/b"}, "suffix"),
        ({"backend": "command"}, "params.command"),
    ],
)
def test_invalid_presets_explain_themselves(change: dict[str, object], message: str) -> None:
    with pytest.raises(PresetError, match=message):
        parse_preset({**MINIMAL, **change})


def test_missing_keys_are_listed() -> None:
    with pytest.raises(PresetError, match="name, backend"):
        parse_preset({"id": "x", "accepts": "image/*", "output_ext": "png"})


def test_accepts_and_rejects() -> None:
    preset = parse_preset({**MINIMAL, "rejects": ["image/png"]})
    assert preset.accepts_mime("image/jpeg")
    assert not preset.accepts_mime("image/png")
    assert not preset.accepts_mime("video/mp4")


def test_user_presets_override_and_extend(tmp_path: Path) -> None:
    (tmp_path / "mine.yaml").write_text(
        "presets:\n"
        "  - {id: jpg, name: My JPG, backend: image, accepts: 'image/*', output_ext: jpg}\n"
        "  - {id: shout, name: Shout, backend: command, accepts: 'text/*', output_ext: txt,\n"
        "     params: {command: 'tr a-z A-Z'}}\n"
    )
    registry = load_presets([tmp_path], include_user=False)
    assert registry.get("jpg").name == "My JPG"
    assert not registry.get("jpg").builtin
    assert registry.get("shout").group == "custom"


def test_broken_user_preset_is_reported_not_fatal(tmp_path: Path) -> None:
    (tmp_path / "broken.yaml").write_text("id: [unclosed\n")
    registry = load_presets([tmp_path], include_user=False)
    assert registry.problems and "valid YAML" in registry.problems[0]
    assert "jpg" in registry


def test_single_preset_file(tmp_path: Path) -> None:
    path = tmp_path / "one.yml"
    path.write_text("id: one\nname: One\nbackend: image\naccepts: image/*\noutput_ext: webp\n")
    [preset] = load_preset_file(path)
    assert preset.id == "one" and preset.source == path


def test_matching_ranks_the_files_own_kind_first() -> None:
    registry = load_presets(include_user=False)
    video = registry.matching(["video/quicktime"])
    ids = [p.id for p in video]
    assert ids[0] == "mp4"
    assert "mp3" in ids  # audio presets also take videos...
    assert ids.index("mp3") > ids.index("mute")  # ...but come after video presets
    assert registry.matching(["image/png", "video/mp4"]) == []
    jpg_targets = [p.id for p in registry.matching(["image/jpeg"])]
    assert "jpg" not in jpg_targets and "webp" in jpg_targets


def test_unknown_preset_suggests_close_ids() -> None:
    registry = load_presets(include_user=False)
    with pytest.raises(PresetError, match="no preset") as info:
        registry.get("mp")
    assert info.value.hint and "mp4" in info.value.hint


def test_query_matches_keywords() -> None:
    registry = load_presets(include_user=False)
    assert registry.get("share-10mb").matches_query("discord")
    assert registry.get("strip-metadata").matches_query("gps")
    assert not registry.get("jpg").matches_query("discord")


def test_same_format_keeps_the_extension_case() -> None:
    preset = load_presets(include_user=False).get("strip-metadata")
    assert preset.output_extension(Path("IMG_0001.HEIC")) == "HEIC"
    assert preset.output_extension(Path("photo.jpg")) == "jpg"


def test_pdf_preset_needs_libreoffice_or_a_pdf_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pandoc alone can't make PDFs: the tile mustn't look ready."""
    from roue.engine import tools
    from roue.engine.backends import missing_tools

    pdf = load_presets().get("pdf")
    monkeypatch.setenv("ROUE_DISABLE_TOOLS", ",".join(["libreoffice", *tools.PDF_ENGINES]))
    tools.which.cache_clear()
    assert ("libreoffice", *tools.PDF_ENGINES) in missing_tools(pdf)
