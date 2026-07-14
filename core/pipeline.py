"""
ScraperPipeline — orchestrates the full document lifecycle:
  discover → download → verify → (upload)

Used by scrapers to process discovered documents. Handles:
  - Checksum-based dedup (skip already-downloaded files)
  - Rate-limited downloads
  - File verification (can it be opened? expected size?)
  - Automatic classification from filename patterns
  - Strategy recording for successes/failures
"""
from __future__ import annotations

import hashlib
import time
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .base import ScrapedDocument
from .db import DocumentDB
from .strategy import StrategyStore


class ScraperPipeline:
    """Processes ScrapedDocuments through download + verification."""

    def __init__(self, download_dir: Optional[Path] = None,
                 rate_limit: float = 3.0, verify_downloads: bool = True):
        if download_dir is None:
            download_dir = Path(__file__).parent.parent / "data" / "downloads"
        self.download_dir = download_dir
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.rate_limit = rate_limit
        self.verify_downloads = verify_downloads
        self.db = DocumentDB()
        self.strategy = StrategyStore()
        self._session: Optional[requests.Session] = None
        self._last_request: float = 0.0

        # Stats for this pipeline run
        self.stats = {"downloaded": 0, "skipped": 0, "failed": 0, "bytes": 0}

    @property
    def session(self) -> requests.Session:
        if self._session is None:
            self._session = requests.Session()
            retries = Retry(total=2, backoff_factor=1.0,
                           status_forcelist=[429, 500, 502, 503, 504])
            self._session.mount("https://", HTTPAdapter(max_retries=retries))
            self._session.mount("http://", HTTPAdapter(max_retries=retries))
            self._session.headers.update({
                "User-Agent": "ParentDataForce/1.0 (research bot; parentdataforce.com)"
            })
        return self._session

    def _rate_limit_wait(self):
        elapsed = time.time() - self._last_request
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self._last_request = time.time()

    # -- Document processing ----------------------------------------------

    def process(self, doc: ScrapedDocument, subdir: str = "") -> ScrapedDocument:
        """Discover → download → verify one document.

        Returns the document with lifecycle state updated.
        """
        # 1. Check if already in DB and downloaded
        existing = self.db.get_by_url(doc.source_url)
        if existing and existing.get("status") in ("downloaded", "verified", "uploaded"):
            if existing.get("file_path") and Path(existing["file_path"]).exists():
                doc.status = "skipped_duplicate"
                self.stats["skipped"] += 1
                return doc

        # 2. Only download actual files (not HTML pages)
        if doc.media_type == "HTML":
            doc.status = "discovered"
            return doc

        # 3. Determine save path
        dest_dir = self.download_dir / subdir if subdir else self.download_dir
        dest_dir.mkdir(parents=True, exist_ok=True)

        filename = self._safe_filename(doc)
        dest = dest_dir / filename
        if dest.exists():
            stem, ext = dest.stem, dest.suffix
            dest = dest_dir / f"{stem}_{int(time.time())}{ext}"

        # 4. Download
        try:
            self._rate_limit_wait()
            resp = self.session.get(doc.source_url, stream=True, timeout=60)
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "").lower()
            content_length = resp.headers.get("content-length")

            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            file_size = dest.stat().st_size

            # Skip empty files
            if file_size == 0:
                dest.unlink()
                doc.mark_failed("Downloaded file is empty (0 bytes)")
                self.stats["failed"] += 1
                return doc

            # Detect actual media type from content-type header
            if "pdf" in content_type:
                doc.media_type = "PDF"
                doc.file_type = "application/pdf"
                doc.file_extension = "pdf"
            elif "html" in content_type:
                doc.media_type = "HTML"
                doc.file_type = "text/html"
                doc.file_extension = "html"
            elif "image" in content_type:
                doc.media_type = "image"
                doc.file_type = content_type.split(";")[0]
            elif "video" in content_type:
                doc.media_type = "video"
                doc.file_type = content_type.split(";")[0]

            doc.mark_downloaded(dest, file_size)

            # 5. Verify (if enabled)
            if self.verify_downloads:
                doc = self._verify(doc)

            # 6. Dedup check
            if doc.checksum:
                dup = self.db.find_by_checksum(doc.checksum)
                if dup:
                    doc.mark_duplicate(doc.checksum)
                    self.stats["skipped"] += 1
                    # Remove duplicate file
                    if dest.exists():
                        dest.unlink()
                    return doc

            # 7. Save to DB
            if not self.db.exists(doc.source_url):
                self.db.insert(doc)
            else:
                self.db.update_status(doc.source_url, doc.status,
                                     file_path=str(doc.file_path) if doc.file_path else None,
                                     file_size=doc.file_size,
                                     checksum=doc.checksum,
                                     media_type=doc.media_type,
                                     file_type=doc.file_type,
                                     file_extension=doc.file_extension)

            self.stats["downloaded"] += 1
            self.stats["bytes"] += file_size

            # 8. Record strategy
            self.strategy.record_success(
                strategy_name=f"Download: {doc.source_system} {doc.document_class}",
                platform_type=doc.source_system,
                pattern_type="direct_download",
                pattern_value=doc.source_url,
                example_url=doc.source_url,
            )

        except Exception as e:
            doc.mark_failed(str(e))
            self.stats["failed"] += 1
            self.strategy.record_failure(
                strategy_name=f"Download: {doc.source_system}",
                platform_type=doc.source_system,
                pattern_type="direct_download",
                pattern_value=doc.source_url,
                notes=str(e),
            )

        return doc

    def process_batch(self, documents: list[ScrapedDocument],
                      subdir: str = "") -> list[ScrapedDocument]:
        """Process a batch of documents through download + verify."""
        results = []
        total = len(documents)
        for i, doc in enumerate(documents, 1):
            print(f"  [{i}/{total}] {doc.title[:60]}...", end=" ")
            processed = self.process(doc, subdir)
            print(processed.status)
            results.append(processed)
        return results

    # -- Helpers ----------------------------------------------------------

    def _safe_filename(self, doc: ScrapedDocument) -> str:
        """Generate a safe filename from document metadata."""
        # Try to extract filename from URL
        url_path = doc.source_url.split("?")[0]
        url_name = url_path.rsplit("/", 1)[-1] if "/" in url_path else url_path

        if url_name and "." in url_name and len(url_name) < 200:
            # Has an extension, use it
            safe = "".join(c for c in url_name if c.isalnum() or c in "._- ")
            return safe.strip()[:200]

        # Build from metadata
        parts = []
        if doc.meeting_date:
            parts.append(doc.meeting_date.isoformat())
        parts.append(doc.document_class[:30])
        if doc.district_code:
            parts.append(doc.district_code)
        parts.append(doc.title[:40])

        base = "_".join(parts)
        safe = "".join(c for c in base if c.isalnum() or c in "_- ")
        ext = doc.file_extension or "pdf"
        return f"{safe[:200]}.{ext}"

    def _verify(self, doc: ScrapedDocument) -> ScrapedDocument:
        """Verify a downloaded file can be opened and has expected content."""
        if not doc.file_path or not doc.file_path.exists():
            doc.mark_failed("File path does not exist after download")
            return doc

        # PDF verification
        if doc.file_extension == "pdf":
            try:
                with open(doc.file_path, "rb") as f:
                    header = f.read(5)
                if header != b"%PDF-":
                    doc.mark_failed("File does not start with PDF header")
                    return doc
            except Exception as e:
                doc.mark_failed(f"PDF verification failed: {e}")
                return doc

        # Image verification
        if doc.file_extension in ("png", "jpg", "jpeg", "gif", "webp"):
            try:
                from PIL import Image
                img = Image.open(doc.file_path)
                img.verify()
            except Exception:
                doc.mark_failed("Image verification failed (corrupt or unreadable)")
                return doc

        doc.mark_verified()
        return doc

    def close(self):
        if self._session:
            self._session.close()
            self._session = None
