"""
glossary_manager.py — Quản lý Thuật ngữ & Tài liệu Tham khảo
Hỗ trợ thêm/xóa/sửa thuật ngữ, import/export file, và xử lý pre/post dịch.
"""

import json
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GlossaryEntry:
    """Một mục thuật ngữ."""
    source: str       # Thuật ngữ gốc (EN/JA)
    target: str       # Thuật ngữ dịch (VI)
    case_sensitive: bool = False
    notes: str = ""   # Ghi chú (tùy chọn)


class GlossaryManager:
    """Quản lý danh sách thuật ngữ và xử lý thay thế trong quá trình dịch."""

    PLACEHOLDER_PREFIX = "⟦TERM_"
    PLACEHOLDER_SUFFIX = "⟧"

    def __init__(self, storage_path: Optional[Path] = None):
        self.entries: dict[str, GlossaryEntry] = {}
        self.storage_path = storage_path or Path("storage/glossary.json")
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._load()

    # ──────────────────────────────────────────
    #  CRUD Operations
    # ──────────────────────────────────────────
    def add(self, source: str, target: str, case_sensitive: bool = False, notes: str = "") -> GlossaryEntry:
        """Thêm hoặc cập nhật thuật ngữ."""
        entry = GlossaryEntry(
            source=source.strip(),
            target=target.strip(),
            case_sensitive=case_sensitive,
            notes=notes,
        )
        key = source.strip().lower() if not case_sensitive else source.strip()
        self.entries[key] = entry
        self._save()
        return entry

    def remove(self, source: str) -> bool:
        """Xóa thuật ngữ. Trả về True nếu tìm thấy và xóa."""
        key_lower = source.strip().lower()
        key_exact = source.strip()
        if key_exact in self.entries:
            del self.entries[key_exact]
            self._save()
            return True
        if key_lower in self.entries:
            del self.entries[key_lower]
            self._save()
            return True
        return False

    def get_all(self) -> list[dict]:
        """Lấy tất cả thuật ngữ dưới dạng list of dicts."""
        return [
            {
                "source": e.source,
                "target": e.target,
                "case_sensitive": e.case_sensitive,
                "notes": e.notes,
            }
            for e in self.entries.values()
        ]

    def clear(self):
        """Xóa toàn bộ thuật ngữ."""
        self.entries.clear()
        self._save()

    def count(self) -> int:
        return len(self.entries)

    # ──────────────────────────────────────────
    #  Pre/Post Processing for Translation
    # ──────────────────────────────────────────
    def find_terms(self, text: str) -> list[tuple[str, str]]:
        """
        Trả về các cặp (thuật ngữ gốc, bản dịch) có xuất hiện trong text.

        Dùng cho model instruct: thay vì chèn placeholder vào giữa câu (model
        sinh ngôn ngữ sẽ nuốt mất), engine liệt kê thuật ngữ ngay trong prompt.
        Sắp xếp theo độ dài giảm dần để thuật ngữ dài được nêu trước.
        """
        found: list[tuple[str, str]] = []
        for entry in sorted(self.entries.values(),
                            key=lambda e: len(e.source), reverse=True):
            if entry.case_sensitive:
                hit = entry.source in text
            else:
                hit = entry.source.lower() in text.lower()
            if hit:
                found.append((entry.source, entry.target))
        return found

    def pre_process(self, text: str) -> tuple[str, dict[str, str]]:
        """
        Thay thế thuật ngữ gốc bằng placeholder trước khi dịch.
        Trả về (text_đã_thay, mapping placeholder -> thuật ngữ dịch).
        """
        mapping: dict[str, str] = {}

        # Sắp xếp theo độ dài giảm dần để xử lý thuật ngữ dài trước
        sorted_entries = sorted(
            self.entries.values(),
            key=lambda e: len(e.source),
            reverse=True,
        )

        for idx, entry in enumerate(sorted_entries):
            placeholder = f"{self.PLACEHOLDER_PREFIX}{idx:03d}{self.PLACEHOLDER_SUFFIX}"

            if entry.case_sensitive:
                pattern = re.escape(entry.source)
            else:
                pattern = re.compile(re.escape(entry.source), re.IGNORECASE)

            if isinstance(pattern, str):
                if entry.source in text:
                    text = text.replace(entry.source, placeholder)
                    mapping[placeholder] = entry.target
            else:
                if pattern.search(text):
                    text = pattern.sub(placeholder, text)
                    mapping[placeholder] = entry.target

        return text, mapping

    def post_process(self, translated: str, mapping: dict[str, str]) -> str:
        """Thay placeholder trở lại thành thuật ngữ tiếng Việt sau khi dịch."""
        for placeholder, target in mapping.items():
            translated = translated.replace(placeholder, target)
        return translated

    # ──────────────────────────────────────────
    #  Import / Export
    # ──────────────────────────────────────────
    def import_json(self, json_str: str) -> int:
        """Import glossary từ chuỗi JSON. Trả về số mục đã import."""
        data = json.loads(json_str)
        count = 0

        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and "source" in item and "target" in item:
                    self.add(
                        source=item["source"],
                        target=item["target"],
                        case_sensitive=item.get("case_sensitive", False),
                        notes=item.get("notes", ""),
                    )
                    count += 1
        elif isinstance(data, dict):
            for source, target in data.items():
                self.add(source=source, target=target)
                count += 1

        return count

    def import_txt(self, txt_content: str) -> int:
        """
        Import glossary từ chuỗi TXT.
        Format: mỗi dòng là `source = target` hoặc `source: target`
        Trả về số mục đã import.
        """
        count = 0
        for line in txt_content.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Thử tách bằng " = " hoặc ": " hoặc "\t"
            for sep in [" = ", " =", "= ", "=", ": ", ":", "\t"]:
                if sep in line:
                    parts = line.split(sep, 1)
                    if len(parts) == 2:
                        source, target = parts[0].strip(), parts[1].strip()
                        if source and target:
                            self.add(source=source, target=target)
                            count += 1
                    break

        return count

    def export_json(self) -> str:
        """Xuất glossary ra chuỗi JSON."""
        return json.dumps(self.get_all(), ensure_ascii=False, indent=2)

    def export_txt(self) -> str:
        """Xuất glossary ra chuỗi TXT (format: source = target)."""
        lines = []
        for entry in self.entries.values():
            lines.append(f"{entry.source} = {entry.target}")
        return "\n".join(lines)

    # ──────────────────────────────────────────
    #  Persistence
    # ──────────────────────────────────────────
    def _save(self):
        """Lưu glossary ra file JSON."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = self.get_all()
        self.storage_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load(self):
        """Tải glossary từ file JSON nếu tồn tại."""
        if self.storage_path.exists():
            try:
                content = self.storage_path.read_text(encoding="utf-8")
                self.import_json(content)
            except (json.JSONDecodeError, Exception):
                pass  # File lỗi, bỏ qua
