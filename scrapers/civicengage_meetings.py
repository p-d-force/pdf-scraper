"""
CivicEngage Meeting Scraper — scrapes meeting agendas and minutes
from CivicEngage-powered municipal agenda centers.

Platform detection: URL contains 'civicengage.com' or '/AgendaCenter/'.

Strategy: CivicEngage agenda centers use JavaScript year navigation via
changeYear(). Use Selenium/Playwright to call changeYear(), then
scrape the resulting table rows for PDF download links.

Two approaches:
  1. JavaScript rendering (Selenium) — navigate years, extract PDF links
  2. Static HTML parsing — works on some CivicEngage installs

Usage:
  python scrapers/civicengage_meetings.py --url https://www.cityofattleboro.us/AgendaCenter/
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


# Known MA municipalities on CivicEngage
MUNICIPAL_URLS = {
    "attleboro": "https://www.cityofattleboro.us/AgendaCenter/",
}


# Meeting date extraction patterns
MEETING_DATE_RE = re.compile(
    r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})',  # 6/15/2024 or 06-15-2024
)
YEAR_RE = re.compile(r'\b(20\d{2})\b')
PDF_HREF_RE = re.compile(r'href=["\']([^"\']+\.pdf)["\']', re.IGNORECASE)


@register_scraper
class CivicEngageMeetingsScraper(BaseScraper):
    """Scrape meeting documents from CivicEngage agenda centers."""

    name = "civicengage_meetings"
    display_name = "CivicEngage Meeting Documents"
    source_system = "civicengage"
    help_text = "Scrape meeting agendas/minutes from CivicEngage Agenda Centers"

    def run(self, url: str = "", district: str = "", **kwargs) -> ScrapeResult:
        """Scrape CivicEngage meeting documents.

        Args:
            url: Direct URL to scrape
            district: Municipality slug for URL lookup
        """
        result = ScrapeResult()
        result.started_at = datetime.now()
        strategy = StrategyStore()
        db = DocumentDB()
        db.ensure_table()

        # Resolve URL
        if not url and district:
            url = MUNICIPAL_URLS.get(district.lower(), "")
        if not url:
            result.errors.append("No URL or district provided.")
            result.finished_at = datetime.now()
            return result

        try:
            print(f"  Fetching {url}...")
            resp = self._get(url)
            resp.raise_for_status()
            html = resp.text

            # Check if CivicEngage
            is_civicengage = "civicengage" in url.lower() or "/agendacenter/" in url.lower()
            if not is_civicengage:
                result.warnings.append(f"URL may not be CivicEngage: {url}")

            # Strategy 1: Extract PDF links directly from HTML
            pdf_urls = self._extract_pdf_urls(html, url)
            for pdf_url, label in pdf_urls:
                doc = self._classify_document(pdf_url, label, url, district)
                result.documents.append(doc)
                if not db.exists(doc.source_url):
                    db.insert(doc)

            if pdf_urls:
                strategy.record_success(
                    "CivicEngage PDF link pattern",
                    "civicengage", "dom_selector",
                    "a[href$='.pdf'] within agenda listing",
                    example_url=url,
                )
            else:
                # Strategy 2: Try to find meeting list pages
                meeting_pages = self._find_meeting_pages(html, url)
                for page_url in meeting_pages:
                    doc = ScrapedDocument(
                        title=f"Meeting page: {page_url}",
                        source_url=page_url,
                        media_type="HTML",
                        document_class="meeting_agenda",
                        source_system="civicengage",
                        source_label=f"CivicEngage — {urlparse(url).netloc}",
                        district_code=district or None,
                        scrape_method="direct_download",
                    )
                    result.documents.append(doc)

                result.warnings.append(
                    f"No PDF links found directly. JS rendering may be needed. "
                    f"Found {len(meeting_pages)} meeting pages to investigate."
                )

        except Exception as e:
            result.errors.append(f"Failed: {e}")
            strategy.record_failure(
                "CivicEngage meeting scrape",
                "civicengage", "url_pattern", url,
                notes=str(e),
            )

        result.finished_at = datetime.now()
        return result

    def _extract_pdf_urls(self, html: str, base_url: str) -> list[tuple[str, str]]:
        """Extract PDF URLs with labels from HTML."""
        results = []
        seen = set()

        # Find all PDF links with surrounding context for labeling
        for match in PDF_HREF_RE.finditer(html):
            href = match.group(1)
            if href in seen:
                continue
            seen.add(href)

            if not href.startswith("http"):
                href = urljoin(base_url, href)

            # Try to extract label from link text or nearby content
            start = max(0, match.start() - 200)
            end = min(len(html), match.end() + 200)
            context = html[start:end]

            label = href.rsplit("/", 1)[-1]  # default: filename

            # Look for date in context
            date_match = MEETING_DATE_RE.search(context)
            if date_match:
                m, d, y = date_match.groups()
                y = y if len(y) == 4 else f"20{y}"
                label = f"{y}-{m.zfill(2)}-{d.zfill(2)}_{label}"

            results.append((href, label))

        return results

    def _find_meeting_pages(self, html: str, base_url: str) -> list[str]:
        """Find meeting-related sub-pages."""
        found = []
        seen = set()
        patterns = [
            r'href=["\']([^"\']*(?:agenda|meeting|minute|calendar|board|committee)[^"\']*)["\']',
        ]
        parsed = urlparse(base_url)
        for pattern in patterns:
            for match in re.finditer(pattern, html, re.IGNORECASE):
                href = match.group(1)
                if href in seen:
                    continue
                seen.add(href)
                if not href.startswith("http"):
                    href = f"https://{parsed.netloc}{href}" if href.startswith("/") else urljoin(base_url, href)
                found.append(href)
        return found

    def _classify_document(self, doc_url: str, label: str, source_url: str,
                           district: str) -> ScrapedDocument:
        """Classify a document based on URL/filename patterns."""
        url_lower = doc_url.lower()

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
        else:
            doc_class = "other"

        ext = label.rsplit(".", 1)[-1].lower() if "." in label else ""

        # Try to extract meeting date from label
        meeting_date = None
        m = MEETING_DATE_RE.search(label)
        if m:
            month, day, year = m.groups()
            year = year if len(year) == 4 else f"20{year}"
            try:
                meeting_date = date(int(year), int(month), int(day))
            except ValueError:
                pass

        return ScrapedDocument(
            title=label,
            source_url=doc_url,
            media_type="PDF" if ext == "pdf" else "HTML",
            file_extension=ext if ext else None,
            document_class=doc_class,
            source_system="civicengage",
            source_label=f"CivicEngage — {urlparse(source_url).netloc}",
            district_code=district or None,
            meeting_date=meeting_date,
            scrape_method="direct_download",
        )


# -- Standalone run -------------------------------------------------------
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="CivicEngage Meeting Document Scraper")
    p.add_argument("--url", help="Direct URL to scrape")
    p.add_argument("--district", help="Municipality slug for known CivicEngage sites")
    args = p.parse_args()
    CivicEngageMeetingsScraper.cli_run(url=args.url or "", district=args.district or "")
