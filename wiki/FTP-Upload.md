# FTP Upload

The FTP upload pipeline sends verified documents to the production server with automatic directory organization.

## Setup

```bash
export PDF_FTP_PASS="your_password"
# Optional overrides:
export PDF_FTP_HOST="ftp.parentdataforce.com"
export PDF_FTP_USER="cline@parentdataforce.com"
```

## Directory Structure

Documents are organized automatically:

```
/public_html/documents/
├── 00160000/           # District code
│   └── 2026/           # Year
│       ├── meeting_agendas/
│       │   └── 2026-06-15_agenda.pdf
│       ├── meeting_minutes/
│       └── policies/
├── 00350000/           # Another district
│   └── 2025/
│       └── budgets/
```

The structure is determined by the document's `district_code`, `scrape_date` (year), and `document_class`.

## Usage

### From CLI

```bash
python -m scraper.cli
scraper> upload https://files-backend.assets.thrillshare.com/abc123/doc.pdf
```

The CLI looks up the document by source URL, confirms it's downloaded, and uploads it with auto directory structure.

### From Code

```python
from scraper.core import FTPUploader
from pathlib import Path

ftp = FTPUploader(
    host="ftp.parentdataforce.com",
    user="cline@parentdataforce.com",
    password=os.environ["PDF_FTP_PASS"],
    remote_root="/public_html/documents",
)

ftp.connect()

# Upload with auto directory
remote_path = ftp.upload_document(
    Path("local/meeting_agenda.pdf"),
    district_code="00160000",
    doc_class="meeting_agenda",
    scrape_date="2026-07-14",
)
# → /public_html/documents/00160000/2026/meeting_agendas/meeting_agenda.pdf

# Upload with manual path
remote_path = ftp.upload(
    Path("local/file.pdf"),
    remote_subdir="custom/path",
    remote_filename="custom_name.pdf",
)

# Verify upload
if ftp.verify(remote_path):
    print("Upload confirmed")

ftp.disconnect()
```

## Lifecycle Integration

After upload, the document's status is updated:

```
verified → uploaded
```

And the `ftp_path` and `ftp_uploaded_at` columns are populated. The document can then be linked from the website's data portal.

## Error Handling

- **Not configured:** `RuntimeError` if `PDF_FTP_PASS` is not set
- **File not found:** `FileNotFoundError` if local file is missing
- **Upload failure:** Status set to `failed` with error message in DB
- **Connection issues:** Automatic disconnect in `finally` block
