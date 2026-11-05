"""Images as PDF pages, written with the standard library only.

JPEGs go in as they are (``DCTDecode``): no re-encoding, no quality lost.
Their metadata segments are left out on the way, so a photo's location
doesn't end up in the PDF, and the EXIF orientation becomes the page's
rotation. Other images arrive here already decoded to 8-bit PGM or PPM and
are stored losslessly with zlib (``FlateDecode``).

Each page has the image's own shape, scaled to fit an A4 sheet turned the
same way as the image, and never larger than the image at 96 dpi, so small
pictures stay small.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import BinaryIO, Literal, NamedTuple

#: A4 in points (1/72 inch), portrait.
A4 = (595.276, 841.89)
#: Points per pixel at most: pictures are never shown larger than at 96 dpi.
MAX_SCALE = 72 / 96

#: EXIF orientations a page rotation can show (the mirrored ones can't).
ROTATION = {1: 0, 3: 180, 6: 90, 8: 270}

_SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
_STANDALONE = {0x01, 0xD8, *range(0xD0, 0xD8)}
#: Segments left out of embedded JPEGs: EXIF and XMP, Photoshop data, comments.
_PRIVATE = {0xE1, 0xED, 0xFE}
_WHITESPACE = b" \t\r\n\v\f"
_BYTE_ORDER: dict[bytes, Literal["little", "big"]] = {b"II": "little", b"MM": "big"}


@dataclass(frozen=True)
class PageImage:
    """One page's picture, ready to embed."""

    data: bytes
    width: int
    height: int
    colors: int  # 1 (grey) or 3 (RGB)
    filter: str  # "DCTDecode" or "FlateDecode"
    rotate: int = 0  # degrees clockwise


class JpegInfo(NamedTuple):
    width: int
    height: int
    components: int
    precision: int
    orientation: int


def page_size(width: int, height: int) -> tuple[float, float]:
    """The page for an image: its shape, fitted to A4, at most 96 dpi."""
    box_w, box_h = A4 if height >= width else (A4[1], A4[0])
    scale = min(box_w / width, box_h / height, MAX_SCALE)
    return width * scale, height * scale


def _segments(data: bytes) -> list[tuple[int, int, int]]:
    """``(marker, start, end)`` of each segment before the image data."""
    if data[:2] != b"\xff\xd8":
        raise ValueError("not a JPEG")
    found = []
    i = 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            raise ValueError("broken JPEG")
        marker = data[i + 1]
        if marker == 0xFF:  # fill byte
            i += 1
            continue
        if marker in _STANDALONE:
            i += 2
            continue
        end = i + 2 + int.from_bytes(data[i + 2 : i + 4], "big")
        found.append((marker, i, end))
        if marker == 0xDA:  # start of scan: image data follows
            return found
        i = end
    raise ValueError("truncated JPEG")


def _exif_orientation(tiff: bytes) -> int:
    order = _BYTE_ORDER.get(tiff[:2])
    if order is None:
        return 1
    ifd = int.from_bytes(tiff[4:8], order)
    count = int.from_bytes(tiff[ifd : ifd + 2], order)
    for k in range(count):
        entry = tiff[ifd + 2 + 12 * k : ifd + 14 + 12 * k]
        if len(entry) < 12:
            break
        if int.from_bytes(entry[:2], order) == 0x0112:
            value = int.from_bytes(entry[8:10], order)
            return value if 1 <= value <= 8 else 1
    return 1


def jpeg_info(data: bytes) -> JpegInfo | None:
    """Size, colour components and EXIF orientation of a JPEG, or None."""
    try:
        segments = _segments(data)
    except ValueError:
        return None
    orientation = 1
    for marker, start, end in segments:
        body = data[start + 4 : end]
        if marker == 0xE1 and body.startswith(b"Exif\0\0"):
            orientation = _exif_orientation(body[6:])
        elif marker in _SOF and len(body) >= 6:
            height = int.from_bytes(body[1:3], "big")
            width = int.from_bytes(body[3:5], "big")
            if not width or not height:
                return None
            return JpegInfo(width, height, body[5], body[0], orientation)
    return None


def strip_jpeg_metadata(data: bytes) -> bytes:
    """The same JPEG without its EXIF, XMP, Photoshop and comment segments."""
    segments = _segments(data)
    kept = [data[start:end] for marker, start, end in segments[:-1] if marker not in _PRIVATE]
    scan_start = segments[-1][1]
    return b"".join([b"\xff\xd8", *kept, data[scan_start:]])


