"""Images as PDF pages: JPEG and PNM parsing, page sizes, and the PDF writer."""

from __future__ import annotations

import re
import shutil
import struct
import subprocess
from pathlib import Path

import pytest

from roue.engine.pdfimages import (
    PageImage,
    PdfWriter,
    jpeg_info,
    jpeg_page,
    page_size,
    pnm_page,
    read_pnm,
    strip_jpeg_metadata,
)


def exif(orientation: int, order: str = "II") -> bytes:
    fmt = "<" if order == "II" else ">"
    entry = struct.pack(f"{fmt}HHIHH", 0x0112, 3, 1, orientation, 0)
    gps = struct.pack(f"{fmt}HHII", 0x8825, 4, 1, 0)
    ifd = struct.pack(f"{fmt}H", 2) + entry + gps + struct.pack(f"{fmt}I", 0)
    tiff = order.encode() + struct.pack(f"{fmt}HI", 42, 8) + ifd
    return b"Exif\0\0" + tiff + b"GPS-SECRET"


def segment(marker: int, body: bytes) -> bytes:
    return bytes([0xFF, marker]) + struct.pack(">H", len(body) + 2) + body


def jpeg(
    width: int = 40,
    height: int = 30,
    *,
    components: int = 3,
    precision: int = 8,
    orientation: int | None = None,
    order: str = "II",
    scan: bytes = b"\x12\x34",
) -> bytes:
    """Just enough of a JPEG for the header parser (not decodable)."""
    parts = [b"\xff\xd8"]
    if orientation is not None:
        parts.append(segment(0xE1, exif(orientation, order)))
    parts.append(segment(0xE0, b"JFIF\0\x01\x01\0\0\x01\0\x01\0\0"))
    parts.append(segment(0xFE, b"a comment"))
    sof = bytes([precision]) + struct.pack(">HH", height, width) + bytes([components])
    parts.append(segment(0xC0, sof + b"\x01\x11\x00" * components))
    parts.append(segment(0xDA, bytes([components]) + b"\x01\x00" * components + b"\x00\x3f\x00"))
    parts.append(scan + b"\xff\xd9")
    return b"".join(parts)


@pytest.mark.parametrize("order", ["II", "MM"])
def test_jpeg_info_reads_size_and_orientation(order: str) -> None:
    info = jpeg_info(jpeg(400, 300, orientation=6, order=order))
    assert info is not None
    assert (info.width, info.height, info.components, info.precision) == (400, 300, 3, 8)
    assert info.orientation == 6
    plain = jpeg_info(jpeg(400, 300))
    assert plain is not None and plain.orientation == 1
    assert jpeg_info(b"not a jpeg") is None
    assert jpeg_info(jpeg()[:20]) is None


def test_a_phone_photo_keeps_its_pixels_turns_the_page_and_drops_its_metadata() -> None:
    data = jpeg(400, 300, orientation=6, scan=b"PIXELS")
    page = jpeg_page(data)
    assert page is not None
    assert (page.width, page.height, page.colors, page.rotate) == (400, 300, 3, 90)
    assert page.filter == "DCTDecode"
    assert b"PIXELS" in page.data and b"JFIF" in page.data
    assert b"GPS-SECRET" not in page.data and b"a comment" not in page.data
    assert strip_jpeg_metadata(page.data) == page.data
    assert jpeg_page(jpeg(orientation=3)).rotate == 180  # type: ignore[union-attr]
    assert jpeg_page(jpeg(orientation=8)).rotate == 270  # type: ignore[union-attr]


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(jpeg(components=4), id="cmyk"),
        pytest.param(jpeg(precision=12), id="12-bit"),
        pytest.param(jpeg(orientation=2), id="mirrored"),
        pytest.param(b"\xff\xd8broken", id="broken"),
    ],
)
def test_jpegs_that_need_decoding_first(data: bytes) -> None:
    assert jpeg_page(data) is None


def test_read_pnm() -> None:
    rgb = b"P6\n# made by vips\n2 1\n255\n" + bytes([255, 0, 0, 0, 0, 255])
    assert read_pnm(rgb) == (2, 1, 3, bytes([255, 0, 0, 0, 0, 255]))
    grey = b"P5 3 1 255\n" + bytes([0, 128, 255])
    assert read_pnm(grey) == (3, 1, 1, bytes([0, 128, 255]))
    page = pnm_page(grey)
    assert (page.width, page.height, page.colors, page.filter) == (3, 1, 1, "FlateDecode")
    with pytest.raises(ValueError, match="8-bit"):
        read_pnm(b"P6 1 1 65535\n" + bytes(6))
    with pytest.raises(ValueError, match="truncated"):
        read_pnm(b"P6 2 2 255\n" + bytes(5))
    with pytest.raises(ValueError):
        read_pnm(b"P3 1 1 255\n255 0 0")


@pytest.mark.parametrize(
    ("size", "page"),
    [
        ((4032, 3024), (793.7, 595.3)),  # a phone photo: fits A4 turned sideways
        ((2480, 3508), (595.2, 841.9)),  # an A4 scan at 300 dpi: A4
        ((64, 64), (48.0, 48.0)),  # an icon: no bigger than at 96 dpi
    ],
)
def test_page_size(size: tuple[int, int], page: tuple[float, float]) -> None:
    width, height = page_size(*size)
    assert (round(width, 1), round(height, 1)) == page


def test_writer_makes_a_well_formed_pdf(tmp_path: Path) -> None:
    out = tmp_path / "pages.pdf"
    with PdfWriter(out) as writer:
        writer.add(jpeg_page(jpeg(400, 300, orientation=6)))  # type: ignore[arg-type]
        writer.add(pnm_page(b"P5 2 2 255\n" + bytes(4)))
        writer.add(PageImage(b"x", 1, 1, 3, "FlateDecode"))
        assert writer.pages == 3
    data = out.read_bytes()
    assert data.startswith(b"%PDF-1.4") and data.rstrip().endswith(b"%%EOF")
    start = int(re.search(rb"startxref\n(\d+)\n", data).group(1))  # type: ignore[union-attr]
    table = data[start:].split(b"trailer")[0].split(b"\n")
    assert table[0] == b"xref"
    count = int(table[1].split()[1])
    for number, line in enumerate(table[3 : 2 + count], start=1):
        offset = int(line[:10])
        assert data[offset:].startswith(f"{number} 0 obj".encode()), number
    assert b"/Count 3" in data and b"/Rotate 90" in data
    if shutil.which("qpdf"):
        pages = subprocess.run(
            ["qpdf", "--show-npages", str(out)], capture_output=True, text=True, check=True
        )
        assert pages.stdout.strip() == "3"


def test_an_aborted_writer_leaves_no_open_file(tmp_path: Path) -> None:
    out = tmp_path / "pages.pdf"
    with pytest.raises(RuntimeError), PdfWriter(out) as writer:
        writer.add(pnm_page(b"P5 1 1 255\n\0"))
        raise RuntimeError("stop")
    assert writer._file.closed
