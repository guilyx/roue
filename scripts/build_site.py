#!/usr/bin/env python3
"""Build the Roue website: landing page + documentation.

    python scripts/build_site.py              # build into website/ (docs in website/docs/)
    python scripts/build_site.py --out _site  # build a deployable copy elsewhere
    python scripts/build_site.py --check      # fail if generated sections are stale

What it does:

1. Regenerates the preset tables in ``docs/presets.md`` and the preset grid in
   ``website/index.html`` (between ``<!-- presets:start -->`` and
   ``<!-- presets:end -->``) from ``src/roue/presets/*.yaml``.
2. Renders every page of ``docs/*.md`` to ``<out>/docs/<page>.html``.
3. Copies the app icon and writes ``sitemap.xml``.

Needs PyYAML and Markdown. Run from a checkout with ``PYTHONPATH=src`` or
from the dev virtualenv (``make site``).
"""

from __future__ import annotations

import argparse
import html
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from roue import __version__  # noqa: E402
from roue.engine.presets import GROUPS, Preset, load_presets  # noqa: E402

DOCS = ROOT / "docs"
WEBSITE = ROOT / "website"
ICONS = ROOT / "src" / "roue" / "data" / "icons"
SITE_URL = "https://guilyx.github.io/roue/"
REPO = "https://github.com/guilyx/roue"
START, END = "<!-- presets:start -->", "<!-- presets:end -->"

#: Documentation pages, in reading order: (file stem, sidebar label).
NAV: list[tuple[str, str]] = [
    ("index", "Overview"),
    ("getting-started", "Getting started"),
    ("install", "Install"),
    ("presets", "Presets"),
    ("custom-presets", "Custom presets"),
    ("cli", "Command line"),
    ("desktop-integration", "Desktop integration"),
    ("privacy", "Privacy"),
    ("faq", "FAQ"),
    ("architecture", "Architecture"),
    ("contributing", "Contributing"),
]

# -- describing presets --------------------------------------------------------

_MIME_NAMES = {
    "image/*": "any image",
    "video/*": "any video",
    "audio/*": "any audio",
    "image/jpeg": "JPG",
    "image/png": "PNG",
    "image/webp": "WebP",
    "image/avif": "AVIF",
    "image/heic": "HEIC",
    "image/heif": "HEIF",
    "image/tiff": "TIFF",
    "image/gif": "GIF",
    "image/svg+xml": "SVG",
    "video/webm": "WebM",
    "audio/mpeg": "MP3",
    "audio/x-wav": "WAV",
    "audio/wav": "WAV",
    "audio/flac": "FLAC",
    "application/pdf": "PDF",
    "application/msword": "DOC",
    "application/rtf": "RTF",
    "application/vnd.ms-*": "old Office files",
    "application/vnd.openxmlformats-officedocument.*": "DOCX/XLSX/PPTX",
    "application/vnd.oasis.opendocument.*": "OpenDocument",
    "application/vnd.oasis.opendocument.text": "ODT",
    "text/markdown": "Markdown",
    "text/x-rst": "reStructuredText",
    "text/org": "Org",
    "text/plain": "plain text",
    "text/csv": "CSV",
    "text/html": "HTML",
}


def _names(patterns: tuple[str, ...]) -> list[str]:
    names: list[str] = []
    for pattern in patterns:
        name = _MIME_NAMES.get(pattern, pattern)
        if name not in names:
            names.append(name)
    return names


def takes(preset: Preset) -> str:
    text = ", ".join(_names(preset.accepts))
    if preset.rejects:
        text += " except " + ", ".join(_names(preset.rejects))
    return text


def gives(preset: Preset) -> str:
    if preset.output == "folder":
        parts = [f"folder of `.{preset.output_ext}`"]
    elif preset.output_ext == "same":
        parts = ["same format"]
    else:
        parts = [f"`.{preset.output_ext}`"]
    if preset.suffix:
        parts.append(f"`{preset.suffix}`")
    if preset.only_if_smaller:
        parts.append("only if smaller")
    return ", ".join(parts)


def short_output(preset: Preset) -> str:
    if preset.output == "folder":
        return f"pages · .{preset.output_ext}"
    return "same" if preset.output_ext == "same" else f".{preset.output_ext}"


