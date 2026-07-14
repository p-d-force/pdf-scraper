# Database Schema

The scraping system uses three tables for document tracking, source registration, and strategy accumulation.

## documents

Primary table for every discovered, downloaded, and uploaded document.

| Column | Type | Description |
|---|---|---|
| `id` | INT PK | Auto-increment |
| `title` | VARCHAR(512) | Document title |
| `source_url` | VARCHAR(2048) UNIQUE | Original URL |
| `checksum` | VARCHAR(64) | SHA-256 for dedup |
| `media_type` | VARCHAR(50) | PDF, HTML, video, image, spreadsheet, text, archive, audio, other |
| `file_type` | VARCHAR(100) | MIME type (application/pdf, text/html, etc.) |
| `file_extension` | VARCHAR(20) | pdf, html, mp4, etc. |
| `document_class` | VARCHAR(100) | meeting_agenda, meeting_minutes, policy_manual, budget, etc. |
| `source_system` | VARCHAR(50) | dese, apptegy, civicengage, boarddocs, youtube, custom_html, manual |
| `source_label` | VARCHAR(255) | Human-readable source description |
| `district_code` | VARCHAR(10) FK | DESE 8-digit district code |
| `meeting_date` | DATE | Meeting date if applicable |
| `file_path` | VARCHAR(1024) | Local path after download |
| `file_size` | BIGINT | Bytes |
| `page_count` | INT | PDF pages (optional) |
| `ftp_path` | VARCHAR(1024) | FTP server path after upload |
| `ftp_uploaded_at` | DATETIME | Upload timestamp |
| `status` | VARCHAR(30) | discovered, downloaded, verified, uploaded, failed, skipped_duplicate |
| `scrape_date` | DATE | Date discovered/scraped |
| `last_checked` | DATETIME | Last URL verification |
| `error_message` | TEXT | Failure details |
| `scrape_method` | VARCHAR(100) | direct_download, selenium_click, api_call, manual |
| `scrape_notes` | TEXT | Strategy notes |
| `created_at` | DATETIME | Auto |
| `updated_at` | DATETIME | Auto |

## source_systems

Registry of known scraping targets.

| Column | Type | Description |
|---|---|---|
| `id` | INT PK | Auto-increment |
| `system_name` | VARCHAR(50) UNIQUE | dese, apptegy, civicengage, etc. |
| `display_name` | VARCHAR(255) | Human-readable |
| `base_url` | VARCHAR(1024) | Starting URL |
| `platform_type` | VARCHAR(50) | government_portal, meeting_platform, cms, cdn, bulk_export, video_platform, manual |
| `auth_required` | TINYINT | 0 or 1 |
| `rate_limit` | VARCHAR(50) | e.g. "2 req/sec" |
| `scraper_module` | VARCHAR(255) | Python module path |
| `is_active` | TINYINT | 0 or 1 |
| `last_scraped` | DATETIME | Last run timestamp |
| `notes` | TEXT | Platform notes |

## scrape_strategies

Learned pattern knowledge base.

| Column | Type | Description |
|---|---|---|
| `id` | INT PK | Auto-increment |
| `strategy_name` | VARCHAR(255) | Unique name |
| `platform_type` | VARCHAR(50) | Platform category |
| `pattern_type` | VARCHAR(50) | url_pattern, dom_selector, api_endpoint, navigation_flow, auth_method |
| `pattern_value` | TEXT | The actual pattern/selector/URL template |
| `success_count` | INT | Times this pattern worked |
| `fail_count` | INT | Times it failed |
| `last_used` | DATETIME | Last attempt |
| `last_success` | DATETIME | Last success |
| `example_urls` | TEXT | JSON array of URLs |
| `notes` | TEXT | Strategy description |
| `is_active` | TINYINT | 0 or 1 |

## Migration

Apply to MariaDB production:

```bash
mysql -u pdf_user -p pdf_db < migration/documents_table.sql
```

Apply to SQLite dev:

```bash
python -m scraper.cli
scraper> ensure-db
```
