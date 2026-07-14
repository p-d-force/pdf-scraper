"""
Apptegy Meeting Scraper — scrapes meeting agendas, minutes, and packets
from Apptegy/Thrillshare-powered school district websites.

Platform detection: subdomain on apptegy.net, or page source references
to 'thrillshare' or 'files-backend.assets.thrillshare.com'.

Strategy: The actual PDFs are hosted on the Thrillshare CDN with UUID paths.
The listing pages use JS to render meeting tables. Two approaches:
  1. Parse the page source for CDN URLs (UUID pattern matching)
  2. Use Selenium/Playwright to render JS, then extract links

Usage:
  python scrapers/apptegy_meetings.py --url https://attleboroschools.apptegy.net/
  python scrapers/apptegy_meetings.py --district attleboro
"""
from __future__ import annotations

import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

from scraper.core import (
    BaseScraper, ScrapeResult, ScrapedDocument,
    register_scraper, DocumentDB, StrategyStore,
)


# UUID pattern from Thrillshare CDN
THRILLSHARE_UUID_RE = re.compile(
    r'files-backend\.assets\.thrillshare\.com/[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}',
    re.IGNORECASE
)

# PDF link patterns
PDF_LINK_RE = re.compile(r'href=["\']([^"\']+\.pdf)["\']', re.IGNORECASE)

# Known MA districts on Apptegy
DISTRICT_URLS = {
    "attleboro": "https://attleboroschools.apptegy.net/",
}


@register_scraper
class ApptegyMeetingsScraper(BaseScraper):
    """Scrape meeting documents from Apptegy-powered district websites."""

    name = "apptegy_meetings"
    display_name = "Apptegy Meeting Documents"
    source_system = "apptegy"
    help_text = "Scrape meeting agendas/minutes from Apptegy/Thrillshare district sites"

    def run(self, url: str = "", district: str = "", **kwargs) -> ScrapeResult:
        """Scrape Apptegy meeting documents.

        Args:
            url: Direct URL to scrape (overrides district lookup)
            district: District slug for URL lookup (e.g., 'attleboro')
        """
        result = ScrapeResult()
        result.started_at = datetime.now()
        strategy = StrategyStore()
        db = DocumentDB()
        db.ensure_table()

        # Resolve URL
        if not url and district:
            url = DISTRICT_URLS.get(district.lower(), "")
        if not url:
            result.errors.append("No URL or district provided.")
            result.finished_at = datetime.now()
            return result

        try:
            print(f"  Fetching {url}...")
            resp = self._get(url)
            resp.raise_for_status()
            html = resp.text

            # Check if this is actually Apptegy
            is_apptegy = "thrillshare" in html.lower() or "apptegy" in url.lower()
            if not is_apptegy:
                result.warnings.append(f"URL does not appear to be Apptegy: {url}")

            # Strategy 1: Find Thrillshare CDN URLs
            cdn_urls = THRILLSHARE_UUID_RE.findall(html)
            if cdn_urls:
                strategy.record_success(
                    "Apptegy CDN direct PDF download",
                    "apptegy", "url_pattern",
                    "Thrillshare UUID pattern in page source",
                    example_url=url,
                )
                for cdn_url in set(cdn_urls):
                    # The regex captures paths, reconstruct full URL
                    full_url = f"https://{cdn_url}"
                    doc = self._classify_document(full_url, url)
                    result.documents.append(doc)
                    if not db.exists(doc.source_url):
                        db.insert(doc)

            # Strategy 2: Find PDF links in page source
            pdf_matches = PDF_LINK_RE.findall(html)
            for pdf_url in set(pdf_matches):
                if not pdf_url.startswith("http"):
                    pdf_url = urljoin(url, pdf_url)
                # Skip already-found CDN URLs
                if any(cdn in pdf_url for cdn in cdn_urls):
                    continue

                doc = self._classify_document(pdf_url, url)
                result.documents.append(doc)
                if not db.exists(doc.source_url):
                    db.insert(doc)

            # Strategy 3: Look for meeting calendar / agenda links
            parsed = urlparse(url)
            agenda_paths = self._find_meeting_paths(html, parsed.netloc)
            for agenda_url in agenda_paths:
                doc = ScrapedDocument(
                    title=f"Meeting page: {agenda_url}",
                    source_url=agenda_url,
                    media_type="HTML",
                    document_class="meeting_agenda",
                    source_system="apptegy",
                    source_label=f"Apptegy — {parsed.netloc}",
                    district_code=district or None,
                    scrape_method="direct_download",
                )
                result.documents.append(doc)

            result.warnings.append(
                f"Found {len(cdn_urls)} CDN URLs, {len(pdf_matches)} PDF links, "
                f"{len(agenda_paths)} meeting pages"
            )

        except Exception as e:
            result.errors.append(f"Failed: {e}")
            strategy.record_failure(
                "Apptegy meeting scrape",
                "apptegy", "url_pattern", url,
                notes=str(e),
            )

        result.finished_at = datetime.now()
        return result

    def _classify_document(self, doc_url: str, source_url: str) -> ScrapedDocument:
        """Classify a document URL based on filename patterns."""
        url_lower = doc_url.lower()
        filename = doc_url.rsplit("/", 1)[-1] if "/" in doc_url else doc_url

        if any(k in url_lower for k in ["agenda", "agnd"]):
            doc_class = "meeting_agenda"
        elif any(k in url_lower for k in ["minute", "min"]):
            doc_class = "meeting_minutes"
        elif any(k in url_lower for k in ["packet", "pkt", "board_docs"]):
            doc_class = "meeting_packet"
        elif any(k in url_lower for k in ["policy", "handbook"]):
            doc_class = "policy_manual"
        elif any(k in url_lower for k in ["budget"]):
            doc_class = "budget"
        else:
            doc_class = "other"

        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

        return ScrapedDocument(
            title=filename,
            source_url=doc_url,
            media_type="PDF" if ext == "pdf" else "HTML",
            file_extension=ext if ext else None,
            document_class=doc_class,
            source_system="apptegy",
            source_label=f"Apptegy — {source_url}",
            scrape_method="direct_download",
        )

    def _find_meeting_paths(self, html: str, domain: str) -> list[str]:
        """Find meeting/agenda/minutes page URLs in HTML."""
        found = []
        path_patterns = [
            r'href=["\']([^"\']*(?:agenda|meeting|minute|board|committee|calendar)[^"\']*)["\']',
        ]
        seen = set()
        for pattern in path_patterns:
            for match in re.finditer(pattern, html, re.IGNORECASE):
                href = match.group(1)
                if href not in seen:
                    seen.add(href)
                    if not href.startswith("http"):
                        href = f"https://{domain}{href}" if href.startswith("/") else f"https://{domain}/{href}"
                    found.append(href)
        return found


# -- Standalone run -------------------------------------------------------
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Apptegy Meeting Document Scraper")
    p.add_argument("--url", help="Direct URL to scrape")
    p.add_argument("--district", help="District slug for known Apptegy sites")
    args = p.parse_args()
    ApptegyMeetingsScraper.cli_run(url=args.url or "", district=args.district or "")
