"""
PlaywrightScraper — base class for scrapers that need JavaScript rendering.

Extends BaseScraper with Playwright browser automation. Use for:
  - CivicEngage agenda centers (changeYear() JS navigation)
  - BoardDocs SPA portals
  - Any site that renders content via JavaScript

Usage:
  Inherit from PlaywrightScraper instead of BaseScraper.
  Use self.page to access the Playwright page object.
  Call self.navigate(url) to load a page with JS rendering.
  Call self.wait_for(selector) to wait for dynamic content.
"""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from .scraper import BaseScraper, ScrapeResult, ScrapedDocument
from .registry import register_scraper


# Check if Playwright is available
try:
    from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class PlaywrightScraper(BaseScraper):
    """Base scraper with Playwright browser automation.

    Provides:
      - self.page — Playwright Page object
      - self.navigate(url) — load page with JS rendering
      - self.wait_for(selector) — wait for element
      - self.screenshot() — capture page state
      - self.extract_pdf_links() — find PDF download links
      - self.extract_text() — get visible page text
    """

    def __init__(self, headless: bool = True, viewport_width: int = 1440,
                 viewport_height: int = 900, timeout: int = 30, **kwargs):
        super().__init__(**kwargs)
        self.headless = headless
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.timeout = timeout
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    # -- Browser lifecycle ------------------------------------------------

    @property
    def page(self) -> Page:
        """Get or create the Playwright page."""
        if self._page is None:
            if not PLAYWRIGHT_AVAILABLE:
                raise RuntimeError(
                    "Playwright is not installed. Install with: pip install playwright && playwright install chromium"
                )
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=self.headless,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )
            self._context = self._browser.new_context(
                viewport={"width": self.viewport_width, "height": self.viewport_height},
                user_agent="ParentDataForce/1.0 (research bot; parentdataforce.com)",
            )
            self._page = self._context.new_page()
            self._page.set_default_timeout(self.timeout * 1000)
        return self._page

    def close_browser(self):
        """Close Playwright browser and cleanup."""
        if self._page:
            self._page.close()
            self._page = None
        if self._context:
            self._context.close()
            self._context = None
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None

    # -- Navigation helpers -----------------------------------------------

    def navigate(self, url: str, wait_until: str = "networkidle") -> str:
        """Load a page with full JS rendering. Returns page content HTML."""
        self._rate_limit_wait()
        self.page.goto(url, wait_until=wait_until)
        self._last_request = time.time()
        return self.page.content()

    def wait_for(self, selector: str, timeout: Optional[int] = None):
        """Wait for an element to appear on the page."""
        self.page.wait_for_selector(
            selector,
            timeout=(timeout or self.timeout) * 1000,
            state="visible",
        )

    def click(self, selector: str):
        """Click an element."""
        self.page.click(selector)

    def evaluate(self, js: str) -> any:
        """Execute JavaScript in the page context."""
        return self.page.evaluate(js)

    def screenshot(self, path: Optional[Path] = None) -> bytes:
        """Take a screenshot. Returns PNG bytes."""
        if path:
            self.page.screenshot(path=str(path))
            return b""
        return self.page.screenshot()

    # -- Content extraction -----------------------------------------------

    def extract_pdf_links(self, base_url: str = "") -> list[tuple[str, str]]:
        """Find all PDF links on the current page.

        Returns list of (url, link_text) tuples.
        """
        links = self.page.evaluate("""() => {
            const links = [];
            document.querySelectorAll('a[href$=".pdf"], a[href*=".pdf?"]').forEach(a => {
                links.push({url: a.href, text: a.textContent.trim()});
            });
            return links;
        }""")
        return [(l["url"], l["text"]) for l in links]

    def extract_links_by_text(self, *keywords: str) -> list[tuple[str, str]]:
        """Find links whose text contains any of the given keywords.

        Returns list of (url, link_text) tuples.
        """
        kw_list = list(keywords)
        links = self.page.evaluate("""
            (keywords) => {
                const links = [];
                document.querySelectorAll('a').forEach(a => {
                    const text = a.textContent.toLowerCase();
                    for (const kw of keywords) {
                        if (text.includes(kw.toLowerCase())) {
                            links.push({url: a.href, text: a.textContent.trim()});
                            break;
                        }
                    }
                });
                return links;
            }
        """, kw_list)
        return [(l["url"], l["text"]) for l in links]

    def extract_table_rows(self, table_selector: str) -> list[dict]:
        """Extract all rows from a table as dicts (header → value)."""
        return self.page.evaluate("""
            (selector) => {
                const table = document.querySelector(selector);
                if (!table) return [];
                const headers = [];
                table.querySelectorAll('thead th, thead td, tr:first-child th, tr:first-child td').forEach(h => {
                    headers.push(h.textContent.trim());
                });
                if (!headers.length) return [];
                const rows = [];
                table.querySelectorAll('tbody tr, tr:not(:first-child)').forEach(row => {
                    const cells = row.querySelectorAll('td, th');
                    if (cells.length === headers.length) {
                        const obj = {};
                        cells.forEach((cell, i) => {
                            obj[headers[i]] = cell.textContent.trim();
                        });
                        rows.push(obj);
                    }
                });
                return rows;
            }
        """, table_selector)

    def extract_text(self, selector: str = "body") -> str:
        """Get visible text content from the page or element."""
        return self.page.text_content(selector) or ""

    # -- Document classification helpers ----------------------------------

    def classify_from_url(self, url: str) -> tuple[str, str]:
        """Guess media_type and document_class from a URL.

        Returns (media_type, document_class).
        """
        url_lower = url.lower()
        filename = url.rsplit("/", 1)[-1] if "/" in url else url

        # Media type
        ext = filename.rsplit(".", 1)[-1] if "." in filename else ""
        media_map = {
            "pdf": "PDF", "html": "HTML", "htm": "HTML",
            "mp4": "video", "mov": "video", "webm": "video",
            "png": "image", "jpg": "image", "jpeg": "image", "gif": "image",
            "xlsx": "spreadsheet", "xls": "spreadsheet", "csv": "spreadsheet",
            "docx": "text", "doc": "text", "txt": "text",
        }
        media_type = media_map.get(ext, "other")

        # Document class
        if any(k in url_lower for k in ["agenda", "agnd"]):
            doc_class = "meeting_agenda"
        elif any(k in url_lower for k in ["minute", "min"]):
            doc_class = "meeting_minutes"
        elif any(k in url_lower for k in ["packet", "pkt"]):
            doc_class = "meeting_packet"
        elif any(k in url_lower for k in ["policy"]):
            doc_class = "policy_manual"
        elif any(k in url_lower for k in ["budget"]):
            doc_class = "budget"
        elif any(k in url_lower for k in ["handbook"]):
            doc_class = "school_handbook"
        elif any(k in url_lower for k in ["report", "annual"]):
            doc_class = "annual_report"
        else:
            doc_class = "other"

        return media_type, doc_class

    # -- Lifecycle --------------------------------------------------------

    def run(self, **kwargs) -> ScrapeResult:
        """Override in subclass. Remember to call close_browser() at the end."""
        raise NotImplementedError("Subclass must implement run()")

    def __del__(self):
        try:
            self.close_browser()
        except Exception:
            pass
