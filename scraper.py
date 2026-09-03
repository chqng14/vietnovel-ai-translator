"""
scraper.py — Web Novel Scraper
Trích xuất tiêu đề và nội dung chương từ các trang web truyện phổ biến.
Hỗ trợ: Witch Cult Translations, Syosetu, Kakuyomu, RoyalRoad, WordPress generic.
"""

import re
import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse


@dataclass
class ChapterData:
    """Dữ liệu chương truyện đã trích xuất."""
    title: str
    paragraphs: list[str]
    source_url: str
    source_lang: str = "en"  # "en" hoặc "ja"
    raw_html: Optional[str] = None


# ──────────────────────────────────────────────
#  Base Parser
# ──────────────────────────────────────────────
class BaseParser:
    """Parser cơ sở — fallback cho mọi domain chưa biết."""

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/130.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    # Các selector CSS phổ biến cho nội dung bài viết
    CONTENT_SELECTORS = [
        "article .entry-content",
        ".entry-content",
        ".post-content",
        "article .content",
        ".chapter-content",
        ".story-content",
        "#chapter-content",
        "article",
        ".post-body",
        "main",
    ]

    # Các selector cần loại bỏ
    REMOVE_SELECTORS = [
        "script", "style", "noscript", "iframe",
        ".sharedaddy", ".sd-sharing", ".share-buttons",
        ".navigation", ".post-navigation", ".nav-links",
        ".comments", "#comments", ".comment-area",
        ".donate", ".donation", ".patreon",
        ".ad", ".ads", ".advertisement",
        "header", "footer", "nav", "aside",
        ".sidebar", ".widget", ".menu",
        ".wp-block-buttons", ".wp-block-button",
        ".code-block",  # Ad blocks
    ]

    def fetch(self, url: str) -> BeautifulSoup:
        """Tải trang web và parse HTML."""
        response = requests.get(url, headers=self.HEADERS, timeout=30)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or "utf-8"
        return BeautifulSoup(response.text, "lxml")

    def clean_soup(self, soup: BeautifulSoup) -> BeautifulSoup:
        """Loại bỏ các phần tử không cần thiết."""
        for selector in self.REMOVE_SELECTORS:
            for el in soup.select(selector):
                el.decompose()
        return soup

    def extract_title(self, soup: BeautifulSoup) -> str:
        """Trích xuất tiêu đề chương."""
        # Thử lấy từ h1, h2, hoặc title
        for tag in ["h1", "h2"]:
            el = soup.find(tag)
            if el:
                text = el.get_text(strip=True)
                if len(text) > 3:
                    return text
        # Fallback: <title> tag
        if soup.title:
            return soup.title.get_text(strip=True)
        return "Untitled Chapter"

    def extract_paragraphs(self, soup: BeautifulSoup) -> list[str]:
        """Trích xuất danh sách đoạn văn từ nội dung."""
        content = None
        for selector in self.CONTENT_SELECTORS:
            content = soup.select_one(selector)
            if content:
                break

        if not content:
            content = soup.body or soup

        paragraphs = []
        for p in content.find_all(["p", "blockquote"]):
            text = p.get_text(strip=True)
            if text and len(text) > 1:
                # Giữ nguyên dấu ngoặc kép cho lời thoại
                text = re.sub(r"\s+", " ", text)
                paragraphs.append(text)

        return paragraphs

    def detect_language(self, paragraphs: list[str]) -> str:
        """Phát hiện ngôn ngữ nguồn (EN hoặc JA)."""
        sample = " ".join(paragraphs[:10])
        # Kiểm tra ký tự Nhật
        ja_chars = len(re.findall(r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]", sample))
        total_chars = len(sample) if sample else 1
        if ja_chars / total_chars > 0.3:
            return "ja"
        return "en"

    def parse(self, url: str) -> ChapterData:
        """Trích xuất chương truyện từ URL."""
        soup = self.fetch(url)
        raw_html = str(soup)
        soup = self.clean_soup(soup)
        title = self.extract_title(soup)
        paragraphs = self.extract_paragraphs(soup)
        lang = self.detect_language(paragraphs)
        return ChapterData(
            title=title,
            paragraphs=paragraphs,
            source_url=url,
            source_lang=lang,
            raw_html=raw_html,
        )


# ──────────────────────────────────────────────
#  Witch Cult Translations (WordPress)
# ──────────────────────────────────────────────
class WitchCultParser(BaseParser):
    """Parser dành riêng cho witchculttranslation.com (WordPress)."""

    CONTENT_SELECTORS = [
        ".entry-content",
        "article .entry-content",
    ]

    REMOVE_SELECTORS = [
        "script", "style", "noscript", "iframe",
        ".sharedaddy", ".sd-sharing", ".share-buttons",
        ".navigation", ".post-navigation", ".nav-links",
        ".comments", "#comments", ".comment-area",
        ".donate", ".donation", ".patreon",
        ".ad", ".ads", ".advertisement",
        "footer", "nav", "aside",
        ".sidebar", ".widget", ".menu",
        ".wp-block-buttons", ".wp-block-button",
        ".wpcnt",  # WordPress stats
        ".jp-relatedposts",  # Related posts
        "hr",  # Separator lines
    ]

    def extract_paragraphs(self, soup: BeautifulSoup) -> list[str]:
        content = soup.select_one(".entry-content")
        if not content:
            return super().extract_paragraphs(soup)

        paragraphs = []
        for p in content.find_all("p"):
            text = p.get_text(strip=True)
            if not text or len(text) <= 1:
                continue
            # Bỏ qua các đoạn chỉ chứa link donate/navigation
            if any(skip in text.lower() for skip in [
                "donate", "patreon", "next chapter", "previous chapter",
                "table of contents", "click here", "support",
            ]):
                continue
            text = re.sub(r"\s+", " ", text)
            paragraphs.append(text)

        return paragraphs


# ──────────────────────────────────────────────
#  Syosetu (ncode.syosetu.com)
# ──────────────────────────────────────────────
class SyosetuParser(BaseParser):
    """Parser cho Syosetu (小説家になろう)."""

    HEADERS = {
        **BaseParser.HEADERS,
        "Accept-Language": "ja,en;q=0.9",
    }

    def extract_title(self, soup: BeautifulSoup) -> str:
        title_el = soup.select_one(".novel_subtitle") or soup.select_one("h1")
        if title_el:
            return title_el.get_text(strip=True)
        return super().extract_title(soup)

    def extract_paragraphs(self, soup: BeautifulSoup) -> list[str]:
        content = soup.select_one("#novel_honbun")
        if not content:
            return super().extract_paragraphs(soup)

        paragraphs = []
        for p in content.find_all("p"):
            text = p.get_text(strip=True)
            if text:
                paragraphs.append(text)

        return paragraphs

    def detect_language(self, paragraphs: list[str]) -> str:
        return "ja"


# ──────────────────────────────────────────────
#  Kakuyomu
# ──────────────────────────────────────────────
class KakuyomuParser(BaseParser):
    """Parser cho Kakuyomu (kakuyomu.jp)."""

    def extract_title(self, soup: BeautifulSoup) -> str:
        title_el = soup.select_one(".widget-episodeTitle")
        if title_el:
            return title_el.get_text(strip=True)
        return super().extract_title(soup)

    def extract_paragraphs(self, soup: BeautifulSoup) -> list[str]:
        content = soup.select_one(".widget-episodeBody")
        if not content:
            return super().extract_paragraphs(soup)

        paragraphs = []
        for p in content.find_all("p"):
            text = p.get_text(strip=True)
            if text:
                paragraphs.append(text)

        return paragraphs

    def detect_language(self, paragraphs: list[str]) -> str:
        return "ja"


# ──────────────────────────────────────────────
#  RoyalRoad
# ──────────────────────────────────────────────
class RoyalRoadParser(BaseParser):
    """Parser cho RoyalRoad (royalroad.com)."""

    CONTENT_SELECTORS = [
        ".chapter-inner.chapter-content",
        ".chapter-content",
    ]

    REMOVE_SELECTORS = BaseParser.REMOVE_SELECTORS + [
        ".portlet",
        ".author-note",
        ".bold-note",  # Author notes
    ]

    def extract_title(self, soup: BeautifulSoup) -> str:
        title_el = soup.select_one("h1")
        if title_el:
            return title_el.get_text(strip=True)
        return super().extract_title(soup)


# ──────────────────────────────────────────────
#  Parser Registry & Factory
# ──────────────────────────────────────────────
PARSER_REGISTRY: dict[str, type[BaseParser]] = {
    "witchculttranslation.com": WitchCultParser,
    "ncode.syosetu.com": SyosetuParser,
    "syosetu.com": SyosetuParser,
    "kakuyomu.jp": KakuyomuParser,
    "royalroad.com": RoyalRoadParser,
    "www.royalroad.com": RoyalRoadParser,
}


def get_parser(url: str) -> BaseParser:
    """Trả về parser phù hợp với domain của URL."""
    domain = urlparse(url).netloc.lower()
    # Loại bỏ www. nếu có
    if domain.startswith("www."):
        domain_clean = domain[4:]
    else:
        domain_clean = domain

    # Tìm parser phù hợp
    for registered_domain, parser_class in PARSER_REGISTRY.items():
        if registered_domain in domain or registered_domain in domain_clean:
            return parser_class()

    # Fallback: generic parser
    return BaseParser()


def scrape_chapter(url: str) -> ChapterData:
    """Hàm chính: trích xuất chương truyện từ URL."""
    parser = get_parser(url)
    return parser.parse(url)


def parse_direct_text(text: str, title: str = "Direct Input", lang: str = "en") -> ChapterData:
    """Tạo ChapterData từ văn bản trực tiếp (không cần URL)."""
    # Tách đoạn văn theo dòng trống
    raw_paragraphs = re.split(r"\n\s*\n", text.strip())
    paragraphs = []
    for p in raw_paragraphs:
        cleaned = re.sub(r"\s+", " ", p.strip())
        if cleaned:
            paragraphs.append(cleaned)

    if not paragraphs:
        # Tách theo dòng đơn nếu không có dòng trống
        paragraphs = [
            line.strip()
            for line in text.strip().split("\n")
            if line.strip()
        ]

    return ChapterData(
        title=title,
        paragraphs=paragraphs,
        source_url="",
        source_lang=lang,
    )
