"""
Document database operations — CRUD for the documents table.
Works with both SQLite (dev) and MariaDB (production).
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from .base import ScrapedDocument


class DocumentDB:
    """Thin wrapper around the documents table."""

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = Path(__file__).parent.parent.parent / "backend" / "dev.db"
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    # -- Schema -------------------------------------------------------

    def ensure_table(self):
        """Create documents table if it doesn't exist."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS documents (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                title           TEXT    NOT NULL,
                source_url      TEXT    NOT NULL UNIQUE,
                checksum        TEXT,
                media_type      TEXT    NOT NULL,
                file_type       TEXT,
                file_extension  TEXT,
                document_class  TEXT    NOT NULL,
                source_system   TEXT    NOT NULL,
                source_label    TEXT,
                district_code   TEXT,
                meeting_date    TEXT,
                file_path       TEXT,
                file_size       INTEGER,
                page_count      INTEGER,
                ftp_path        TEXT,
                ftp_uploaded_at TEXT,
                status          TEXT    NOT NULL DEFAULT 'discovered',
                scrape_date     TEXT    NOT NULL,
                last_checked    TEXT,
                error_message   TEXT,
                scrape_method   TEXT,
                scrape_notes    TEXT,
                created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
                updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_docs_media_type ON documents(media_type);
            CREATE INDEX IF NOT EXISTS idx_docs_doc_class ON documents(document_class);
            CREATE INDEX IF NOT EXISTS idx_docs_source_sys ON documents(source_system);
            CREATE INDEX IF NOT EXISTS idx_docs_district   ON documents(district_code);
            CREATE INDEX IF NOT EXISTS idx_docs_status     ON documents(status);
            CREATE INDEX IF NOT EXISTS idx_docs_scrape_date ON documents(scrape_date);
            CREATE INDEX IF NOT EXISTS idx_docs_checksum   ON documents(checksum);
        """)
        self.conn.commit()

    # -- CRUD ---------------------------------------------------------

    def exists(self, source_url: str) -> bool:
        """Check if a document with this URL already exists."""
        row = self.conn.execute(
            "SELECT 1 FROM documents WHERE source_url = ?", (source_url,)
        ).fetchone()
        return row is not None

    def find_by_checksum(self, checksum: str) -> Optional[dict]:
        """Find a document by SHA-256 checksum (dedup)."""
        row = self.conn.execute(
            "SELECT * FROM documents WHERE checksum = ? AND status != 'failed'",
            (checksum,)
        ).fetchone()
        return dict(row) if row else None

    def insert(self, doc: ScrapedDocument) -> int:
        """Insert a new document. Returns row id."""
        row = doc.to_db_row()
        columns = ", ".join(row.keys())
        placeholders = ", ".join("?" for _ in row)
        values = tuple(row.values())

        cursor = self.conn.execute(
            f"INSERT OR IGNORE INTO documents ({columns}) VALUES ({placeholders})",
            values
        )
        self.conn.commit()
        return cursor.lastrowid

    def update_status(self, source_url: str, status: str, **kwargs):
        """Update document status and optional fields."""
        sets = ["status = ?", "updated_at = datetime('now')"]
        params = [status]

        for key, value in kwargs.items():
            sets.append(f"{key} = ?")
            params.append(str(value) if not isinstance(value, (int, float, type(None))) else value)

        params.append(source_url)
        self.conn.execute(
            f"UPDATE documents SET {', '.join(sets)} WHERE source_url = ?",
            params
        )
        self.conn.commit()

    def get_by_url(self, source_url: str) -> Optional[dict]:
        """Get a single document by URL."""
        row = self.conn.execute(
            "SELECT * FROM documents WHERE source_url = ?", (source_url,)
        ).fetchone()
        return dict(row) if row else None

    def list_by_source(self, source_system: str, limit: int = 50) -> list[dict]:
        """List documents from a source system."""
        rows = self.conn.execute(
            "SELECT * FROM documents WHERE source_system = ? ORDER BY scrape_date DESC LIMIT ?",
            (source_system, limit)
        ).fetchall()
        return [dict(r) for r in rows]

    def list_by_district(self, district_code: str, limit: int = 50) -> list[dict]:
        """List documents for a district."""
        rows = self.conn.execute(
            "SELECT * FROM documents WHERE district_code = ? ORDER BY scrape_date DESC LIMIT ?",
            (district_code, limit)
        ).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> dict:
        """Quick stats about the documents table."""
        total = self.conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        by_status = self.conn.execute(
            "SELECT status, COUNT(*) as n FROM documents GROUP BY status ORDER BY n DESC"
        ).fetchall()
        by_source = self.conn.execute(
            "SELECT source_system, COUNT(*) as n FROM documents GROUP BY source_system ORDER BY n DESC"
        ).fetchall()
        return {
            "total": total,
            "by_status": {r["status"]: r["n"] for r in by_status},
            "by_source": {r["source_system"]: r["n"] for r in by_source},
        }

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
