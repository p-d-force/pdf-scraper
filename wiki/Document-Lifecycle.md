# Document Lifecycle

Every document flows through five states with checksum-based deduplication.

## States

```
 ┌──────────┐
 │discovered│  ← Scraper finds a URL and classifies it
 └────┬─────┘
      │
 ┌────┴─────┐
 │downloaded│  ← ScraperPipeline downloads the file
 └────┬─────┘      + SHA-256 checksum computed
      │            + Actual media type detected from headers
 ┌────┴─────┐
 │ verified │  ← File opens correctly, PDF header valid
 └────┬─────┘      + Optional: PDF page count, image verification
      │
 ┌────┴─────┐
 │ uploaded │  ← FTPUploader sends to production
 └──────────┘      + Auto directory structure

Failure paths:
  discovered ──→ failed          (download error)
  downloaded ──→ failed          (verification error)
  discovered ──→ skipped_duplicate (checksum match in DB)
```

## Pipeline Methods

### `process(doc, subdir)`

Processes a single `ScrapedDocument` through the full pipeline:

1. Checks if already in DB with `downloaded`/`verified`/`uploaded` status → skip
2. Skips HTML documents (no binary to download)
3. Generates safe filename from metadata
4. Downloads with rate limiting and stream writing
5. Detects actual media type from `Content-Type` header
6. Verifies file integrity (PDF header, image verification via PIL)
7. Computes SHA-256 checksum
8. Dedup check: `find_by_checksum()` → skip if match
9. Inserts or updates documents table
10. Records success/failure in StrategyStore

### `process_batch(documents, subdir)`

Processes multiple documents sequentially with progress output.

## Deduplication

Documents are deduplicated by SHA-256 checksum, not URL. This means:

- Same PDF at two different CDN URLs → one document
- Re-scraping the same page → documents marked `skipped_duplicate`
- Corrupted download (wrong checksum) → retried next run

## Classification

Documents are classified by three dimensions on discovery:

| Dimension | Source |
|---|---|
| `media_type` | URL extension, then Content-Type header after download |
| `document_class` | URL path keywords (agenda, minutes, budget, policy, etc.) |
| `source_system` | Set by the scraper (`dese`, `apptegy`, `civicengage`, etc.) |

## Verification

- **PDF:** Reads first 5 bytes, verifies `%PDF-` header
- **Images (png/jpg/gif/webp):** Opens with PIL, calls `verify()`
- **Other:** Passes through without verification
- **Empty files (0 bytes):** Marked `failed`
