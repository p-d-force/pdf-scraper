# CLI Reference

The interactive terminal is the primary interface for running scrapers, managing documents, and querying the knowledge base.

## Starting

```bash
python -m scraper.cli
```

## Commands

### `list [source]`

List all registered scrapers. Filter by source system.

```
scraper> list
scraper> list apptegy
```

### `run <name> [--arg=val ...]`

Execute a scraper by name with optional arguments.

```
scraper> run dese_all
scraper> run dese_all --dataset=restraints
scraper> run apptegy_meetings --url=https://attleboroschools.apptegy.net/
scraper> run youtube_meetings --channel=@attleboroschools
```

### `download [all|<source>|<url>]`

Download pending documents through the pipeline.

```
scraper> download all              # All pending documents
scraper> download apptegy          # All pending from apptegy source
scraper> download https://...      # Single document by URL
```

### `upload <source_url>`

Upload a downloaded document to FTP. Requires `PDF_FTP_PASS` environment variable.

```
scraper> upload https://files-backend.assets.thrillshare.com/abc123/doc.pdf
```

### `docs [source|district]`

Browse scraped documents. Without arguments shows summary stats.

```
scraper> docs                      # Summary stats
scraper> docs apptegy              # Documents from apptegy source
scraper> docs 00160000             # Documents for district code
```

### `sources`

List known source systems and their document counts.

```
scraper> sources
```

### `strategies [platform]`

Browse learned scraping strategies. Filter by platform.

```
scraper> strategies                # All strategies
scraper> strategies apptegy        # Apptegy-specific strategies
```

### `strategy-stats`

Show strategy store statistics (total patterns, success/fail counts by platform).

```
scraper> strategy-stats
```

### `db`

Show document database statistics.

```
scraper> db
```

### `add`

Manually add a document record. Interactive prompts for title, URL, classification.

```
scraper> add
  Title: Attleboro School Committee Agenda 2024-06-15
  Source URL: https://...
  Document class: (pick from list)
  Media type: (pick from list)
  Source system: (pick from list)
  District code (or blank):
```

### `ensure-db`

Create or migrate the documents table. Safe to run multiple times.

```
scraper> ensure-db
```

### `help` / `?`

Show all commands.

### `quit` / `exit` / Ctrl+D

Exit the terminal.

## Environment

| Variable | Purpose |
|---|---|
| `PDF_FTP_PASS` | FTP password for uploads |
| `PDF_FTP_HOST` | FTP host (default: ftp.parentdataforce.com) |
| `PDF_FTP_USER` | FTP username (default: cline@parentdataforce.com) |