def presets_markdown(presets: list[Preset]) -> str:
    out: list[str] = []
    for group, label in GROUPS.items():
        members = [p for p in presets if p.group == group]
        if not members:
            continue
        out += [
            f"### {label}",
            "",
            "| Id | Name | Takes | Gives | What it does |",
            "|---|---|---|---|---|",
        ]
        for p in members:
            row = [f"`{p.id}`", p.name, takes(p), gives(p), p.description]
            out.append("| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def presets_html(presets: list[Preset]) -> str:
    indent = "        "
    out: list[str] = []
    for group, label in GROUPS.items():
        members = [p for p in presets if p.group == group]
        if not members:
            continue
        out.append(f'{indent}<article class="kind kind-{group}">')
        out.append(f'{indent}  <h3><span class="dot" aria-hidden="true"></span>{label}</h3>')
        out.append(f'{indent}  <ul role="list">')
        for p in members:
            out.append(
                f'{indent}    <li title="{html.escape(p.description)}">'
                f'<span class="pname">{html.escape(p.name)}</span>'
                f'<code class="pext">{html.escape(short_output(p))}</code></li>'
            )
        out += [f"{indent}  </ul>", f"{indent}</article>"]
    return "\n".join(out)


def replace_between(text: str, block: str, *, where: str) -> str:
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    if not pattern.search(text):
        raise SystemExit(f"{where}: missing {START} ... {END} markers")
    return pattern.sub(lambda _m: f"{START}\n{block.rstrip()}\n{END}", text, count=1)


# -- rendering docs ------------------------------------------------------------


@dataclass
class Page:
    stem: str
    label: str
    title: str
    body: str
    toc: list[tuple[str, str]]


_LINK_RE = re.compile(r'href="([^"#:]+)\.md(#[^"]*)?"')
_UP_RE = re.compile(r'href="\.\./([^"]+)"')


def _rewrite_links(body: str) -> str:
    body = _UP_RE.sub(lambda m: f'href="{REPO}/blob/main/{m.group(1)}"', body)
    return _LINK_RE.sub(lambda m: f'href="{m.group(1)}.html{m.group(2) or ""}"', body)


def render_page(stem: str, label: str) -> Page:
    source = (DOCS / f"{stem}.md").read_text(encoding="utf-8")
    title_match = re.search(r"^# (.+)$", source, re.M)
    title = title_match.group(1).strip() if title_match else label
    source = source.replace(title_match.group(0), "", 1) if title_match else source
    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "sane_lists", "toc"],
        extension_configs={
            "toc": {"permalink": "#", "permalink_class": "anchor", "toc_depth": "2-3"}
        },
    )
    body = _rewrite_links(md.convert(source))
    body = body.replace(
        "<table>", '<div class="table-wrap" tabindex="0" role="region" aria-label="Table"><table>'
    ).replace("</table>", "</table></div>")
    toc = [(t["id"], t["name"]) for t in getattr(md, "toc_tokens", []) if t.get("level") == 2]
    return Page(stem, label, title, body, toc)


ICON_SVG = '<img src="../assets/icon.svg" alt="" width="28" height="28">'


def docs_template(page: Page, pages: list[Page]) -> str:
    index = [p.stem for p in pages].index(page.stem)
    prev_page = pages[index - 1] if index > 0 else None
    next_page = pages[index + 1] if index + 1 < len(pages) else None

    def nav_items() -> str:
        items = []
        for p in pages:
            current = ' aria-current="page"' if p.stem == page.stem else ""
            items.append(f'<li><a href="{p.stem}.html"{current}>{html.escape(p.label)}</a></li>')
        return "\n          ".join(items)

    toc = ""
    if len(page.toc) > 1:
        links = "\n".join(
            f'          <li><a href="#{anchor}">{html.escape(html.unescape(name))}</a></li>'
            for anchor, name in page.toc
        )
        toc = (
            '      <aside class="docs-toc" aria-label="On this page">\n'
            '        <p>On this page</p>\n        <ul role="list">\n'
            f"{links}\n        </ul>\n      </aside>\n"
        )
    pager = []
    if prev_page:
        pager.append(
            f'<a class="prev" href="{prev_page.stem}.html"><span>Previous</span>'
            f"{html.escape(prev_page.label)}</a>"
        )
    if next_page:
        pager.append(
            f'<a class="next" href="{next_page.stem}.html"><span>Next</span>'
            f"{html.escape(next_page.label)}</a>"
        )
    title = "Roue documentation" if page.stem == "index" else f"{page.title} · Roue docs"
    first = re.search(r"<p>(.*?)</p>", page.body, re.S)
    description = " ".join(re.sub(r"<[^>]+>", "", first.group(1) if first else page.title).split())
    description = html.unescape(description)[:180]
    url = f"{SITE_URL}docs/{page.stem}.html"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <meta name="description" content="{html.escape(description)}">
  <link rel="canonical" href="{url}">
  <meta property="og:type" content="article">
  <meta property="og:title" content="{html.escape(title)}">
  <meta property="og:description" content="{html.escape(description)}">
  <meta property="og:url" content="{url}">
  <meta property="og:image" content="{SITE_URL}assets/icon-512.png">
  <meta name="theme-color" content="#fbfaf8" media="(prefers-color-scheme: light)">
  <meta name="theme-color" content="#141218" media="(prefers-color-scheme: dark)">
  <link rel="icon" href="../assets/icon.svg" type="image/svg+xml">
  <link rel="apple-touch-icon" href="../assets/icon-512.png">
  <link rel="stylesheet" href="../assets/style.css">
  <script src="../assets/site.js" defer></script>
