"""
BoardDocs Meeting Scraper — Playwright-based scraper for BoardDocs-powered
school district meeting portals.

BoardDocs uses a complex JavaScript SPA (Single Page Application) at:
  https://go.boarddocs.com/{state}/{district}/Board.nsf/Public

This scraper uses Playwright to:
  1. Navigate to the public portal
  2. Wait for the meeting list to render
  3. Extract meeting entries with dates, types, and agenda links
  4. Navigate to individual meeting pages for document downloads
  5. Download and classify PDFs (agendas, minutes, packets)

Usage:
  python scrapers/boarddocs_meetings.py --url https://go.boarddocs.com/ma/attleboro/Board.nsf/Public
"""
from __future__ import annotations

import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from scraper.core import (
    ScrapeResult, ScrapedDocument,
    register_scraper, DocumentDB, StrategyStore,
    PlaywrightScraper, PLAYWRIGHT_AVAILABLE,
)


# Meeting type patterns in BoardDocs titles
MEETING_TYPE_PATTERNS = [
    (re.compile(r"school\s+committee", re.I), "School Committee"),
    (re.compile(r"policy\s+subcommittee", re.I), "Policy Subcommittee"),
    (re.compile(r"finance\s+subcommittee", re.I), "Finance Subcommittee"),
    (re.compile(r"teaching.*learning", re.I), "Teaching & Learning"),
    (re.compile(r"infrastructure", re.I), "Infrastructure"),
    (re.compile(r"special\s+education", re.I), "Special Education"),
    (re.compile(r"negotiation", re.I), "Negotiations"),
    (re.compile(r"budget", re.I), "Budget"),
    (re.compile(r"workshop", re.I), "Workshop"),
    (re.compile(r"executive\s+session", re.I), "Executive Session"),
    (re.compile(r"regular\s+meeting", re.I), "Regular Meeting"),
    (re.compile(r"special\s+meeting", re.I), "Special Meeting"),
]


