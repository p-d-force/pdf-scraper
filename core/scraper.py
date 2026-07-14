"""
BaseScraper — the abstract base every scraper inherits from.
Supports running standalone OR via registry/CLI.
"""
from __future__ import annotations

import sys
import time
import traceback
from abc import ABC, abstractmethod
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .base import ScrapedDocument


class ScrapeResult:
    """Returned by every scraper run. Carries documents + metadata."""

    def __init__(self):
        self.documents: list[ScrapedDocument] = []
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.stats: dict = {}
        self.started_at: Optional[datetime] = None
        self.finished_at: Optional[datetime] = None

    @property
    def elapsed(self) -> float:
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return 0.0

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


class BaseScraper(ABC):
    """Every scraper inherits this.

    Subclasses override:
      - name: str           — unique identifier
      - display_name: str   — human-readable
      - source_system: str  — dese, apptegy, civicengage, etc.
      - help_text: str      — shown in CLI

    Then implement:
      - run(**kwargs) -> ScrapeResult
    """

    # -- Override these in subclasses ------------------------------------

    name: str = "__base__"
    display_name: str = "Base Scraper"
    source_system: str = "manual"
    help_text: str = "Base scraper — override in subclass."

    # -- Session management ---------------------------------------------

    def __init__(self, download_dir: Optional[Path] = None, rate_limit: float = 3.0):
        self.download_dir = download_dir or Path("data/downloads")
        self.rate_limit = rate_limit
        self._session: Optional[requests.Session] = None
        self._last_request: float = 0.0

    def _get_session(self) -> requests.Session:
        if self._session is None:
            self._session = requests.Session()
            retries = Retry(total=3, backoff_factor=1.0,
                           status_forcelist=[429, 500, 502, 503, 504])
            self._session.mount("https://", HTTPAdapter(max_retries=retries))
            self._session.mount("http://", HTTPAdapter(max_retries=retries))
            self._session.headers.update({
                "User-Agent": "ParentDataForce/1.0 (research bot; parentdataforce.com)"
            })
        return self._session

    def _rate_limit_wait(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self._last_request = time.time()

    def _get(self, url: str, **kwargs) -> requests.Response:
        """GET with rate limiting and session reuse."""
        self._rate_limit_wait()
        return self._get_session().get(url, timeout=30, **kwargs)

    def _download_file(self, url: str, filename: str) -> Optional[Path]:
        """Download a file, return local path."""
        self._rate_limit_wait()
        self.download_dir.mkdir(parents=True, exist_ok=True)

        # Sanitize filename
        safe_name = "".join(c for c in filename if c.isalnum() or c in "._- ")
        safe_name = safe_name.strip()[:200]
        dest = self.download_dir / safe_name

        # Avoid overwriting
        if dest.exists():
            stem, ext = dest.stem, dest.suffix
            dest = self.download_dir / f"{stem}_{int(time.time())}{ext}"

        resp = self._get_session().get(url, stream=True, timeout=60)
        resp.raise_for_status()

        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        return dest

    # -- Abstract method ------------------------------------------------

    @abstractmethod
    def run(self, **kwargs) -> ScrapeResult:
        """Execute the scraper. Called by CLI or direct invocation."""
        ...

    # -- CLI helpers ----------------------------------------------------

    @classmethod
    def cli_run(cls, **kwargs):
        """Entry point for `python scrapers/foo.py` standalone runs."""
        scraper = cls(**{k: v for k, v in kwargs.items()
                        if k in ("download_dir", "rate_limit")})
        print(f"\n{'='*60}")
        print(f"  {scraper.display_name}")
        print(f"  Source: {scraper.source_system}")
        print(f"{'='*60}\n")

        try:
            result = scraper.run(**{k: v for k, v in kwargs.items()
                                    if k not in ("download_dir", "rate_limit")})
            scraper._print_result(result)
        except Exception as e:
            print(f"\n[FATAL] {e}")
            traceback.print_exc()
            sys.exit(1)

    @staticmethod
    def _print_result(result: ScrapeResult):
        """Pretty-print scrape results."""
        print(f"\n{'─'*60}")
        print(f"  Results: {len(result.documents)} docs in {result.elapsed:.1f}s")
        print(f"  Errors:  {len(result.errors)}")
        print(f"{'─'*60}")

        discovered = sum(1 for d in result.documents if d.status == "discovered")
        downloaded = sum(1 for d in result.documents if d.status == "downloaded")
        skipped = sum(1 for d in result.documents if d.status == "skipped_duplicate")
        failed = sum(1 for d in result.documents if d.status == "failed")

        print(f"  ↳ {downloaded} downloaded, {discovered} discovered, "
              f"{skipped} duplicates, {failed} failed")

        if result.documents:
            print(f"\n  Documents:")
            for doc in result.documents[:20]:
                print(f"    {doc.summary()}")
            if len(result.documents) > 20:
                print(f"    ... and {len(result.documents) - 20} more")

        if result.errors:
            print(f"\n  Errors:")
            for err in result.errors[:5]:
                print(f"    ✗ {err}")
            if len(result.errors) > 5:
                print(f"    ... and {len(result.errors) - 5} more")
