"""
Strategy Store — learned scraping patterns that accumulate over time.
Stored as YAML for human readability, queried by pattern type.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml


class StrategyStore:
    """Learned scraping strategies — what worked, what didn't.

    Strategies are patterns: URL structures, DOM selectors, navigation flows,
    API endpoints. Each has a success/fail count so the system can prefer
    proven approaches when encountering new pages.
    """

    def __init__(self, store_path: Optional[Path] = None):
        if store_path is None:
            store_path = Path(__file__).parent.parent / "strategies" / "patterns.yaml"
        self.store_path = store_path
        self._patterns: list[dict] = []
        self._load()

    def _load(self):
        if self.store_path.exists():
            with open(self.store_path, "r") as f:
                self._patterns = yaml.safe_load(f) or []

    def _save(self):
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.store_path, "w") as f:
            yaml.dump(self._patterns, f, default_flow_style=False, sort_keys=False)

    # -- Recording ------------------------------------------------------

    def record_success(self, strategy_name: str, platform_type: str,
                       pattern_type: str, pattern_value: str,
                       example_url: Optional[str] = None, notes: Optional[str] = None):
        """Record a pattern that worked."""
        existing = self._find(strategy_name, platform_type, pattern_type, pattern_value)
        if existing:
            existing["success_count"] = existing.get("success_count", 0) + 1
            existing["last_used"] = datetime.now().isoformat()
            existing["last_success"] = datetime.now().isoformat()
            if example_url:
                urls = existing.get("example_urls", [])
                if example_url not in urls:
                    urls.append(example_url)
                existing["example_urls"] = urls
        else:
            entry = {
                "strategy_name": strategy_name,
                "platform_type": platform_type,
                "pattern_type": pattern_type,
                "pattern_value": pattern_value,
                "success_count": 1,
                "fail_count": 0,
                "last_used": datetime.now().isoformat(),
                "last_success": datetime.now().isoformat(),
                "example_urls": [example_url] if example_url else [],
                "notes": notes or "",
                "is_active": True,
            }
            self._patterns.append(entry)
        self._save()

    def record_failure(self, strategy_name: str, platform_type: str,
                       pattern_type: str, pattern_value: str,
                       notes: Optional[str] = None):
        """Record a pattern that failed."""
        existing = self._find(strategy_name, platform_type, pattern_type, pattern_value)
        if existing:
            existing["fail_count"] = existing.get("fail_count", 0) + 1
            existing["last_used"] = datetime.now().isoformat()
        else:
            entry = {
                "strategy_name": strategy_name,
                "platform_type": platform_type,
                "pattern_type": pattern_type,
                "pattern_value": pattern_value,
                "success_count": 0,
                "fail_count": 1,
                "last_used": datetime.now().isoformat(),
                "last_success": None,
                "example_urls": [],
                "notes": notes or "Recorded from failure.",
                "is_active": True,
            }
            self._patterns.append(entry)
        self._save()

    # -- Querying -------------------------------------------------------

    def suggest(self, platform_type: str, pattern_type: Optional[str] = None) -> list[dict]:
        """Suggest strategies for a platform, sorted by success ratio."""
        candidates = []
        for p in self._patterns:
            if not p.get("is_active", True):
                continue
            if p["platform_type"] != platform_type:
                continue
            if pattern_type and p["pattern_type"] != pattern_type:
                continue
            # Only suggest proven strategies (at least one success)
            if p.get("success_count", 0) > 0:
                candidates.append(p)

        # Sort by success ratio (success / total attempts)
        candidates.sort(key=lambda p: (
            p.get("success_count", 0) / max(p.get("success_count", 0) + p.get("fail_count", 0), 1)
        ), reverse=True)
        return candidates

    def list_all(self) -> list[dict]:
        return sorted(self._patterns, key=lambda p: p.get("success_count", 0), reverse=True)

    def stats(self) -> dict:
        total = len(self._patterns)
        successes = sum(p.get("success_count", 0) for p in self._patterns)
        failures = sum(p.get("fail_count", 0) for p in self._patterns)
        by_platform = {}
        for p in self._patterns:
            pt = p["platform_type"]
            by_platform.setdefault(pt, {"success": 0, "fail": 0})
            by_platform[pt]["success"] += p.get("success_count", 0)
            by_platform[pt]["fail"] += p.get("fail_count", 0)
        return {
            "total_patterns": total,
            "total_successes": successes,
            "total_failures": failures,
            "by_platform": by_platform,
        }

    # -- Internals ------------------------------------------------------

    def _find(self, strategy_name: str, platform_type: str,
              pattern_type: str, pattern_value: str) -> Optional[dict]:
        for p in self._patterns:
            if (p.get("strategy_name") == strategy_name and
                p.get("platform_type") == platform_type and
                p.get("pattern_type") == pattern_type and
                p.get("pattern_value") == pattern_value):
                return p
        return None
