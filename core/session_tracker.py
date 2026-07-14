"""
Scrape session tracking — records each scraper run with timing, stats,
and links to discovered documents. Builds a reportable history for
monitoring scraper health and data freshness.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional


class SessionTracker:
    """Records scraper runs in a scrape_sessions table."""

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
        return self._conn

    def ensure_table(self):
        """Create scrape_sessions table if it doesn't exist."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS scrape_sessions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                scraper_name    TEXT    NOT NULL,
                source_system   TEXT    NOT NULL,
                started_at      TEXT    NOT NULL,
                finished_at     TEXT,
                elapsed_seconds REAL,
                documents_found INTEGER DEFAULT 0,
                documents_new   INTEGER DEFAULT 0,
                documents_down  INTEGER DEFAULT 0,
                documents_fail  INTEGER DEFAULT 0,
                bytes_total     INTEGER DEFAULT 0,
                errors          TEXT,
                status          TEXT    NOT NULL DEFAULT 'running',
                notes           TEXT,
                created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_scrape_sessions_name
                ON scrape_sessions(scraper_name);
            CREATE INDEX IF NOT EXISTS idx_scrape_sessions_started
                ON scrape_sessions(started_at);
        """)
        self.conn.commit()

    def start_session(self, scraper_name: str, source_system: str,
                      notes: str = "") -> int:
        """Begin a new scrape session. Returns session ID."""
        self.ensure_table()
        cursor = self.conn.execute(
            """INSERT INTO scrape_sessions
               (scraper_name, source_system, started_at, status, notes)
               VALUES (?, ?, ?, 'running', ?)""",
            (scraper_name, source_system, datetime.now().isoformat(), notes),
        )
        self.conn.commit()
        return cursor.lastrowid

    def finish_session(self, session_id: int, result, status: str = "completed"):
        """Record session completion with results."""
        errors_json = json.dumps(result.errors) if hasattr(result, "errors") and result.errors else None

        elapsed = 0.0
        if hasattr(result, "started_at") and hasattr(result, "finished_at"):
            if result.started_at and result.finished_at:
                elapsed = (result.finished_at - result.started_at).total_seconds()

        docs = getattr(result, "documents", [])
        docs_new = sum(1 for d in docs if d.status not in ("skipped_duplicate",))
        docs_down = sum(1 for d in docs if d.status == "downloaded")
        docs_fail = sum(1 for d in docs if d.status == "failed")
        stats = getattr(result, "stats", {})
        bytes_total = stats.get("bytes", 0)

        self.conn.execute(
            """UPDATE scrape_sessions SET
               finished_at = ?, elapsed_seconds = ?,
               documents_found = ?, documents_new = ?,
               documents_down = ?, documents_fail = ?,
               bytes_total = ?, errors = ?, status = ?
               WHERE id = ?""",
            (
                datetime.now().isoformat(), elapsed,
                len(docs), docs_new, docs_down, docs_fail,
                bytes_total, errors_json, status, session_id,
            ),
        )
        self.conn.commit()

    def recent_sessions(self, limit: int = 10) -> list[dict]:
        """Get recent scrape sessions."""
        self.ensure_table()
        rows = self.conn.execute(
            "SELECT * FROM scrape_sessions ORDER BY started_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> dict:
        """Aggregate stats across all sessions."""
        self.ensure_table()
        total = self.conn.execute(
            "SELECT COUNT(*) FROM scrape_sessions"
        ).fetchone()[0]
        by_scraper = self.conn.execute(
            """SELECT scraper_name, COUNT(*) as runs,
                      SUM(documents_found) as docs,
                      SUM(documents_down) as downloaded,
                      SUM(bytes_total) as bytes
               FROM scrape_sessions WHERE status = 'completed'
               GROUP BY scraper_name ORDER BY runs DESC"""
        ).fetchall()
        last_run = self.conn.execute(
            "SELECT scraper_name, MAX(started_at) as last_run, status "
            "FROM scrape_sessions GROUP BY scraper_name"
        ).fetchall()

        return {
            "total_sessions": total,
            "by_scraper": [dict(r) for r in by_scraper],
            "last_runs": [dict(r) for r in last_run],
        }

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None


# -- Integration with BaseScraper ----------------------------------------

def track_session(scraper_name: str, source_system: str):
    """Context manager/decorator helper for tracking scrape sessions.

    Usage:
        tracker = SessionTracker()
        session_id = tracker.start_session("dese_all", "dese")
        try:
            result = scraper.run()
            tracker.finish_session(session_id, result)
        except Exception as e:
            tracker.finish_session(session_id, result, status="failed")
    """
    return SessionTracker()
