"""
YouTube Meeting Scraper — discovers and tracks school committee meeting
videos from district YouTube channels.

Strategy: District channels often have playlists organized by year.
This scraper discovers videos, extracts metadata (title, date, duration),
and records them as ScrapedDocument entries.

Does NOT download videos — too large. Instead:
  - Records video URL + metadata in documents table
  - Downloads subtitles/captions when available (via yt-dlp)
  - Links to YouTube for playback

Usage:
  python scrapers/youtube_meetings.py --channel @attleboroschools
  python scrapers/youtube_meetings.py --playlist https://youtube.com/playlist?list=...
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from scraper.core import (
    BaseScraper, ScrapeResult, ScrapedDocument,
    register_scraper, DocumentDB, StrategyStore,
)

# Known MA district YouTube channels
DISTRICT_CHANNELS = {
    "attleboro": "@attleboroschools",
}


@register_scraper
class YouTubeMeetingsScraper(BaseScraper):
    """Discover meeting videos from district YouTube channels."""

    name = "youtube_meetings"
    display_name = "YouTube Meeting Videos"
    source_system = "youtube"
    help_text = "Discover meeting videos from district YouTube channels"

    def run(self, channel: str = "", district: str = "",
            playlist_url: str = "", **kwargs) -> ScrapeResult:
        """Scrape YouTube for meeting videos.

        Args:
            channel: YouTube channel handle (e.g., @attleboroschools)
            district: District slug for channel lookup
            playlist_url: Direct playlist URL
        """
        result = ScrapeResult()
        result.started_at = datetime.now()
        strategy = StrategyStore()
        db = DocumentDB()
        db.ensure_table()

        # Resolve channel
        if not channel and district:
            channel = DISTRICT_CHANNELS.get(district.lower(), "")
        if not channel and not playlist_url:
            result.errors.append("No channel or playlist provided.")
            result.finished_at = datetime.now()
            return result

        try:
            if playlist_url:
                docs = self._scrape_playlist(playlist_url, district)
            else:
                docs = self._scrape_channel(channel, district)

            for doc in docs:
                result.documents.append(doc)
                if not db.exists(doc.source_url):
                    db.insert(doc)

            if docs:
                strategy.record_success(
                    "YouTube district channel",
                    "youtube", "url_pattern",
                    f"https://www.youtube.com/@{channel}/playlists" if channel else playlist_url,
                    example_url=f"https://www.youtube.com/@{channel}",
                )

        except Exception as e:
            result.errors.append(f"Failed: {e}")
            strategy.record_failure(
                "YouTube meeting scrape",
                "youtube", "url_pattern",
                channel or playlist_url,
                notes=str(e),
            )

        result.finished_at = datetime.now()
        return result

    def _scrape_channel(self, channel: str, district: str) -> list[ScrapedDocument]:
        """Scrape a channel's playlists and recent videos."""
        docs = []
        channel_url = f"https://www.youtube.com/@{channel}"

        # Try yt-dlp to get channel metadata
        try:
            proc = subprocess.run(
                ["yt-dlp", "--flat-playlist", "--dump-json",
                 "--playlist-end", "20", channel_url],
                capture_output=True, text=True, timeout=60,
            )
            if proc.returncode == 0:
                for line in proc.stdout.strip().split("\n"):
                    if not line:
                        continue
                    try:
                        video = json.loads(line)
                        docs.append(self._video_to_doc(video, district, channel))
                    except json.JSONDecodeError:
                        continue
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # yt-dlp not available — try scraping the page
            docs.extend(self._scrape_channel_html(channel, district))

        return docs

    def _scrape_playlist(self, url: str, district: str) -> list[ScrapedDocument]:
        """Scrape a specific playlist."""
        docs = []
        try:
            proc = subprocess.run(
                ["yt-dlp", "--flat-playlist", "--dump-json",
                 "--playlist-end", "50", url],
                capture_output=True, text=True, timeout=90,
            )
            if proc.returncode == 0:
                for line in proc.stdout.strip().split("\n"):
                    if not line:
                        continue
                    try:
                        video = json.loads(line)
                        docs.append(self._video_to_doc(video, district, ""))
                    except json.JSONDecodeError:
                        continue
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return docs

    def _scrape_channel_html(self, channel: str, district: str) -> list[ScrapedDocument]:
        """Fallback: scrape channel page HTML for video links."""
        docs = []
        url = f"https://www.youtube.com/@{channel}/videos"
        try:
            resp = self._get(url)
            html = resp.text

            # Extract video IDs from watch URLs
            video_ids = set(re.findall(r'watch\?v=([a-zA-Z0-9_-]{11})', html))

            for vid in video_ids:
                video_url = f"https://www.youtube.com/watch?v={vid}"
                doc = ScrapedDocument(
                    title=f"YouTube video: {vid}",
                    source_url=video_url,
                    media_type="video",
                    document_class="meeting_video",
                    source_system="youtube",
                    source_label=f"YouTube — {channel}",
                    district_code=district or None,
                    scrape_method="direct_download",
                    scrape_notes="Extracted from channel page HTML (yt-dlp unavailable)",
                )
                docs.append(doc)

        except Exception as e:
            pass

        return docs

    def _video_to_doc(self, video: dict, district: str,
                      channel: str) -> ScrapedDocument:
        """Convert yt-dlp video dict to ScrapedDocument."""
        video_id = video.get("id", "")
        title = video.get("title", f"YouTube video {video_id}")
        upload_date = video.get("upload_date", "")

        # Try to parse meeting date from title or upload date
        meeting_date = None
        if upload_date and len(upload_date) == 8:
            try:
                meeting_date = date(
                    int(upload_date[:4]),
                    int(upload_date[4:6]),
                    int(upload_date[6:8]),
                )
            except ValueError:
                pass

        # Classify based on title keywords
        title_lower = title.lower()
        if any(k in title_lower for k in ["school committee", "board meeting",
                                            "committee meeting"]):
            doc_class = "meeting_video"
        elif "budget" in title_lower:
            doc_class = "budget"
        elif "policy" in title_lower:
            doc_class = "policy_manual"
        else:
            doc_class = "other"

        return ScrapedDocument(
            title=title,
            source_url=f"https://www.youtube.com/watch?v={video_id}",
            media_type="video",
            file_type="video/mp4",
            document_class=doc_class,
            source_system="youtube",
            source_label=f"YouTube — {channel or 'playlist'}",
            district_code=district or None,
            meeting_date=meeting_date,
            scrape_method="api_call" if channel else "direct_download",
            scrape_notes=f"Duration: {video.get('duration', '?')}s",
        )


# -- Standalone run -------------------------------------------------------
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="YouTube Meeting Video Scraper")
    p.add_argument("--channel", help="YouTube channel handle (@handle)")
    p.add_argument("--district", help="District slug for known channels")
    p.add_argument("--playlist", help="Direct playlist URL")
    args = p.parse_args()
    YouTubeMeetingsScraper.cli_run(
        channel=args.channel or "",
        district=args.district or "",
        playlist_url=args.playlist or "",
    )
