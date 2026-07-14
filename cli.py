#!/usr/bin/env python3
"""
Interactive scraping terminal.
─────────────────────────────
Run:  python -m scraper.cli
Or:   python scraper/cli.py

Provides a rich TUI for:
  - Discovering and running scrapers
  - Browsing scraped documents
  - Uploading to FTP
  - Querying the strategy store
  - Manual document entry

Type 'help' for commands, 'quit' to exit.
"""
from __future__ import annotations

import cmd
import os
import shlex
import sys
import textwrap
from datetime import date, datetime
from pathlib import Path
from typing import Optional

# Add project root to path so imports work when run directly
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.markdown import Markdown
    from rich import box
    RICH = True
except ImportError:
    RICH = False

from scraper.core import (
    ScrapedDocument, BaseScraper, ScrapeResult,
    ScraperRegistry, DocumentDB, FTPUploader, StrategyStore,
    DOCUMENT_CLASSES, MEDIA_TYPES, SOURCE_SYSTEMS,
)


class ScraperShell(cmd.Cmd):
    """Interactive scraping terminal."""

    intro = textwrap.dedent("""
    ╔══════════════════════════════════════════════════════════╗
    ║        Parent Data Force — Scraping Terminal             ║
    ║        Type 'help' or '?' for commands                   ║
    ╚══════════════════════════════════════════════════════════╝
    """).strip()
    prompt = "\nscraper> "

    def __init__(self):
        super().__init__()
        self.registry = ScraperRegistry.get()
        self.db = DocumentDB()
        self.ftp = FTPUploader()
        self.strategy = StrategyStore()
        self.results: list[ScrapeResult] = []  # session history

        # Rich console if available
        self.console = Console() if RICH else None

        # Auto-discover scrapers
        scrapers_dir = _project_root / "scraper" / "scrapers"
        self.registry.discover(scrapers_dir)
        self._welcome()

    def _welcome(self):
        names = self.registry.list_names()
        if self.console:
            self.console.print(f"\n[bold green]✓[/] Loaded [bold]{len(names)}[/] scrapers: "
                              f"{', '.join(names) if names else 'none'}")
            if not self.ftp.configured:
                self.console.print("[yellow]⚠[/] FTP not configured — set PDF_FTP_PASS")
        else:
            print(f"\nLoaded {len(names)} scrapers: {', '.join(names) if names else 'none'}")
            if not self.ftp.configured:
                print("⚠  FTP not configured — set PDF_FTP_PASS")

    # -- Commands ---------------------------------------------------------

    def do_list(self, arg: str):
        """list [source] — List available scrapers. Filter by source system."""
        scrapers = self.registry.list_all()
        if arg:
            scrapers = [s for s in scrapers
                       if getattr(s, "source_system", "") == arg.strip()]

        if self.console:
            table = Table(title="Available Scrapers", box=box.ROUNDED)
            table.add_column("Name", style="cyan")
            table.add_column("Source", style="green")
            table.add_column("Description")
            for s in scrapers:
                table.add_row(
                    getattr(s, "name", "?"),
                    getattr(s, "source_system", "?"),
                    getattr(s, "help_text", "")[:80],
                )
            self.console.print(table)
        else:
            print(f"\n{'Name':<25} {'Source':<15} Description")
            print("-" * 80)
            for s in scrapers:
                print(f"{getattr(s, 'name', '?'):<25} {getattr(s, 'source_system', '?'):<15} "
                      f"{getattr(s, 'help_text', '')[:50]}")

    def do_run(self, arg: str):
        """run <name> [--arg=val ...] — Run a scraper."""
        parts = shlex.split(arg)
        if not parts:
            print("Usage: run <scraper_name> [--arg=val ...]")
            return

        name = parts[0]
        kwargs = {}
        for p in parts[1:]:
            if p.startswith("--") and "=" in p:
                k, v = p[2:].split("=", 1)
                kwargs[k] = v

        scraper = self.registry.get_scraper(name)
        if scraper is None:
            print(f"Unknown scraper: {name}")
            print(f"Available: {self.registry.list_names()}")
            return

        print(f"\nRunning {scraper.display_name}...")

        # Set download dir
        if "download_dir" not in kwargs:
            kwargs["download_dir"] = str(
                _project_root / "data" / "downloads" / scraper.source_system
            )

        result = self.registry.run(name, **kwargs)
        if result:
            self.results.append(result)
            self._print_result(result)

    def do_sources(self, arg: str):
        """sources — List known source systems and their document counts."""
        stats = self.db.stats()
        if self.console:
            table = Table(title="Source Systems", box=box.ROUNDED)
            table.add_column("Source", style="cyan")
            table.add_column("Documents")
            for src, count in stats.get("by_source", {}).items():
                table.add_column(src, str(count))
            self.console.print(table)
            self.console.print(f"\n[bold]Total documents:[/] {stats['total']}")
        else:
            print(f"\n{'Source':<20} Documents")
            print("-" * 35)
            for src, count in stats.get("by_source", {}).items():
                print(f"{src:<20} {count}")
            print(f"\nTotal: {stats['total']}")

    def do_docs(self, arg: str):
        """docs [source|district] — Browse scraped documents."""
        if not arg:
            # Show summary
            stats = self.db.stats()
            if self.console:
                self.console.print(f"\n[bold]Documents:[/] {stats['total']} total")
                table = Table(box=box.SIMPLE)
                table.add_column("Status", style="cyan")
                table.add_column("Count")
                for status, count in stats.get("by_status", {}).items():
                    table.add_row(status, str(count))
                self.console.print(table)
            else:
                print(f"\nDocuments: {stats['total']} total")
                for status, count in stats.get("by_status", {}).items():
                    print(f"  {status}: {count}")
            return

        arg = arg.strip()
        if arg in SOURCE_SYSTEMS:
            rows = self.db.list_by_source(arg, limit=50)
        else:
            rows = self.db.list_by_district(arg, limit=50)

        if self.console:
            table = Table(title=f"Documents — {arg}", box=box.ROUNDED)
            table.add_column("Status")
            table.add_column("Title", style="cyan")
            table.add_column("Class", style="green")
            table.add_column("Date")
            for r in rows:
                icon = {"discovered": "?", "downloaded": "↓", "uploaded": "↑",
                        "failed": "✗", "skipped_duplicate": "≅"}.get(r["status"], "?")
                table.add_row(icon, r["title"][:60], r["document_class"], r["scrape_date"] or "")
            self.console.print(table)
        else:
            for r in rows:
                icon = {"discovered": "?", "downloaded": "↓", "uploaded": "↑",
                        "failed": "✗", "skipped_duplicate": "≅"}.get(r["status"], "?")
                print(f"  [{icon}] {r['title'][:60]:<60} | {r['document_class']:<20} | {r['scrape_date']}")

    def do_upload(self, arg: str):
        """upload <doc_id> — Upload a downloaded document to FTP."""
        if not arg:
            print("Usage: upload <document_source_url_or_id>")
            return

        if not self.ftp.configured:
            print("FTP not configured. Set PDF_FTP_PASS environment variable.")
            return

        # Try to find the document
        doc = self.db.get_by_url(arg.strip())
        if not doc:
            # Try as ID
            try:
                doc_id = int(arg.strip())
                doc = self.db.get_by_url(arg.strip())  # won't find by ID this way
                print("Use the source URL to identify the document (try 'docs' first)")
            except ValueError:
                pass
            return

        if doc["status"] not in ("downloaded", "verified"):
            print(f"Document status is '{doc['status']}' — must be downloaded first.")
            return

        local = doc.get("file_path")
        if not local or not Path(local).exists():
            print(f"Local file not found: {local}")
            return

        try:
            self.ftp.connect()
            remote_path = self.ftp.upload_document(
                Path(local),
                district_code=doc.get("district_code"),
                doc_class=doc.get("document_class"),
                scrape_date=doc.get("scrape_date"),
            )
            self.db.update_status(doc["source_url"], "uploaded", ftp_path=remote_path,
                                 ftp_uploaded_at=datetime.now().isoformat())
            print(f"Uploaded → {remote_path}")
        except Exception as e:
            print(f"Upload failed: {e}")
            self.db.update_status(doc["source_url"], "failed", error_message=str(e))
        finally:
            self.ftp.disconnect()

    def do_download(self, arg: str):
        """download [source|all|url] — Download discovered documents.

        download all              download all pending documents
        download apptegy          download all pending from source
        download <source_url>     download a single document by URL
        """
        from scraper.core.pipeline import ScraperPipeline

        arg = arg.strip()

        if arg in ("all", ""):
            docs = self._get_pending_documents()
            if not docs:
                print("No pending documents to download.")
                return
            print(f"Downloading {len(docs)} pending documents...")
            pipeline = ScraperPipeline()
            pipeline.process_batch(docs)
            print(f"\nDone: {pipeline.stats['downloaded']} downloaded, "
                  f"{pipeline.stats['skipped']} skipped, "
                  f"{pipeline.stats['failed']} failed, "
                  f"{pipeline.stats['bytes'] / 1024 / 1024:.1f} MB")
            pipeline.close()
        elif arg in SOURCE_SYSTEMS:
            docs = self._get_pending_documents(source=arg)
            if not docs:
                print(f"No pending documents for source '{arg}'.")
                return
            print(f"Downloading {len(docs)} pending documents from {arg}...")
            pipeline = ScraperPipeline()
            pipeline.process_batch(docs, subdir=arg)
            print(f"\nDone: {pipeline.stats['downloaded']} downloaded, "
                  f"{pipeline.stats['skipped']} skipped, "
                  f"{pipeline.stats['failed']} failed")
            pipeline.close()
        else:
            doc = self.db.get_by_url(arg)
            if not doc:
                print(f"Document not found: {arg}")
                return
            sd = ScrapedDocument(
                title=doc["title"],
                source_url=doc["source_url"],
                media_type=doc["media_type"],
                document_class=doc["document_class"],
                source_system=doc["source_system"],
                district_code=doc.get("district_code"),
                meeting_date=doc.get("meeting_date"),
            )
            pipeline = ScraperPipeline()
            result = pipeline.process(sd)
            print(f"  {result.summary()}")
            pipeline.close()

    def _get_pending_documents(self, source: str = "") -> list[ScrapedDocument]:
        """Get all documents that need downloading (not yet saved to disk)."""
        import sqlite3
        conn = sqlite3.connect(str(self.db.db_path))
        conn.row_factory = sqlite3.Row
        query = "SELECT * FROM documents WHERE status IN ('discovered', 'failed')"
        params = []
        if source:
            query += " AND source_system = ?"
            params.append(source)
        query += " ORDER BY scrape_date DESC LIMIT 100"
        rows = conn.execute(query, params).fetchall()
        conn.close()
        docs = []
        for r in rows:
            d = dict(r)
            try:
                from datetime import date
                mtg = date.fromisoformat(d["meeting_date"]) if d.get("meeting_date") else None
            except (ValueError, TypeError):
                mtg = None
            docs.append(ScrapedDocument(
                title=d["title"],
                source_url=d["source_url"],
                media_type=d["media_type"],
                document_class=d["document_class"],
                source_system=d["source_system"],
                district_code=d.get("district_code"),
                meeting_date=mtg,
            ))
        return docs


    def do_sessions(self, arg: str):
        """sessions — Show recent scrape session history."""
        from scraper.core.session_tracker import SessionTracker
        tracker = SessionTracker()
        tracker.ensure_table()
        recent = tracker.recent_sessions(limit=10)
        stats = tracker.stats()

        if self.console:
            self.console.print(f"\n[bold]Recent Sessions[/] ({stats['total_sessions']} total)")
            table = Table(box=box.SIMPLE)
            table.add_column("Scraper", style="cyan")
            table.add_column("Started")
            table.add_column("Docs", justify="right")
            table.add_column("Status", style="green")
            for s in recent:
                started = s["started_at"][:16] if s.get("started_at") else "?"
                docs = f"{s.get('documents_found', 0)} found / {s.get('documents_down', 0)} down"
                table.add_row(s["scraper_name"], started, docs, s["status"])
            self.console.print(table)
        else:
            print(f"\nRecent Sessions ({stats['total_sessions']} total):")
            print(f"{'Scraper':<25} {'Started':<18} {'Docs':<20} Status")
            print("-" * 80)
            for s in recent:
                started = s["started_at"][:16] if s.get("started_at") else "?"
                docs = f"{s.get('documents_found', 0)}f/{s.get('documents_down', 0)}d"
                print(f"{s['scraper_name']:<25} {started:<18} {docs:<20} {s['status']}")
        tracker.close()

    def do_strategies(self, arg: str):
        """strategies [platform] — Browse learned scraping strategies."""
        if arg:
            suggestions = self.strategy.suggest(arg.strip())
        else:
            suggestions = self.strategy.list_all()

        if self.console:
            table = Table(title="Learned Strategies", box=box.ROUNDED)
            table.add_column("Strategy", style="cyan")
            table.add_column("Platform", style="green")
            table.add_column("Type")
            table.add_column("Success/Fail")
            for s in suggestions:
                ratio = f"{s['success_count']}/{s['success_count'] + s['fail_count']}"
                table.add_row(s["strategy_name"], s["platform_type"],
                             s["pattern_type"], ratio)
            self.console.print(table)
        else:
            print(f"\n{'Strategy':<40} {'Platform':<15} {'Type':<18} S/F")
            print("-" * 90)
            for s in suggestions:
                ratio = f"{s['success_count']}/{s['success_count'] + s['fail_count']}"
                print(f"{s['strategy_name']:<40} {s['platform_type']:<15} "
                      f"{s['pattern_type']:<18} {ratio}")

    def do_add(self, arg: str):
        """add — Manually add a document record."""
        print("\nManual document entry:")
        title = input("  Title: ").strip()
        if not title:
            print("Cancelled.")
            return

        url = input("  Source URL: ").strip()
        doc_class = self._pick("  Document class", DOCUMENT_CLASSES)
        media_type = self._pick("  Media type", MEDIA_TYPES)
        source_system = self._pick("  Source system", SOURCE_SYSTEMS)
        district = input("  District code (or blank): ").strip() or None

        doc = ScrapedDocument(
            title=title,
            source_url=url,
            media_type=media_type,
            document_class=doc_class,
            source_system=source_system,
            district_code=district,
            scrape_method="manual",
            scrape_notes="Manual entry via CLI.",
        )
        self.db.insert(doc)
        print(f"  ✓ Added: {title}")

    def do_db(self, arg: str):
        """db — Show document database stats."""
        stats = self.db.stats()
        if self.console:
            self.console.print(f"\n[bold]Total documents:[/] {stats['total']}")
            self.console.print(f"[bold]By status:[/]")
            for s, n in stats["by_status"].items():
                self.console.print(f"  {s}: {n}")
            self.console.print(f"[bold]By source:[/]")
            for s, n in stats["by_source"].items():
                self.console.print(f"  {s}: {n}")
        else:
            print(f"\nTotal: {stats['total']}")
            print(f"By status: {stats['by_status']}")
            print(f"By source: {stats['by_source']}")

    def do_strategy_stats(self, arg: str):
        """strategy-stats — Show strategy store statistics."""
        stats = self.strategy.stats()
        if self.console:
            self.console.print(f"\n[bold]Strategy Store:[/]")
            self.console.print(f"  Patterns: {stats['total_patterns']}")
            self.console.print(f"  Successes recorded: {stats['total_successes']}")
            self.console.print(f"  Failures recorded: {stats['total_failures']}")
        else:
            print(f"\nStrategy Store:")
            print(f"  Patterns: {stats['total_patterns']}")
            print(f"  Successes: {stats['total_successes']}")
            print(f"  Failures: {stats['total_failures']}")

    def do_ensure_db(self, arg: str):
        """ensure-db — Create documents table if it doesn't exist."""
        self.db.ensure_table()
        print("Documents table ready.")

    def do_quit(self, arg: str):
        """quit — Exit the terminal."""
        print("Goodbye.")
        self.db.close()
        return True

    def do_exit(self, arg: str):
        """exit — Exit the terminal."""
        return self.do_quit(arg)

    def do_EOF(self, arg: str):
        """Ctrl+D — Exit."""
        print()
        return self.do_quit(arg)

    # -- Helpers ----------------------------------------------------------

    def _print_result(self, result: ScrapeResult):
        if self.console:
            self.console.print(f"\n[bold]Results:[/] {len(result.documents)} docs "
                              f"in {result.elapsed:.1f}s")
            if result.documents:
                self.console.print(f"  [green]↓[/] "
                    f"{sum(1 for d in result.documents if d.status == 'downloaded')} downloaded, "
                    f"[yellow]?[/] "
                    f"{sum(1 for d in result.documents if d.status == 'discovered')} discovered, "
                    f"[red]✗[/] "
                    f"{sum(1 for d in result.documents if d.status == 'failed')} failed")
            if result.errors:
                for err in result.errors[:3]:
                    self.console.print(f"  [red]✗[/] {err}")
        else:
            BaseScraper._print_result(result)

    def _pick(self, label: str, options: list[str]) -> str:
        """Interactive option picker."""
        print(f"\n{label}:")
        for i, opt in enumerate(options, 1):
            print(f"  {i}. {opt}")
        while True:
            try:
                choice = input(f"  Choose (1-{len(options)}): ").strip()
                idx = int(choice) - 1
                if 0 <= idx < len(options):
                    return options[idx]
            except (ValueError, IndexError):
                pass
            print(f"  Enter 1-{len(options)}")


def main():
    """Entry point."""
    # Ensure DB table exists
    try:
        db = DocumentDB()
        db.ensure_table()
        db.close()
    except Exception as e:
        print(f"Warning: Could not initialize DB: {e}")

    shell = ScraperShell()
    try:
        shell.cmdloop()
    except KeyboardInterrupt:
        print("\nGoodbye.")
        shell.db.close()


if __name__ == "__main__":
    main()
