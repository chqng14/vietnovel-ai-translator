"""
translate.py — Script CLI dịch truyện độc lập
Sử dụng: python translate.py --url <URL> --output <file.md>
         python translate.py --text "nội dung" --output <file.txt>
"""

import argparse
import sys
import time

from scraper import scrape_chapter, parse_direct_text
from glossary_manager import GlossaryManager
from translate_engine import (
    TranslationEngine,
    DEFAULT_MODEL,
    DEEP_TRANSLATOR_GOOGLE,
)
from exporter import export_markdown, export_epub, export_txt


def format_time(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins}m {secs}s"


def main():
    parser = argparse.ArgumentParser(
        description="🔮 Novel Translator CLI — Dịch truyện tự động bằng NiuTrans AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ví dụ:
  python translate.py --url https://witchculttranslation.com/... --output chapter.md
  python translate.py --url https://ncode.syosetu.com/... --format epub
  python translate.py --text "Hello world" --output test.txt
  python translate.py --url <URL> --glossary glossary.json --format epub
        """,
    )

    # Input source
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--url", help="URL chương truyện cần dịch")
    input_group.add_argument("--text", help="Văn bản trực tiếp cần dịch")
    input_group.add_argument("--file", help="File văn bản cần dịch")

    # Output
    parser.add_argument("--output", "-o", help="Tên file output (tự động đặt nếu bỏ trống)")
    parser.add_argument("--format", "-f", choices=["md", "epub", "txt"], default="md",
                        help="Định dạng output (mặc định: md)")

    # Options
    parser.add_argument("--glossary", "-g", help="File glossary (JSON hoặc TXT)")
    parser.add_argument("--lang", choices=["en", "ja"], default="en",
                        help="Ngôn ngữ nguồn (mặc định: en)")
    parser.add_argument("--bilingual", action="store_true",
                        help="Xuất song ngữ (nguyên tác + bản dịch)")
    parser.add_argument("--title", help="Tiêu đề chương (cho --text và --file)")
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=(
            "Model/provider dịch. Dùng 'deep-translator/google' để dịch qua "
            "Google Translate mà không cần GPU"
        ),
    )
    parser.add_argument(
        "--context",
        default="",
        help="Mô tả ngắn về bối cảnh, nhân vật và văn phong của truyện",
    )

    args = parser.parse_args()

    print("═" * 60)
    print(f"📖  Novel Translator CLI — {args.model}")
    print("═" * 60)

    # ── Load glossary ──
    glossary = GlossaryManager()
    if args.glossary:
        from pathlib import Path
        gfile = Path(args.glossary)
        if gfile.exists():
            content = gfile.read_text(encoding="utf-8")
            if gfile.suffix == ".json":
                count = glossary.import_json(content)
            else:
                count = glossary.import_txt(content)
            print(f"📚 Đã nạp {count} thuật ngữ từ {args.glossary}")
        else:
            print(f"⚠️  Không tìm thấy file glossary: {args.glossary}")

    # ── Get chapter data ──
    print()
    if args.url:
        print(f"🔗 Đang trích xuất từ: {args.url}")
        chapter = scrape_chapter(args.url)
        print(f"📄 Tiêu đề: {chapter.title}")
        print(f"📝 Số đoạn: {len(chapter.paragraphs)}")
        print(f"🌐 Ngôn ngữ: {chapter.source_lang.upper()}")
    elif args.text:
        title = args.title or "Direct Input"
        chapter = parse_direct_text(args.text, title, args.lang)
        print(f"📋 Đã nhận văn bản trực tiếp — {len(chapter.paragraphs)} đoạn")
    elif args.file:
        from pathlib import Path
        fpath = Path(args.file)
        if not fpath.exists():
            print(f"❌ Không tìm thấy file: {args.file}")
            sys.exit(1)
        text = fpath.read_text(encoding="utf-8")
        title = args.title or fpath.stem
        chapter = parse_direct_text(text, title, args.lang)
        print(f"📁 Đã đọc file: {args.file} — {len(chapter.paragraphs)} đoạn")

    if not chapter.paragraphs:
        print("❌ Không tìm thấy đoạn văn nào!")
        sys.exit(1)

    # ── Translate ──
    print()
    print("⚡ Bắt đầu dịch...")
    print("─" * 60)

    engine = TranslationEngine(glossary=glossary)
    total = len(chapter.paragraphs)
    translated = []

    # Chuẩn bị model hoặc thư viện dịch trước khi bắt đầu.
    preparing = (
        "Đang kết nối Google Translate..."
        if args.model == DEEP_TRANSLATOR_GOOGLE
        else "Đang nạp model..."
    )
    print(f"  ⏳ {preparing}", end="", flush=True)
    engine._load_model(args.model)
    print(" xong!")
    start_time = time.time()

    batch = max(1, engine.batch_size)
    for batch_start in range(0, total, batch):
        chunk = chapter.paragraphs[batch_start: batch_start + batch]

        # Đoạn phân cách ("***", "---") giữ nguyên, không tốn một lượt generate
        need = [t for t in chunk if engine._needs_translation(t)]
        done = {}
        if need:
            results = engine.translate_batch(
                need,
                chapter.source_lang,
                args.model,
                args.context,
            )
            done = dict(zip(need, results))
        translated.extend(done.get(t, t) for t in chunk)

        idx = len(translated) - 1
        elapsed = time.time() - start_time
        speed = (idx + 1) / elapsed if elapsed > 0 else 0
        remaining = (total - idx - 1) / speed if speed > 0 else 0

        # Progress display
        pct = (idx + 1) / total * 100
        bar_width = 30
        filled = int(bar_width * (idx + 1) / total)
        bar = "█" * filled + "░" * (bar_width - filled)

        print(f"\r  [{bar}] {pct:5.1f}%  {idx+1}/{total}  "
              f"⚡{speed:.2f}/s  ⏱️ETA: {format_time(remaining)}", end="", flush=True)

    total_time = time.time() - start_time
    print()
    print("─" * 60)
    print(f"✅ Hoàn thành! {total} đoạn trong {format_time(total_time)}")

    # ── Export ──
    print()
    fmt = args.format
    if fmt == "md":
        path = export_markdown(
            title=chapter.title,
            paragraphs_original=chapter.paragraphs,
            paragraphs_translated=translated,
            source_url=chapter.source_url,
            source_lang=chapter.source_lang,
            bilingual=args.bilingual,
        )
    elif fmt == "epub":
        path = export_epub(
            title=chapter.title,
            paragraphs_original=chapter.paragraphs,
            paragraphs_translated=translated,
            source_url=chapter.source_url,
            source_lang=chapter.source_lang,
            bilingual=args.bilingual,
        )
    elif fmt == "txt":
        path = export_txt(
            title=chapter.title,
            paragraphs_translated=translated,
            source_url=chapter.source_url,
        )

    print(f"📦 File đã xuất: {path}")
    print()
    print("═" * 60)
    print("🎉 Done!")


if __name__ == "__main__":
    main()