</head>
<body class="docs">
  <a class="skip" href="#main">Skip to content</a>
  <header class="site-header">
    <div class="wrap header-row">
      <a class="brand" href="../index.html">{ICON_SVG}<span>Roue</span></a>
      <nav class="top-nav" aria-label="Site">
        <a href="index.html" aria-current="true">Docs</a>
        <a href="presets.html" class="hide-sm">Presets</a>
        <a href="{REPO}">GitHub</a>
      </nav>
    </div>
  </header>
  <div class="wrap docs-layout">
    <nav class="docs-nav" aria-label="Documentation">
      <details class="docs-menu">
        <summary>Documentation menu</summary>
        <ul role="list">
          {nav_items()}
        </ul>
      </details>
      <ul role="list" class="docs-list">
          {nav_items()}
      </ul>
    </nav>
    <main id="main" class="docs-main">
      <article class="prose">
        <h1>{html.escape(page.title)}</h1>
{page.body}
      </article>
      <nav class="pager" aria-label="Pages">{"".join(pager)}</nav>
      <p class="edit-link">
        <a href="{REPO}/edit/main/docs/{page.stem}.md">Edit this page on GitHub</a>
      </p>
    </main>
{toc}  </div>
  <footer class="site-footer">
    <div class="wrap footer-row">
      <p>Roue {__version__} · Free software under the
        <a href="{REPO}/blob/main/LICENSE">GPL-3.0-or-later</a> ·
        Your files never leave your computer.</p>
    </div>
  </footer>
</body>
</html>
"""


def sitemap(pages: list[Page]) -> str:
    urls = [SITE_URL] + [f"{SITE_URL}docs/{p.stem}.html" for p in pages]
    entries = "\n".join(f"  <url><loc>{u}</loc></url>" for u in urls)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{entries}\n</urlset>\n"
    )


# -- main ------------------------------------------------------------------------


def refresh_sources(*, check: bool) -> list[str]:
    """Update generated sections in tracked files. Returns the stale ones."""
    presets = list(load_presets(include_user=False))
    stale = []
    targets = [
        (DOCS / "presets.md", presets_markdown(presets)),
        (WEBSITE / "index.html", presets_html(presets)),
    ]
    for path, block in targets:
        text = path.read_text(encoding="utf-8")
        updated = replace_between(text, block, where=str(path.relative_to(ROOT)))
        if updated != text:
            stale.append(str(path.relative_to(ROOT)))
            if not check:
                path.write_text(updated, encoding="utf-8")
    icon_src, icon_dst = ICONS / "io.github.guilyx.Roue.svg", WEBSITE / "assets" / "icon.svg"
    if not icon_dst.exists() or icon_dst.read_bytes() != icon_src.read_bytes():
        stale.append(str(icon_dst.relative_to(ROOT)))
        if not check:
            shutil.copyfile(icon_src, icon_dst)
    return stale


def build(out: Path) -> int:
    out = out.resolve()
    if out != WEBSITE.resolve():
        if out.exists():
            shutil.rmtree(out)
        shutil.copytree(WEBSITE, out, ignore=shutil.ignore_patterns("docs", ".gitignore"))
    docs_out = out / "docs"
    docs_out.mkdir(parents=True, exist_ok=True)
    pages = [render_page(stem, label) for stem, label in NAV]
    missing = sorted({p.stem for p in DOCS.glob("*.md")} - {stem for stem, _ in NAV})
    if missing:
        print(f"warning: docs not in the navigation: {', '.join(missing)}", file=sys.stderr)
    for page in pages:
        (docs_out / f"{page.stem}.html").write_text(docs_template(page, pages), encoding="utf-8")
    (out / "sitemap.xml").write_text(sitemap(pages), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    return len(pages)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out", type=Path, default=WEBSITE, help="output folder (default: website/)"
    )
    parser.add_argument("--check", action="store_true", help="fail if generated sections are stale")
    args = parser.parse_args()
    stale = refresh_sources(check=args.check)
    if args.check:
        if stale:
            print("Out of date (run: make site): " + ", ".join(stale), file=sys.stderr)
            return 1
        print("Generated sections are up to date.")
        return 0
    for path in stale:
        print(f"updated {path}")
    count = build(args.out)
    print(f"Built {count} docs pages into {args.out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
