"""
Template Scraper — copy and customize for new scrapers.

To create a new scraper:
  1. Copy this file to scrapers/<your_scraper>.py
  2. Change the class name, name, display_name, source_system, help_text
  3. Implement the run() method
  4. The registry auto-discovers it on next CLI start

Each run() should:
  - Return a ScrapeResult with ScrapedDocument objects
  - Use self._get() for HTTP GETs (rate-limited, retry-enabled)
  - Use self._download_file() for binary downloads
  - Call self.strategy.record_success() / record_failure() for learning
"""
from __future__ import annotations

from scraper.core import BaseScraper, ScrapeResult, ScrapedDocument, register_scraper, StrategyStore


@register_scraper
class TemplateScraper(BaseScraper):
    """Template — copy this to create a new scraper."""

    name = "template"
    display_name = "Template Scraper"
    source_system = "manual"
    help_text = "Template for new scrapers. Copy and customize."

    def run(self, url: str = "", **kwargs) -> ScrapeResult:
        """Main scraping logic.

        Args:
            url: Starting URL to scrape
        """
        result = ScrapeResult()
        result.started_at = __import__("datetime").datetime.now()

        if not url:
            result.warnings.append("No URL provided — nothing to scrape.")
            result.finished_at = __import__("datetime").datetime.now()
            return result

        try:
            # 1. Fetch the page
            resp = self._get(url)
            resp.raise_for_status()

            # 2. Parse and extract documents
            #    (Replace this with your actual parsing logic)
            doc = ScrapedDocument(
                title=f"Document from {url}",
                source_url=url,
                media_type="HTML",
                document_class="other",
                source_system=self.source_system,
                scrape_method="direct_download",
            )
            result.documents.append(doc)

            # 3. Record successful strategy for learning
            strategy = StrategyStore()
            strategy.record_success(
                strategy_name="Template direct fetch",
                platform_type=self.source_system,
                pattern_type="direct_download",
                pattern_value=url,
                example_url=url,
            )

        except Exception as e:
            result.errors.append(f"Failed to scrape {url}: {e}")

        result.finished_at = __import__("datetime").datetime.now()
        return result


# -- Standalone run -------------------------------------------------------
if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    TemplateScraper.cli_run(url=url)
