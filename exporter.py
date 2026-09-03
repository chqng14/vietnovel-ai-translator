"""
exporter.py — Module xuất bản dịch ra file Markdown, EPUB, TXT
Hỗ trợ tạo file sách với định dạng chuẩn cho máy đọc sách.
"""

import re
from pathlib import Path
from datetime import datetime
from typing import Optional

from ebooklib import epub


STORAGE_DIR = Path("storage")
STORAGE_DIR.mkdir(exist_ok=True)


def _sanitize_filename(name: str) -> str:
    """Loại bỏ ký tự không hợp lệ trong tên file."""
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = re.sub(r"\s+", "_", name.strip())
    return name[:100] if name else "untitled"


# ──────────────────────────────────────────────
#  Markdown Export
# ──────────────────────────────────────────────
def export_markdown(
    title: str,
    paragraphs_original: list[str],
    paragraphs_translated: list[str],
    source_url: str = "",
    source_lang: str = "en",
    bilingual: bool = False,
) -> Path:
    """
    Xuất bản dịch ra file Markdown (.md) với YAML frontmatter.
    Nếu bilingual=True, hiển thị cả nguyên tác và bản dịch.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    safe_name = _sanitize_filename(title)
    filepath = STORAGE_DIR / f"{safe_name}.md"

    lines = [
        "---",
        f"title: \"{title}\"",
        f"source_url: \"{source_url}\"",
        f"source_language: \"{source_lang}\"",
        f"translated_date: \"{timestamp}\"",
        f"translator: \"NiuTrans/LMT-60-1.7B\"",
        "---",
        "",
        f"# {title}",
        "",
    ]

    for i, translated in enumerate(paragraphs_translated):
        if bilingual and i < len(paragraphs_original):
            # Hiển thị nguyên tác ở dạng blockquote
            lines.append(f"> {paragraphs_original[i]}")
            lines.append("")

        lines.append(translated)
        lines.append("")

    content = "\n".join(lines)
    filepath.write_text(content, encoding="utf-8")
    return filepath


# ──────────────────────────────────────────────
#  TXT Export
# ──────────────────────────────────────────────
def export_txt(
    title: str,
    paragraphs_translated: list[str],
    source_url: str = "",
) -> Path:
    """Xuất bản dịch ra file TXT đơn giản."""
    safe_name = _sanitize_filename(title)
    filepath = STORAGE_DIR / f"{safe_name}.txt"

    lines = [
        title,
        "=" * len(title),
        "",
    ]

    if source_url:
        lines.append(f"Nguồn: {source_url}")
        lines.append("")

    lines.append(f"Ngày dịch: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("-" * 40)
    lines.append("")

    for p in paragraphs_translated:
        lines.append(p)
        lines.append("")

    content = "\n".join(lines)
    filepath.write_text(content, encoding="utf-8")
    return filepath


# ──────────────────────────────────────────────
#  EPUB Export
# ──────────────────────────────────────────────

# CSS cho sách điện tử
EPUB_CSS = """
@charset "utf-8";
body {
    font-family: "Noto Serif", "Georgia", serif;
    line-height: 1.8;
    color: #2c2c2c;
    margin: 1em;
    padding: 0;
}
h1 {
    font-size: 1.6em;
    font-weight: 700;
    text-align: center;
    margin: 1.5em 0 1em 0;
    color: #1a1a2e;
    border-bottom: 2px solid #6c63ff;
    padding-bottom: 0.5em;
}
p {
    text-align: justify;
    text-indent: 1.5em;
    margin: 0.6em 0;
    font-size: 1em;
}
blockquote {
    font-style: italic;
    color: #555;
    border-left: 3px solid #6c63ff;
    padding-left: 1em;
    margin: 1em 0;
}
.meta {
    text-align: center;
    color: #888;
    font-size: 0.85em;
    margin: 1em 0 2em 0;
}
"""


def export_epub(
    title: str,
    paragraphs_original: list[str],
    paragraphs_translated: list[str],
    source_url: str = "",
    source_lang: str = "en",
    author: str = "NiuTrans/LMT-60-1.7B",
    bilingual: bool = False,
) -> Path:
    """
    Xuất bản dịch ra file EPUB chuẩn cho máy đọc sách.
    Bao gồm bìa, mục lục, CSS đọc sách đẹp.
    """
    safe_name = _sanitize_filename(title)
    filepath = STORAGE_DIR / f"{safe_name}.epub"

    book = epub.EpubBook()

    # ── Metadata ──
    book.set_identifier(f"novel-translator-{safe_name}-{datetime.now().strftime('%Y%m%d%H%M%S')}")
    book.set_title(title)
    book.set_language("vi")
    book.add_author(author)
    book.add_metadata("DC", "description", f"Bản dịch tự động từ {source_url}")
    book.add_metadata("DC", "source", source_url)

    # ── CSS ──
    css_item = epub.EpubItem(
        uid="style",
        file_name="style/default.css",
        media_type="text/css",
        content=EPUB_CSS.encode("utf-8"),
    )
    book.add_item(css_item)

    # ── Title Page ──
    title_html = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>{title}</title><link rel="stylesheet" href="style/default.css"/></head>
<body>
<h1>{title}</h1>
<p class="meta">Dịch bởi: {author}</p>
<p class="meta">Ngày dịch: {datetime.now().strftime('%d/%m/%Y')}</p>
{"<p class='meta'>Nguồn: " + source_url + "</p>" if source_url else ""}
</body>
</html>"""

    title_page = epub.EpubHtml(
        title="Trang bìa",
        file_name="title.xhtml",
        lang="vi",
    )
    title_page.content = title_html.encode("utf-8")
    title_page.add_item(css_item)
    book.add_item(title_page)

    # ── Chapter Content ──
    body_parts = []
    for i, translated in enumerate(paragraphs_translated):
        escaped_translated = translated.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        if bilingual and i < len(paragraphs_original):
            escaped_original = paragraphs_original[i].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            body_parts.append(f"<blockquote>{escaped_original}</blockquote>")

        body_parts.append(f"<p>{escaped_translated}</p>")

    chapter_html = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>{title}</title><link rel="stylesheet" href="style/default.css"/></head>
<body>
<h1>{title}</h1>
{"".join(body_parts)}
</body>
</html>"""

    chapter = epub.EpubHtml(
        title=title,
        file_name="chapter_01.xhtml",
        lang="vi",
    )
    chapter.content = chapter_html.encode("utf-8")
    chapter.add_item(css_item)
    book.add_item(chapter)

    # ── Table of Contents & Spine ──
    book.toc = [
        epub.Link("title.xhtml", "Trang bìa", "title"),
        epub.Link("chapter_01.xhtml", title, "chapter_01"),
    ]

    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    book.spine = ["nav", title_page, chapter]

    # ── Write file ──
    epub.write_epub(str(filepath), book, {})
    return filepath
