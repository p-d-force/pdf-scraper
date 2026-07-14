"""
ScrapedDocument — the universal document record that flows through discovery,
download, verification, and FTP upload.

Every scraper produces these. The CLI, DB, and FTP modules all consume them.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional


@dataclass
class ScrapedDocument:
    """A document discovered during scraping — from URL to FTP."""

    # Identity (required)
    title: str
    source_url: str

    # Classification (required)
    media_type: str  # PDF, HTML, video, image, spreadsheet, text, archive, other
    document_class: str  # meeting_agenda, meeting_minutes, policy_manual, budget, etc.

    # Source context (required)
    source_system: str  # dese, apptegy, civicengage, boarddocs, custom_html, manual

    # Optional metadata
    file_type: Optional[str] = None  # MIME type
    file_extension: Optional[str] = None
    source_label: Optional[str] = None
    district_code: Optional[str] = None
    meeting_date: Optional[date] = None

    # File tracking (populated during lifecycle)
    file_path: Optional[Path] = None
    file_size: Optional[int] = None
    page_count: Optional[int] = None
    checksum: Optional[str] = None
    ftp_path: Optional[str] = None
    ftp_uploaded_at: Optional[datetime] = None

    # Lifecycle
    status: str = "discovered"  # discovered, downloaded, verified, uploaded, failed, skipped_duplicate
    scrape_date: date = field(default_factory=date.today)
    last_checked: Optional[datetime] = None
    error_message: Optional[str] = None

    # Strategy
    scrape_method: Optional[str] = None
    scrape_notes: Optional[str] = None

    # Internal
    _local_path: Optional[Path] = field(default=None, repr=False)

    # -- Lifecycle helpers -------------------------------------------------

    def mark_downloaded(self, local_path: Path, file_size: Optional[int] = None) -> "ScrapedDocument":
        """Called after file is saved locally."""
        self.file_path = local_path
        self._local_path = local_path
        self.file_size = file_size or (local_path.stat().st_size if local_path.exists() else None)
        self.checksum = self._compute_checksum()
        self.status = "downloaded"
        return self

    def mark_verified(self, page_count: Optional[int] = None) -> "ScrapedDocument":
        """Called after file is confirmed valid (opens, has expected content)."""
        self.status = "verified"
        if page_count is not None:
            self.page_count = page_count
        return self

    def mark_uploaded(self, ftp_path: str) -> "ScrapedDocument":
        """Called after successful FTP upload."""
        self.ftp_path = ftp_path
        self.ftp_uploaded_at = datetime.now()
        self.status = "uploaded"
        return self

    def mark_failed(self, error: str) -> "ScrapedDocument":
        """Called on any failure."""
        self.status = "failed"
        self.error_message = error
        return self

    def mark_duplicate(self, existing_checksum: str) -> "ScrapedDocument":
        """Called when checksum matches an existing document."""
        self.status = "skipped_duplicate"
        self.checksum = existing_checksum
        return self

    # -- Serialization ----------------------------------------------------

    def to_db_row(self) -> dict:
        """Convert to dict matching the documents table columns."""
        d = asdict(self)
        # Convert Path/date/datetime to string/ISO for SQL
        for key in ("file_path", "ftp_path", "_local_path"):
            if isinstance(d.get(key), Path):
                d[key] = str(d[key])
        for key in ("meeting_date", "scrape_date"):
            if isinstance(d.get(key), date):
                d[key] = d[key].isoformat()
        for key in ("ftp_uploaded_at", "last_checked"):
            if isinstance(d.get(key), datetime):
                d[key] = d[key].isoformat()
        d.pop("_local_path", None)
        return d

    def summary(self) -> str:
        """One-line summary for CLI display."""
        status_icon = {"discovered": "?", "downloaded": "↓", "verified": "✓",
                       "uploaded": "↑", "failed": "✗", "skipped_duplicate": "≅"}
        icon = status_icon.get(self.status, "?")
        return f"[{icon}] {self.title[:60]:<60} | {self.document_class:<25} | {self.source_system:<12} | {self.scrape_date}"

    # -- Internals ---------------------------------------------------------

    def _compute_checksum(self) -> Optional[str]:
        if self._local_path and self._local_path.exists():
            sha = hashlib.sha256()
            with open(self._local_path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    sha.update(chunk)
            return sha.hexdigest()
        return None


# -- Document classification constants -------------------------------------

MEDIA_TYPES = [
    "PDF", "HTML", "video", "image", "spreadsheet",
    "text", "archive", "audio", "other",
]

DOCUMENT_CLASSES = [
    "meeting_agenda",
    "meeting_minutes",
    "meeting_packet",
    "meeting_video",
    "policy_manual",
    "budget",
    "annual_report",
    "school_handbook",
    "sepac_info",
    "prr_response",
    "des_report",
    "correspondence",
    "testimony",
    "legal_filing",
    "media_coverage",
    "other",
]

SOURCE_SYSTEMS = [
    "dese", "apptegy", "civicengage", "boarddocs",
    "youtube", "custom_html", "manual",
]
