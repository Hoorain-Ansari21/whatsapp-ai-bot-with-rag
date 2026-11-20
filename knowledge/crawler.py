"""Website extraction agent.

Crawls every Source in sources.py, extracts the readable text of each HTML page
and PDF, and appends it to data/raw/pages.jsonl. Progress is saved per source in
data/raw/crawl_state.json, so an interrupted crawl resumes where it stopped
instead of starting over.

How a site is crawled:
- Start from the seed pages, then follow links on the same site.
- Links whose URL or text mention scholarships, fees, admissions, etc. are
  visited first, so the page budget is spent on the useful pages.
- robots.txt is respected and each site gets at most one request per second.
"""

import hashlib
import heapq
import itertools
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.parse import urldefrag, urljoin, urlparse, urlencode, parse_qsl
from urllib.robotparser import RobotFileParser

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .extract import extract_links, html_to_text, pdf_to_text
from .paths import CRAWL_STATE_FILE, PAGES_FILE, RAW_DIR
from .sources import SOURCES, Source

logger = logging.getLogger(__name__)

USER_AGENT = "IlmAssistBot/1.0 (educational WhatsApp assistant; one-time crawl)"
DEFAULT_MAX_DEPTH = 2
DEFAULT_MAX_PAGES = 300
REQUEST_DELAY_SECONDS = 1.0
REQUEST_TIMEOUT_SECONDS = 25
MAX_DOWNLOAD_BYTES = 15 * 1024 * 1024  # skip files bigger than 15 MB
MIN_TEXT_CHARS = 200  # pages with less text than this are menus or empty

# Links containing these words are crawled first
PRIORITY_WORDS = [
    "scholarship", "fellowship", "financial", "aid", "fee", "tuition", "admission",
    "eligib", "apply", "application", "deadline", "stipend", "policy", "faq",
    "loan", "need-based", "merit", "attestation", "equivalence", "programme",
    "program", "criteria", "recognised", "recognized", "university", "campus",
]

SKIP_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico", ".bmp", ".mp3", ".mp4",
    ".avi", ".mov", ".wmv", ".zip", ".rar", ".7z", ".gz", ".exe", ".css", ".js",
    ".xml", ".rss", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".csv",
)
SKIP_URL_PARTS = ("/login", "/signin", "/sign-in", "/logout", "/search", "/_layouts/", "/wp-admin")
TRACKING_PARAMS = ("utm_", "fbclid", "gclid")

_write_lock = threading.Lock()


# --------------------------------------------------------------------------- helpers
def _host(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def normalize_url(url: str) -> str | None:
    url, _ = urldefrag(url.strip())
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    query = urlencode(
        [(k, v) for k, v in parse_qsl(parsed.query) if not k.lower().startswith(TRACKING_PARAMS)]
    )
    path = parsed.path or "/"
    return parsed._replace(netloc=parsed.netloc.lower(), path=path, query=query).geturl()


def link_priority(url: str) -> int:
    lowered = url.lower()
    return sum(word in lowered for word in PRIORITY_WORDS)


def make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=2,
        backoff_factor=2,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "HEAD"),
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en"})
    return session


# --------------------------------------------------------------------------- state
def load_state() -> dict:
    if CRAWL_STATE_FILE.exists():
        return json.loads(CRAWL_STATE_FILE.read_text(encoding="utf-8"))
    return {"completed_sources": {}}


def save_state(state: dict) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    CRAWL_STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def drop_pages_of(sources: set[str]) -> None:
    """Remove half-finished sources from pages.jsonl so they can be re-crawled cleanly."""
    if not PAGES_FILE.exists() or not sources:
        return
    kept = [
        line
        for line in PAGES_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and json.loads(line)["source"] not in sources
    ]
    PAGES_FILE.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")


def append_page(record: dict) -> None:
    with _write_lock:
        with PAGES_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------- crawler
