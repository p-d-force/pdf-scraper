"""
DESE Consolidated Scraper — wraps all Massachusetts DESE data fetchers.
Runs the existing massachusetts/dese/fetch_*.py scripts and records
their outputs as ScrapedDocument entries in the documents table.

Usage:
  python scrapers/dese_all.py                    # run all
  python scrapers/dese_all.py --dataset restraints  # run one
"""
from __future__ import annotations

import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from scraper.core import (
    BaseScraper, ScrapeResult, ScrapedDocument,
    register_scraper, DocumentDB, StrategyStore,
)


# Map dataset names to their fetch scripts
DESE_SCRIPTS = {
    "restraints":    "fetch_restraints.py",
    "enrollment":    "fetch_enrollment.py",
    "discipline":    "fetch_discipline.py",
    "attendance":    "fetch_attendance.py",
    "prs":           "fetch_prs.py",
    "sped":          "fetch_sped_results.py",
}


@register_scraper
class DESEAllScraper(BaseScraper):
    """Run all DESE data fetchers and record results."""

    name = "dese_all"
    display_name = "DESE All Datasets"
    source_system = "dese"
    help_text = "Fetch all MA DESE datasets (restraints, enrollment, discipline, attendance, PRS, SPED)"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._dese_dir = Path(__file__).resolve().parent.parent / "massachusetts" / "dese"
        self._db = DocumentDB()
        self._db.ensure_table()
        self._strategy = StrategyStore()

    def run(self, dataset: Optional[str] = None, **kwargs) -> ScrapeResult:
        """Run DESE fetchers.

        Args:
            dataset: Specific dataset to fetch (None = all)
        """
        result = ScrapeResult()
        result.started_at = datetime.now()

        datasets = [dataset] if dataset else list(DESE_SCRIPTS.keys())

        if dataset and dataset not in DESE_SCRIPTS:
            result.errors.append(f"Unknown dataset: {dataset}. Available: {list(DESE_SCRIPTS.keys())}")
            result.finished_at = datetime.now()
            return result

        for ds in datasets:
            script = self._dese_dir / DESE_SCRIPTS[ds]
            if not script.exists():
                result.errors.append(f"Script not found: {script}")
                continue

            try:
                print(f"  Running {script.name}...")
                proc = subprocess.run(
                    [sys.executable, str(script)],
                    capture_output=True, text=True, timeout=300,
                    cwd=str(script.parent),
                )

                if proc.returncode != 0:
                    result.errors.append(f"{ds} failed (exit {proc.returncode}): {proc.stderr[:200]}")
                    self._strategy.record_failure(
                        strategy_name=f"DESE {ds} fetch",
                        platform_type="government_portal",
                        pattern_type="api_endpoint" if "socrata" in script.name.lower() else "dom_selector",
                        pattern_value=str(script),
                        notes=f"Exit code {proc.returncode}: {proc.stderr[:200]}",
                    )
                else:
                    # Record the output as a discovered document
                    doc = ScrapedDocument(
                        title=f"DESE {ds.replace('_', ' ').title()} Data",
                        source_url=f"dese://{ds}/{date.today().isoformat()}",
                        media_type="text",
                        document_class="des_report",
                        source_system="dese",
                        source_label=f"DESE {ds} — {date.today().isoformat()}",
                        scrape_method="api_call" if "socrata" in script.name.lower() else "direct_download",
                        scrape_notes=f"Script: {script.name}\nRows: {proc.stdout.count(chr(10))}",
                    )
                    result.documents.append(doc)

                    if not self._db.exists(doc.source_url):
                        self._db.insert(doc)

                    self._strategy.record_success(
                        strategy_name=f"DESE {ds} fetch",
                        platform_type="government_portal",
                        pattern_type="api_endpoint" if "socrata" in script.name.lower() else "dom_selector",
                        pattern_value=str(script),
                        example_url=f"dese://{ds}/{date.today().isoformat()}",
                    )

            except subprocess.TimeoutExpired:
                result.errors.append(f"{ds} timed out after 300s")
            except Exception as e:
                result.errors.append(f"{ds} error: {e}")

        result.finished_at = datetime.now()
        return result


# -- Standalone run -------------------------------------------------------
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="DESE All Datasets Scraper")
    p.add_argument("--dataset", help=f"Specific dataset: {', '.join(DESE_SCRIPTS)}")
    args = p.parse_args()
    DESEAllScraper.cli_run(dataset=args.dataset)
