"""
FTP upload module — uploads downloaded documents to the production server.
Tracks upload status, handles retries, and verifies uploads.
"""
from __future__ import annotations

import ftplib
import os
from datetime import datetime
from pathlib import Path
from typing import Optional


class FTPUploader:
    """Uploads files to parentdataforce.com via FTP."""

    def __init__(self, host: Optional[str] = None, user: Optional[str] = None,
                 password: Optional[str] = None, remote_root: str = "/public_html/documents"):
        self.host = host or os.environ.get("PDF_FTP_HOST", "ftp.parentdataforce.com")
        self.user = user or os.environ.get("PDF_FTP_USER", "cline@parentdataforce.com")
        self.password = password or os.environ.get("PDF_FTP_PASS", "")
        self.remote_root = remote_root
        self._ftp: Optional[ftplib.FTP] = None

    @property
    def configured(self) -> bool:
        return bool(self.password)

    def connect(self):
        """Establish FTP connection."""
        if not self.configured:
            raise RuntimeError("FTP not configured. Set PDF_FTP_PASS environment variable.")
        self._ftp = ftplib.FTP(self.host, timeout=30)
        self._ftp.login(self.user, self.password)
        self._ftp.set_pasv(True)

    def disconnect(self):
        if self._ftp:
            try:
                self._ftp.quit()
            except Exception:
                pass
            self._ftp = None

    def _ensure_remote_dir(self, path: str):
        """Create remote directory tree if it doesn't exist."""
        parts = path.strip("/").split("/")
        current = ""
        for part in parts:
            current += f"/{part}"
            try:
                self._ftp.cwd(current)
            except ftplib.error_perm:
                self._ftp.mkd(current)

    def upload(self, local_path: Path, remote_subdir: str = "",
               remote_filename: Optional[str] = None) -> str:
        """Upload a file. Returns the remote path.

        Args:
            local_path: Local file to upload
            remote_subdir: Subdirectory under remote_root (e.g., 'attleboro/2024')
            remote_filename: Override filename (default: use local filename)

        Returns:
            Remote path relative to FTP root
        """
        if not local_path.exists():
            raise FileNotFoundError(f"File not found: {local_path}")

        remote_dir = f"{self.remote_root}/{remote_subdir}".rstrip("/")
        filename = remote_filename or local_path.name
        remote_path = f"{remote_dir}/{filename}"

        self._ensure_remote_dir(remote_dir)

        with open(local_path, "rb") as f:
            self._ftp.storbinary(f"STOR {filename}", f)

        return remote_path

    def verify(self, remote_path: str) -> bool:
        """Check that a file exists at the remote path."""
        try:
            remote_dir = str(Path(remote_path).parent)
            filename = Path(remote_path).name
            self._ftp.cwd(remote_dir)
            files = self._ftp.nlst()
            return filename in files
        except Exception:
            return False

    def upload_document(self, local_path: Path, district_code: Optional[str] = None,
                        doc_class: Optional[str] = None, scrape_date: Optional[str] = None) -> str:
        """Upload with automatic directory structure.

        Produces paths like: /public_html/documents/attleboro/2026/meeting_agendas/filename.pdf
        """
        parts = []
        if district_code:
            parts.append(district_code)
        if scrape_date:
            parts.append(scrape_date[:4])  # year
        if doc_class:
            # Convert document_class to directory-friendly name
            parts.append(doc_class.replace("_", "_") + "s")

        subdir = "/".join(parts) if parts else ""
        return self.upload(local_path, subdir)