@register_scraper
class BoardDocsMeetingsScraper(PlaywrightScraper):
    """Scrape meeting documents from BoardDocs SPA portals."""

    name = "boarddocs_meetings"
    display_name = "BoardDocs Meeting Documents"
    source_system = "boarddocs"
    help_text = "Scrape meeting agendas/minutes from BoardDocs portals (requires Playwright)"

    def run(self, url: str = "", **kwargs) -> ScrapeResult:
        """Scrape BoardDocs portal for meeting documents.

        Args:
            url: BoardDocs portal URL (e.g., https://go.boarddocs.com/ma/attleboro/Board.nsf/Public)
        """
        result = ScrapeResult()
        result.started_at = datetime.now()
        strategy = StrategyStore()
        db = DocumentDB()
        db.ensure_table()

        if not PLAYWRIGHT_AVAILABLE:
            result.errors.append(
                "Playwright not installed. Install with: "
                "pip install playwright && playwright install chromium"
            )
            result.finished_at = datetime.now()
            return result

        if not url:
            result.errors.append("No URL provided.")
            result.finished_at = datetime.now()
            return result

        if "boarddocs.com" not in url.lower():
            result.warnings.append(f"URL may not be BoardDocs: {url}")

        try:
            print(f"  Loading {url}...")
            self.navigate(url)

            # Wait for meeting list to render (BoardDocs uses dynamic loading)
            try:
                self.wait_for("table", timeout=15)
            except Exception:
                # Try alternative selectors
                try:
                    self.wait_for(".meeting-table", timeout=10)
                except Exception:
                    result.warnings.append(
                        "Meeting table not found. Page may require additional "
                        "navigation. Screenshot saved for analysis."
                    )

            # Extract meeting entries
            meetings = self._extract_meetings()
            print(f"  Found {len(meetings)} meeting entries")

            for meeting in meetings:
                # Create document record for the meeting page
                doc = ScrapedDocument(
                    title=meeting.get("title", "BoardDocs Meeting"),
                    source_url=meeting.get("url", url),
                    media_type="HTML",
                    document_class="meeting_agenda",
                    source_system="boarddocs",
                    source_label=f"BoardDocs — {url}",
                    meeting_date=meeting.get("date"),
                    scrape_method="playwright_click",
                    scrape_notes=f"Meeting type: {meeting.get('type', 'unknown')}",
                )
                result.documents.append(doc)
                if not db.exists(doc.source_url):
                    db.insert(doc)

                # Try to find PDF links within the meeting entry
                pdf_links = self._extract_meeting_pdfs(meeting)
                for pdf_url, pdf_label in pdf_links:
                    media_type, doc_class = self.classify_from_url(pdf_url)
                    pdf_doc = ScrapedDocument(
                        title=pdf_label or meeting.get("title", "PDF"),
                        source_url=pdf_url,
                        media_type=media_type,
                        document_class=doc_class,
                        source_system="boarddocs",
                        source_label=f"BoardDocs — {url}",
                        meeting_date=meeting.get("date"),
                        scrape_method="playwright_click",
                    )
                    result.documents.append(pdf_doc)
                    if not db.exists(pdf_doc.source_url):
                        db.insert(pdf_doc)

            if meetings:
                strategy.record_success(
                    "BoardDocs meeting extraction",
                    "boarddocs", "navigation_flow",
                    "Playwright: navigate → wait for table → extract meetings",
                    example_url=url,
                )
            else:
                strategy.record_failure(
                    "BoardDocs meeting extraction",
                    "boarddocs", "navigation_flow", url,
                    notes="No meetings found. BoardDocs SPA structure may have changed.",
                )

        except Exception as e:
            result.errors.append(f"BoardDocs scrape failed: {e}")
            strategy.record_failure(
                "BoardDocs meeting scrape",
                "boarddocs", "url_pattern", url,
                notes=str(e),
            )

        finally:
            self.close_browser()

        result.finished_at = datetime.now()
        self.process_results(result, download=False)  # Don't auto-download from SPA
        return result

    def _extract_meetings(self) -> list[dict]:
        """Extract meeting entries from the BoardDocs page."""
        meetings = self.page.evaluate("""() => {
            const meetings = [];
            // BoardDocs typically uses a table or list structure
            const rows = document.querySelectorAll(
                'table tr, .meeting-row, .meeting-entry, [class*="meeting"]'
            );

            rows.forEach(row => {
                const links = row.querySelectorAll('a');
                if (!links.length) return;

                // Find the main meeting link
                const mainLink = Array.from(links).find(a =>
                    a.href && !a.href.endsWith('.pdf')
                ) || links[0];

                // Extract date from text
                const text = row.textContent || '';
                const dateMatch = text.match(
                    /(\\d{1,2})[\\/\\-](\\d{1,2})[\\/\\-](\\d{2,4})/
                );

                let meetingDate = null;
                if (dateMatch) {
                    const [m, d, y] = dateMatch.slice(1);
                    const year = y.length === 2 ? '20' + y : y;
                    meetingDate = `${year}-${m.padStart(2, '0')}-${d.padStart(2, '0')}`;
                }

                meetings.push({
                    title: mainLink.textContent.trim(),
                    url: mainLink.href,
                    date: meetingDate,
                    type: text,
                });
            });

            return meetings;
        }""")

        # Classify meeting types
        for m in meetings:
            for pattern, mtype in MEETING_TYPE_PATTERNS:
                if pattern.search(m.get("type", "")):
                    m["type"] = mtype
                    break
            else:
                m["type"] = "Unknown"

        # Parse dates
        for m in meetings:
            if m.get("date") and isinstance(m["date"], str):
                try:
                    m["date"] = date.fromisoformat(m["date"])
                except ValueError:
                    m["date"] = None

        return meetings

    def _extract_meeting_pdfs(self, meeting: dict) -> list[tuple[str, str]]:
        """Try to navigate to meeting page and find PDF links."""
        pdfs = []
        meeting_url = meeting.get("url", "")
        if not meeting_url:
            return pdfs

        try:
            # Navigate to the meeting page
            self.page.goto(meeting_url, wait_until="networkidle", timeout=15000)

            # Find PDF links
            pdf_links = self.page.evaluate("""() => {
                const links = [];
                document.querySelectorAll('a[href$=".pdf"], a[href*=".pdf?"]').forEach(a => {
                    links.push({url: a.href, text: a.textContent.trim().substring(0, 100)});
                });
                return links;
            }""")

            for link in pdf_links:
                pdfs.append((link["url"], link["text"]))

        except Exception:
            pass  # If meeting page fails, just return what we have

        return pdfs


# -- Standalone run -------------------------------------------------------
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="BoardDocs Meeting Document Scraper")
    p.add_argument("--url", required=True, help="BoardDocs portal URL")
    p.add_argument("--no-headless", action="store_true", help="Show browser window")
    p.add_argument("--no-download", action="store_true", help="Skip auto-download")
    args = p.parse_args()

    BoardDocsMeetingsScraper.cli_run(
        url=args.url,
        headless=not args.no_headless,
        download=not args.no_download,
    )