class SiteCrawler:
    """Crawls one Source, politely, and writes its pages to pages.jsonl."""

    def __init__(self, source: Source, max_depth: int, max_pages: int):
        self.source = source
        self.max_depth = source.max_depth if source.max_depth is not None else max_depth
        self.max_pages = source.max_pages if source.max_pages is not None else max_pages
        self.hosts = {_host(seed) for seed in source.seeds}
        self.session = make_session()
        self.robots: dict[str, RobotFileParser | None] = {}
        self.last_request = 0.0
        self.seen_urls: set[str] = set()
        self.seen_text_hashes: set[str] = set()
        self.saved = 0

    # ---- rules
    def allowed_by_robots(self, url: str) -> bool:
        parsed = urlparse(url)
        root = f"{parsed.scheme}://{parsed.netloc}"
        if root not in self.robots:
            parser = RobotFileParser()
            try:
                response = self.session.get(f"{root}/robots.txt", timeout=REQUEST_TIMEOUT_SECONDS)
                if response.status_code == 200:
                    parser.parse(response.text.splitlines())
                    self.robots[root] = parser
                else:
                    self.robots[root] = None  # no robots.txt = everything allowed
            except requests.RequestException:
                self.robots[root] = None
        parser = self.robots[root]
        return parser is None or parser.can_fetch(USER_AGENT, url)

    def should_follow(self, url: str) -> bool:
        parsed = urlparse(url)
        path = parsed.path.lower()
        if _host(url) not in self.hosts:
            return False
        if path.endswith(SKIP_EXTENSIONS) or any(part in path for part in SKIP_URL_PARTS):
            return False
        if self.source.allow_paths and not path.endswith(".pdf"):
            if not any(path.startswith(p.lower()) for p in self.source.allow_paths):
                return False
        return True

    # ---- network
    def fetch(self, url: str) -> requests.Response | None:
        wait = REQUEST_DELAY_SECONDS - (time.monotonic() - self.last_request)
        if wait > 0:
            time.sleep(wait)
        self.last_request = time.monotonic()
        try:
            response = self.session.get(url, timeout=REQUEST_TIMEOUT_SECONDS, stream=True)
            length = int(response.headers.get("Content-Length") or 0)
            if response.status_code != 200 or length > MAX_DOWNLOAD_BYTES:
                logger.debug("Skip %s (status %s, %s bytes)", url, response.status_code, length)
                response.close()
                return None
            content = response.raw.read(MAX_DOWNLOAD_BYTES + 1, decode_content=True)
            if len(content) > MAX_DOWNLOAD_BYTES:
                return None
            response._content = content  # make .text/.content work after streaming
            return response
        except requests.RequestException as error:
            logger.debug("Failed %s: %s", url, error)
            return None

    # ---- main loop
    def crawl(self) -> int:
        counter = itertools.count()
        queue: list[tuple[int, int, int, str]] = []  # (depth, -priority, order, url)
        for seed in self.source.seeds:
            url = normalize_url(seed)
            if url and url not in self.seen_urls:
                self.seen_urls.add(url)
                heapq.heappush(queue, (0, 0, next(counter), url))

        while queue and self.saved < self.max_pages:
            depth, _, _, url = heapq.heappop(queue)
            if not self.allowed_by_robots(url):
                logger.debug("robots.txt disallows %s", url)
                continue

            response = self.fetch(url)
            if response is None:
                continue

            final_url = normalize_url(response.url) or url
            content_type = response.headers.get("Content-Type", "").lower()
            is_pdf = "application/pdf" in content_type or final_url.lower().endswith(".pdf")

            try:
                if is_pdf:
                    title, text = pdf_to_text(response.content)
                    if not title or title.lower() in ("untitled", "microsoft word"):
                        title = urlparse(final_url).path.rsplit("/", 1)[-1].replace("-", " ")
                    links = []
                elif "html" in content_type or not content_type:
                    html = response.text
                    title, text = html_to_text(html, final_url)
                    links = extract_links(html)
                else:
                    continue
            except Exception:
                logger.warning("Could not extract %s", final_url, exc_info=True)
                continue

            self.save(final_url, title, text, "pdf" if is_pdf else "html")

            if depth < self.max_depth:
                for href in links:
                    link = normalize_url(urljoin(final_url, href))
                    if link and link not in self.seen_urls and self.should_follow(link):
                        self.seen_urls.add(link)
                        heapq.heappush(queue, (depth + 1, -link_priority(link), next(counter), link))

        return self.saved

    def save(self, url: str, title: str, text: str, kind: str) -> None:
        if len(text) < MIN_TEXT_CHARS:
            return
        digest = hashlib.sha1(text.encode("utf-8")).hexdigest()
        if digest in self.seen_text_hashes:  # same page under another URL
            return
        self.seen_text_hashes.add(digest)
        append_page(
            {
                "url": url,
                "title": title or url,
                "source": self.source.name,
                "category": self.source.category,
                "type": kind,
                "text": text,
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        )
        self.saved += 1
        if self.saved % 25 == 0:
            logger.info("  %s: %d pages saved", self.source.name, self.saved)


def crawl_all(
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_pages: int = DEFAULT_MAX_PAGES,
    only: list[str] | None = None,
    workers: int = 4,
) -> dict:
    """Crawl every source that has not been completed yet. Returns the crawl state."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()
    done = state["completed_sources"]

    sources = [s for s in SOURCES if not only or s.name in only]
    todo = [s for s in sources if s.name not in done]
    if not todo:
        logger.info("All sources already crawled, nothing to do.")
        return state

    # Pages of sources that were interrupted last time are removed and crawled again
    drop_pages_of({s.name for s in todo})
    logger.info("Crawling %d source(s) (depth %d, up to %d pages each)...", len(todo), max_depth, max_pages)

    # Different sites are crawled at the same time; each site itself is crawled
    # one request at a time so we never hammer a single server.
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(SiteCrawler(s, max_depth, max_pages).crawl): s for s in todo}
        for future in as_completed(futures):
            source = futures[future]
            try:
                count = future.result()
            except Exception:
                logger.exception("Crawling %s failed; it will be retried next run", source.name)
                continue
            if count == 0:
                logger.warning("%s: no pages extracted (site blocked or unreachable?)", source.name)
            logger.info("Finished %s: %d pages", source.name, count)
            with _write_lock:
                done[source.name] = {
                    "pages": count,
                    "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }
                save_state(state)

    return state


def load_pages() -> list[dict]:
    if not PAGES_FILE.exists():
        return []
    with PAGES_FILE.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def source_names() -> list[str]:
    return [s.name for s in SOURCES]


def is_crawl_complete() -> bool:
    done = load_state()["completed_sources"]
    return all(name in done for name in source_names())

