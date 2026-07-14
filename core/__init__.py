"""
Scraper Core — shared infrastructure for the consolidated scraping system.
"""
from .base import ScrapedDocument, MEDIA_TYPES, DOCUMENT_CLASSES, SOURCE_SYSTEMS
from .scraper import BaseScraper, ScrapeResult
from .registry import ScraperRegistry, register_scraper
from .db import DocumentDB
from .ftp import FTPUploader
from .strategy import StrategyStore
from .pipeline import ScraperPipeline
