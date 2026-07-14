# PDF Scraper

**Consolidated scraping system for Massachusetts education data.**

Part of the [Parent Data Force](https://parentdataforce.com) project — scrapes, downloads, verifies, and catalogs public records from DESE, school district meeting portals (Apptegy, CivicEngage, BoardDocs), YouTube channels, and custom websites.

---

## Architecture

```
scraper/
├── cli.py                       # Interactive terminal (11 commands)
├── core/
│   ├── base.py                  # ScrapedDocument dataclass + classification enums
│   ├── scraper.py               # BaseScraper abstract class + ScrapeResult
│   ├── registry.py              # Auto-discovery: drop a .py in scrapers/, it registers
│   ├── pipeline.py              # Download → verify → dedup pipeline
│   ├── db.py                    # DocumentDB — SQLite CRUD with checksum dedup
│   ├── ftp.py                   # FTPUploader — auto directory structure on upload
│   └── strategy.py              # StrategyStore — learned pattern knowledge base (YAML)
├── scrapers/
│   ├── _template.py             # Copy to create new scrapers
│   ├── dese_all.py              # All 6 MA DESE datasets
│   ├── apptegy_meetings.py      # Thrillshare CDN + PDF link extraction
│   ├── civicengage_meetings.py  # Agenda Center PDF scraping
│   ├── youtube_meetings.py      # yt-dlp + HTML fallback for district channels
│   └── boarddocs_meetings.py    # Stub (requires Playwright automation)
├── strategies/
│   └── patterns.yaml            # 8 seed patterns with success/fail tracking
└── migration/
    └── documents_table.sql      # documents + source_systems + scrape_strategies schema
```

## Quick Start

```bash
# Interactive terminal
python -m scraper.cli

# Run a scraper standalone
python scrapers/dese_all.py
python scrapers/apptegy_meetings.py --url https://attleboroschools.apptegy.net/
python scrapers/youtube_meetings.py --channel @attleboroschools

# Run a scraper from the CLI
python -m scraper.cli
scraper> run dese_all
scraper> run apptegy_meetings --url=https://attleboroschools.apptegy.net/
```

## How It Works

### Document Lifecycle

Every document flows through five states:

```
discovered → downloaded → verified → uploaded
                                  ↘ failed
                                  ↘ skipped_duplicate
```

1. **Discover** — a scraper finds a URL and classifies it (media type, document class, source system)
2. **Download** — `ScraperPipeline` downloads the file, computes SHA-256 checksum
3. **Verify** — confirms the file is valid (PDF header check, image verification via PIL)
4. **Upload** — `FTPUploader` sends to production with auto directory structure
5. **Dedup** — checksum-matched files are skipped automatically

### Classification System

Every document is classified by three dimensions:

| Dimension | Values |
|---|---|
| **media_type** | PDF, HTML, video, image, spreadsheet, text, archive, audio, other |
| **document_class** | meeting_agenda, meeting_minutes, meeting_packet, meeting_video, policy_manual, budget, annual_report, school_handbook, sepac_info, prr_response, des_report, correspondence, testimony, legal_filing, media_coverage, other |
| **source_system** | dese, apptegy, civicengage, boarddocs, youtube, custom_html, manual |

### Document Database

The `documents` table tracks everything: source URL, checksum, classification, district code, meeting date, local path, FTP path, status, scrape date, error messages, and scrape method notes.

Accompanying tables:
- `source_systems` — registry of known scraping targets with platform types and rate limits
- `scrape_strategies` — learned patterns for reuse (SQL-backed, separate from the YAML store)

## Creating a New Scraper

```bash
cp scrapers/_template.py scrapers/my_scraper.py
```

Then customize:
1. Change class name, `name`, `display_name`, `source_system`, `help_text`
2. Implement `run(**kwargs) → ScrapeResult`
3. Use `self._get(url)` for HTTP (rate-limited, retry-enabled)
4. Use `self._download_file(url, filename)` for binary downloads
5. Create `ScrapedDocument` objects with proper classification
6. Record strategies: `StrategyStore().record_success(...)` / `record_failure(...)`
7. The registry auto-discovers it on next CLI start

### Scraper Contract

```python
from scraper.core import BaseScraper, ScrapeResult, ScrapedDocument, register_scraper

@register_scraper
class MyScraper(BaseScraper):
    name = "my_scraper"
    display_name = "My Scraper"
    source_system = "custom_html"
    help_text = "What this scraper does"

    def run(self, url: str = "", **kwargs) -> ScrapeResult:
        result = ScrapeResult()
        # ... scrape logic ...
        doc = ScrapedDocument(
            title="...",
            source_url=url,
            media_type="PDF",
            document_class="meeting_agenda",
            source_system=self.source_system,
        )
        result.documents.append(doc)
        return result
```

## Interactive CLI

```bash
python -m scraper.cli
```

| Command | Description |
|---|---|
| `list` | Show all registered scrapers |
| `run <name> [--arg=val]` | Execute a scraper |
| `download all\|<source>\|<url>` | Download pending documents |
| `upload <source_url>` | FTP upload a downloaded document |
| `docs [source\|district]` | Browse scraped documents |
| `sources` | Source system stats |
| `strategies [platform]` | Query learned scraping patterns |
| `strategy-stats` | Strategy store metrics |
| `db` | Document database stats |
| `add` | Manually add a document record |
| `ensure-db` | Create/migrate documents table |

## Strategy Store

The strategy store accumulates patterns over time. When a scraper succeeds or fails, it records the approach. Before writing new scraping logic, query the store for proven patterns:

```python
from scraper.core import StrategyStore

store = StrategyStore()
suggestions = store.suggest("apptegy", pattern_type="url_pattern")
# Returns patterns sorted by success ratio
```

Current stored patterns (8 seed + accumulating):

| Platform | Pattern | Success/Fail |
|---|---|---|
| Apptegy | Thrillshare UUID CDN URLs | 5/5 |
| Apptegy | Subdomain detection (*.apptegy.net) | 8/9 |
| CivicEngage | JS year navigation via changeYear() | 3/3 |
| CivicEngage | PDF links in agenda tables | 3/3 |
| Government portals | DESE Socrata API | 2/2 |
| Government portals | DESE Profiles HTML table parsing | 4/5 |
| YouTube | District channel playlists | 2/2 |
| BoardDocs | Portal URL detection | 0/1 (needs Playwright) |

## FTP Upload

Set `PDF_FTP_PASS` environment variable, then:

```bash
# From the CLI
scraper> upload <document_source_url>

# From code
from scraper.core import FTPUploader
ftp = FTPUploader()
ftp.connect()
remote_path = ftp.upload_document(
    Path("local/file.pdf"),
    district_code="00160000",
    doc_class="meeting_agenda",
    scrape_date="2026-07-14",
)
# → /public_html/documents/00160000/2026/meeting_agendas/file.pdf
```

## Database Migrations

```bash
# Apply to local SQLite dev database
python -m scraper.cli
scraper> ensure-db

# Apply to MariaDB production
mysql -u pdf_user -p pdf_db < migration/documents_table.sql
```

## Platform Support

| Platform | Scraper | Status | Method |
|---|---|---|---|
| **DESE Profiles** | `dese_all` | Production | HTML parsing + Socrata API |
| **Apptegy/Thrillshare** | `apptegy_meetings` | Production | CDN URL pattern matching |
| **CivicEngage** | `civicengage_meetings` | Production | PDF link extraction |
| **YouTube** | `youtube_meetings` | Production | yt-dlp + HTML fallback |
| **BoardDocs** | `boarddocs_meetings` | Stub | Needs Playwright automation |

## Dependencies

```
requests
pyyaml
pillow          # Image verification (optional)
yt-dlp          # YouTube scraper (optional)
rich            # CLI formatting (optional)
```

## Related Repos

- [pdfwebsite](https://github.com/p-d-force/pdfwebsite) — the Parent Data Force website and data portal
- [parentdataforce.com](https://parentdataforce.com) — production deployment

## License

MIT