def read_pnm(data: bytes) -> tuple[int, int, int, bytes]:
    """``(width, height, colours, pixels)`` of an 8-bit binary PGM or PPM."""
    colors = {b"P5": 1, b"P6": 3}.get(data[:2])
    if colors is None:
        raise ValueError("not a binary PGM or PPM")
    fields: list[int] = []
    pos = 2
    while len(fields) < 3:
        while pos < len(data) and data[pos] in _WHITESPACE:
            pos += 1
        if data[pos : pos + 1] == b"#":
            pos = data.index(b"\n", pos) + 1
            continue
        start = pos
        while pos < len(data) and data[pos] not in _WHITESPACE:
            pos += 1
        fields.append(int(data[start:pos]))
    width, height, maxval = fields
    if maxval != 255:
        raise ValueError("not 8-bit")
    pos += 1  # the one whitespace byte after maxval
    size = width * height * colors
    pixels = data[pos : pos + size]
    if len(pixels) != size:
        raise ValueError("truncated image")
    return width, height, colors, pixels


def jpeg_page(data: bytes) -> PageImage | None:
    """A page that embeds this JPEG untouched, or None if it needs decoding.

    CMYK, 12-bit and mirrored JPEGs return None: they're re-encoded first.
    """
    info = jpeg_info(data)
    if (
        info is None
        or info.precision != 8
        or info.components not in (1, 3)
        or info.orientation not in ROTATION
    ):
        return None
    return PageImage(
        strip_jpeg_metadata(data),
        info.width,
        info.height,
        info.components,
        "DCTDecode",
        ROTATION[info.orientation],
    )


def pnm_page(data: bytes) -> PageImage:
    """A lossless page from an 8-bit PGM or PPM."""
    width, height, colors, pixels = read_pnm(data)
    return PageImage(zlib.compress(pixels, 6), width, height, colors, "FlateDecode")


class PdfWriter:
    """A minimal PDF with one image per page, written as pages are added."""

    def __init__(self, path: Path):
        self._file: BinaryIO = path.open("wb")
        self._offsets: dict[int, int] = {}
        self._pages: list[int] = []
        self._next = 3  # 1 is the catalog, 2 the page tree
        self._file.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

    def __enter__(self) -> PdfWriter:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if kind is None:
            self.close()
        else:
            self.abort()

    @property
    def pages(self) -> int:
        return len(self._pages)

    def _number(self) -> int:
        number = self._next
        self._next += 1
        return number

    def _object(self, number: int, body: str, stream: bytes | None = None) -> None:
        self._offsets[number] = self._file.tell()
        self._file.write(f"{number} 0 obj\n{body}".encode())
        if stream is not None:
            self._file.write(b"\nstream\n" + stream + b"\nendstream")
        self._file.write(b"\nendobj\n")

    def add(self, image: PageImage) -> None:
        picture, content, page = self._number(), self._number(), self._number()
        space = "/DeviceGray" if image.colors == 1 else "/DeviceRGB"
        self._object(
            picture,
            f"<< /Type /XObject /Subtype /Image /Width {image.width} /Height {image.height}"
            f" /ColorSpace {space} /BitsPerComponent 8 /Filter /{image.filter}"
            f" /Length {len(image.data)} >>",
            image.data,
        )
        width, height = page_size(image.width, image.height)
        draw = f"q {width:.3f} 0 0 {height:.3f} 0 0 cm /Im0 Do Q".encode()
        self._object(content, f"<< /Length {len(draw)} >>", draw)
        rotate = f" /Rotate {image.rotate}" if image.rotate else ""
        self._object(
            page,
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width:.3f} {height:.3f}]{rotate}"
            f" /Resources << /XObject << /Im0 {picture} 0 R >> >> /Contents {content} 0 R >>",
        )
        self._pages.append(page)

    def abort(self) -> None:
        """Stop without finishing the file (it isn't a valid PDF then)."""
        self._file.close()

    def close(self) -> None:
        kids = " ".join(f"{page} 0 R" for page in self._pages)
        self._object(2, f"<< /Type /Pages /Kids [{kids}] /Count {len(self._pages)} >>")
        self._object(1, "<< /Type /Catalog /Pages 2 0 R >>")
        start = self._file.tell()
        size = self._next
        table = [f"xref\n0 {size}\n", "0000000000 65535 f \n"]
        table += [f"{self._offsets[n]:010d} 00000 n \n" for n in range(1, size)]
        self._file.write("".join(table).encode())
        self._file.write(
            f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode()
        )
        self._file.close()
