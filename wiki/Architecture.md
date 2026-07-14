# Architecture

The PDF Scraper is built around four core abstractions that compose into a full document pipeline.

## Component Diagram

```
┌─────────────────────────────────────────────────────┐
│                  Interactive CLI                     │
│                  (scraper/cli.py)                    │
│          list | run | download | upload | docs       │
└──────────────────────┬──────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
   ┌────┴────┐   ┌────┴────┐   ┌─────┴─────┐
   │Registry │   │Pipeline │   │Strategy   │
   │         │   │         │   │Store      │
   │discovers│   │downloads│   │learns     │
   │scrapers │   │verifies │   │patterns   │
   └────┬────┘   └────┬────┘   └─────┬─────┘
        │              │              │
   ┌────┴────┐   ┌────┴────┐   ┌─────┴─────┐
   │Scrapers │   │  FTP    │   │patterns   │
   │         │   │Uploader │   │.yaml      │
   │5 modules│   │         │   │           │
   └────┬────┘   └────┬────┘   └───────────┘
        │              │
   ┌────┴──────────────┴────┐
   │     DocumentDB         │
   │     SQLite CRUD        │
   │     checksum dedup     │
   └────────────────────────┘
```

## Core Abstractions

### ScrapedDocument (`core/base.py`)

The universal record. Every document — whether a PDF agenda, YouTube video, or HTML page — flows through the system as a `ScrapedDocument` dataclass. It carries:

- **Identity:** title, source_url, checksum
- **Classification:** media_type, document_class, file_type, source_system
- **Context:** district_code, meeting_date, source_label
- **Lifecycle:** status (discovered/downloaded/verified/uploaded/failed), scrape_date, file_path, ftp_path
- **Strategy:** scrape_method, scrape_notes

### BaseScraper (`core/scraper.py`)

Abstract base that every scraper inherits. Provides:

- Rate-limited HTTP GET via `self._get(url)`
- Binary file download via `self._download_file(url, filename)`
- CLI standalone entry point via `cls.cli_run()`
- Pretty-printed results via `_print_result()`

### ScraperRegistry (`core/registry.py`)

Singleton that auto-discovers scrapers. On import of `scrapers/*.py`, the `@register_scraper` decorator registers the class. The CLI calls `registry.discover()` on startup. Scrapers can be listed, queried by source system, and executed by name.

### ScraperPipeline (`core/pipeline.py`)

Orchestrates the download → verify → dedup flow. Used by scrapers after discovery:

1. Downloads the file with rate limiting
2. Detects actual media type from Content-Type header
3. Verifies file integrity (PDF header check, image verification)
4. Computes SHA-256 checksum
5. Checks for duplicates via `DocumentDB.find_by_checksum()`
6. Inserts or updates the documents table

### DocumentDB (`core/db.py`)

Thin SQLite wrapper for the `documents` table. Handles insert, update, checksum dedup, source/district listing, and stats. Works with both the local dev database and production.

### FTPUploader (`core/ftp.py`)

Uploads verified documents to production. Automatic directory structure: `/public_html/documents/<district>/<year>/<class>/filename`. Uses `PDF_FTP_PASS` environment variable for credentials.

### StrategyStore (`core/strategy.py`)

YAML-based knowledge base that accumulates scraping patterns. Each pattern tracks success/fail counts, last used, example URLs. Before writing new scraping logic, query for proven patterns by platform and pattern type.

## Design Principles

1. **Every scraper runs standalone AND via registry.** No lock-in to the CLI.
2. **Classification is explicit.** No guessing media types or document classes from filenames alone.
3. **Dedup by checksum, not URL.** Same file at different URLs = one document.
4. **Strategies accumulate.** Every success and failure is recorded for future use.
5. **No silent failures.** Every error goes into `ScrapeResult.errors` and the strategy store.
