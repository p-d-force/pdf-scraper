# Scrapers

Five scraper modules, each targeting a different data source platform.

## DESE All (`scrapers/dese_all.py`)

Wraps all six Massachusetts DESE data fetchers.

| Dataset | Script | Method |
|---|---|---|
| Restraints | `fetch_restraints.py` | DESE Profiles HTML parsing |
| Enrollment | `fetch_enrollment.py` | DESE Profiles HTML parsing |
| Discipline | `fetch_discipline.py` | DESE Profiles HTML parsing |
| Attendance | `fetch_attendance.py` | DESE Profiles HTML parsing |
| PRS Complaints | `fetch_prs.py` | Socrata API |
| SPED Results | `fetch_sped_results.py` | Socrata API |

**Usage:**
```bash
python scrapers/dese_all.py                    # All datasets
python scrapers/dese_all.py --dataset restraints  # Single dataset
```

## Apptegy Meetings (`scrapers/apptegy_meetings.py`)

Targets school district websites powered by Apptegy/Thrillshare.

**Strategy:** Apptegy hosts actual PDFs on the Thrillshare CDN (`files-backend.assets.thrillshare.com`) with UUID paths. The listing pages use JavaScript to render meeting tables. The scraper extracts CDN URLs from page source and HTML PDF links.

**Usage:**
```bash
python scrapers/apptegy_meetings.py --url https://attleboroschools.apptegy.net/
python scrapers/apptegy_meetings.py --district attleboro
```

## CivicEngage Meetings (`scrapers/civicengage_meetings.py`)

Targets municipal agenda centers powered by CivicEngage.

**Strategy:** CivicEngage uses JavaScript year navigation via `changeYear()`. The scraper does static HTML parsing for PDF links; full automation requires Selenium/Playwright to call `changeYear()` across years.

**Usage:**
```bash
python scrapers/civicengage_meetings.py --url https://www.cityofattleboro.us/AgendaCenter/
python scrapers/civicengage_meetings.py --district attleboro
```

## YouTube Meetings (`scrapers/youtube_meetings.py`)

Discovers school committee meeting videos from district YouTube channels.

**Strategy:** Uses `yt-dlp` to dump playlist/channel metadata as JSON. Falls back to HTML scraping of watch URLs if yt-dlp is unavailable. Does NOT download videos — records metadata and links to YouTube.

**Usage:**
```bash
python scrapers/youtube_meetings.py --channel @attleboroschools
python scrapers/youtube_meetings.py --playlist https://youtube.com/playlist?list=...
```

## BoardDocs Meetings (`scrapers/boarddocs_meetings.py`)

**Status: Stub.** BoardDocs uses a complex JavaScript SPA that requires Playwright browser automation. The stub records the portal URL for manual follow-up and logs the attempt to the strategy store for future automation.

**Usage:**
```bash
python scrapers/boarddocs_meetings.py --url https://go.boarddocs.com/ma/district/Board.nsf/Public
```

## Template (`scrapers/_template.py`)

Copy this to create new scrapers. Includes `@register_scraper` decorator, `BaseScraper` inheritance, example `run()` method, and standalone CLI entry point.
