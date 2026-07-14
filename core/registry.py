"""
Scraper Registry — discovers, validates, and runs scrapers.
Plug a new scraper file into scrapers/ and it auto-registers.
"""
from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path
from typing import Optional

from .scraper import BaseScraper, ScrapeResult


class ScraperRegistry:
    """Holds all registered scrapers. Singleton per process."""

    _instance: Optional["ScraperRegistry"] = None

    def __init__(self):
        self._scrapers: dict[str, type[BaseScraper]] = {}

    @classmethod
    def get(cls) -> "ScraperRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # -- Registration --------------------------------------------------

    def register(self, scraper_cls: type[BaseScraper]):
        """Register a scraper class."""
        if not issubclass(scraper_cls, BaseScraper):
            raise TypeError(f"{scraper_cls} must inherit from BaseScraper")
        if scraper_cls is BaseScraper:
            return  # skip the base class itself

        instance = scraper_cls.__new__(scraper_cls)  # peek at class attrs without __init__
        name = getattr(scraper_cls, "name", scraper_cls.__name__)

        if name in self._scrapers:
            existing = self._scrapers[name]
            print(f"[registry] Warning: '{name}' already registered by {existing.__name__}, "
                  f"overwriting with {scraper_cls.__name__}")

        self._scrapers[name] = scraper_cls

    def discover(self, scrapers_dir: Optional[Path] = None):
        """Import all .py files in the scrapers directory to trigger registration."""
        if scrapers_dir is None:
            scrapers_dir = Path(__file__).parent.parent / "scrapers"

        if not scrapers_dir.exists():
            return

        sys.path.insert(0, str(scrapers_dir.parent))

        for py_file in sorted(scrapers_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            module_name = py_file.stem
            try:
                importlib.import_module(f"scrapers.{module_name}")
            except Exception as e:
                print(f"[registry] Error loading {module_name}: {e}")

    # -- Queries -------------------------------------------------------

    def list_all(self) -> list[type[BaseScraper]]:
        """Return all registered scraper classes sorted by name."""
        return sorted(self._scrapers.values(), key=lambda c: getattr(c, "name", ""))

    def get_scraper(self, name: str) -> Optional[type[BaseScraper]]:
        """Get a scraper by name."""
        return self._scrapers.get(name)

    def list_by_source(self, source_system: str) -> list[type[BaseScraper]]:
        """Get all scrapers for a given source system."""
        return [s for s in self.list_all()
                if getattr(s, "source_system", "") == source_system]

    def list_names(self) -> list[str]:
        return sorted(self._scrapers.keys())

    # -- Execution -----------------------------------------------------

    def run(self, name: str, **kwargs) -> Optional[ScrapeResult]:
        """Run a scraper by name and return its result."""
        scraper_cls = self._scrapers.get(name)
        if scraper_cls is None:
            print(f"[registry] No scraper named '{name}'. Available: {self.list_names()}")
            return None

        # Separate scraper init kwargs from run kwargs
        init_kwargs = {k: v for k, v in kwargs.items()
                       if k in ("download_dir", "rate_limit")}
        run_kwargs = {k: v for k, v in kwargs.items()
                      if k not in ("download_dir", "rate_limit")}

        instance = scraper_cls(**init_kwargs)
        return instance.run(**run_kwargs)


# -- Auto-registration decorator --------------------------------------------

def register_scraper(cls):
    """Decorator: auto-registers a scraper class on import."""
    ScraperRegistry.get().register(cls)
    return cls
