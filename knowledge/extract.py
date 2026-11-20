"""Turn downloaded HTML pages and PDFs into clean text."""

import io
import logging
import re

import trafilatura
from bs4 import BeautifulSoup
from pypdf import PdfReader

logger = logging.getLogger(__name__)

# Tags that never contain useful content
_NOISE_TAGS = ["script", "style", "noscript", "nav", "header", "footer", "form", "svg", "iframe"]


def clean_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def page_title(soup: BeautifulSoup) -> str:
    if soup.title and soup.title.string:
        return clean_text(soup.title.string)
    h1 = soup.find("h1")
    return clean_text(h1.get_text(" ")) if h1 else ""


def html_to_text(html: str, url: str) -> tuple[str, str]:
    """Return (title, main text) of an HTML page.

    trafilatura removes menus, footers and cookie banners and keeps headings
    and tables (as markdown). If it finds nothing, fall back to all visible text.
    """
    soup = BeautifulSoup(html, "lxml")
    title = page_title(soup)

    text = trafilatura.extract(
        html,
        url=url,
        output_format="markdown",
        include_tables=True,
        include_links=False,
        include_comments=False,
        favor_recall=True,
    )
    if not text or len(text) < 200:
        for tag in soup(_NOISE_TAGS):
            tag.decompose()
        fallback = soup.get_text("\n")
        if len(fallback.strip()) > len(text or ""):
            text = fallback
    return title, clean_text(text or "")


def pdf_to_text(data: bytes) -> tuple[str, str]:
    """Return (title, text) of a PDF file."""
    reader = PdfReader(io.BytesIO(data))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:  # one broken page should not lose the whole file
            logger.debug("Could not read a PDF page", exc_info=True)
    title = ""
    if reader.metadata and reader.metadata.title:
        title = str(reader.metadata.title)
    return clean_text(title), clean_text("\n\n".join(pages))


def extract_links(html: str) -> list[str]:
    """All href values on the page (relative or absolute)."""
    soup = BeautifulSoup(html, "lxml")
    return [a["href"] for a in soup.find_all("a", href=True)]
