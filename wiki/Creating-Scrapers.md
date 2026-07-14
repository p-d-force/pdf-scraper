# Creating Scrapers

Every scraper follows a standard contract. Copy the template, customize, and it auto-registers.

## Quick Start

```bash
cp scrapers/_template.py scrapers/my_district_scraper.py
```

Then edit the file:

## Required Changes

```python
from scraper.core import BaseScraper, ScrapeResult, ScrapedDocument, register_scraper

@register_scraper                                                  # 1. Auto-registration
class MyDistrictScraper(BaseScraper):                              # 2. Unique class name
    """Scrape meeting documents from My District website."""

    name = "my_district"                                           # 3. Unique CLI name
    display_name = "My District Meeting Documents"                 # 4. Human-readable
    source_system = "custom_html"                                  # 5. Source system
    help_text = "Scrape meeting agendas from mydistrict.gov"       # 6. Help text

    def run(self, url: str = "", **kwargs) -> ScrapeResult:       # 7. Main logic
        result = ScrapeResult()
        result.started_at = datetime.now()

        try:
            # Fetch the page
            resp = self._get(url)
            resp.raise_for_status()

            # Parse and extract documents
            for pdf_url in self._extract_pdfs(resp.text, url):
                doc = ScrapedDocument(
                    title=self._get_title(pdf_url),
                    source_url=pdf_url,
                    media_type="PDF",
                    document_class="meeting_agenda",
                    source_system=self.source_system,
                    scrape_method="direct_download",
                )
                result.documents.append(doc)

                # Save to database
                db = DocumentDB()
                if not db.exists(doc.source_url):
                    db.insert(doc)

            # Record successful strategy
            StrategyStore().record_success(
                "My District PDF extraction",
                self.source_system, "dom_selector",
                "a.meeting-pdf[href$='.pdf']",
                example_url=url,
            )

        except Exception as e:
            result.errors.append(str(e))
            StrategyStore().record_failure(
                "My District scrape",
                self.source_system, "url_pattern", url,
                notes=str(e),
            )

        result.finished_at = datetime.now()
        return result

# Standalone run
if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else ""
    MyDistrictScraper.cli_run(url=url)
```

## Key Methods

### `self._get(url)` → Response

Rate-limited HTTP GET with automatic retries (3 attempts, backoff). Respects `self.rate_limit` (default: 3 seconds between requests).

### `self._download_file(url, filename)` → Path

Downloads a binary file with streaming, returns local path. Handles filename conflicts by appending timestamp.

### Document Classification

Always set `media_type`, `document_class`, and `source_system`. See `scraper/core/base.py` for the full list of valid values.

### Strategy Recording

After every run, record the outcome:
- `StrategyStore().record_success(...)` for patterns that worked
- `StrategyStore().record_failure(...)` for patterns that failed

This builds the knowledge base for future scrapers.

## Testing

```bash
# Standalone
python scrapers/my_district_scraper.py --url=https://example.com

# Via CLI
python -m scraper.cli
scraper> run my_district --url=https://example.com
```

## Classification Reference

| `media_type` | `document_class` |
|---|---|
| PDF | meeting_agenda, meeting_minutes, meeting_packet, policy_manual, budget, annual_report, school_handbook, sepac_info, prr_response, des_report, correspondence, testimony, legal_filing, media_coverage, other |
| HTML | _(same as above)_ |
| video | meeting_video, media_coverage, other |
| image | media_coverage, other |
| spreadsheet | budget, des_report, other |
| text | correspondence, testimony, other |
