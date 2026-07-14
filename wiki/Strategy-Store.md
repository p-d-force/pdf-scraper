# Strategy Store

The Strategy Store learns from every scraping operation — successes and failures. Over time, it builds a knowledge base of proven patterns that can be queried before writing new scrapers.

## How It Works

1. **Scrapers record results:** After each run, scrapers call `record_success()` or `record_failure()` with the strategy name, platform type, pattern type, and pattern value.
2. **Patterns accumulate:** Each unique strategy tracks success/fail counts, last used date, and example URLs.
3. **Query before scraping:** When encountering a new page, query `suggest(platform_type)` to get proven patterns sorted by success ratio.

## Storage

Two storage backends:

1. **YAML file** (`strategies/patterns.yaml`) — human-readable, version-controlled. The primary store. Loaded on startup, saved on each update.
2. **SQL table** (`scrape_strategies`) — database-backed. Used for production queries and reporting.

## Current Patterns (Seed)

| Strategy | Platform | Type | Success | Fail |
|---|---|---|---|---|
| Apptegy CDN direct PDF download | apptegy | url_pattern | 5 | 0 |
| Apptegy subdomain detection | apptegy | url_pattern | 8 | 1 |
| CivicEngage JS year navigation | civicengage | navigation_flow | 3 | 0 |
| CivicEngage PDF link pattern | civicengage | dom_selector | 3 | 0 |
| DESE Socrata API | government_portal | api_endpoint | 2 | 0 |
| DESE Profiles HTML table | government_portal | dom_selector | 4 | 1 |
| YouTube district channel | video_platform | url_pattern | 2 | 0 |
| BoardDocs meeting portal | boarddocs | url_pattern | 0 | 1 |

## Querying

```python
from scraper.core import StrategyStore

store = StrategyStore()

# Get proven patterns for a platform
suggestions = store.suggest("apptegy")
# → sorted by success ratio (most proven first)

# Filter by pattern type
url_patterns = store.suggest("civicengage", pattern_type="url_pattern")

# Get all strategies
all_patterns = store.list_all()

# Stats
stats = store.stats()
# → total_patterns, total_successes, total_failures, by_platform
```

## Pattern Types

| Type | Description | Example |
|---|---|---|
| `url_pattern` | URL structure that identifies the platform | `*.apptegy.net` |
| `dom_selector` | CSS selector or XPath for extracting content | `a[href$='.pdf']` |
| `api_endpoint` | REST API endpoint pattern | `educationdata.mass.gov/resource/{id}` |
| `navigation_flow` | Multi-step navigation (JS calls, redirects) | `changeYear()` on CivicEngage |
| `auth_method` | Authentication approach | OAuth, API key, session cookie |

## Recording

```python
store = StrategyStore()

# Record a success
store.record_success(
    strategy_name="Apptegy CDN PDF download",
    platform_type="apptegy",
    pattern_type="url_pattern",
    pattern_value="https://files-backend.assets.thrillshare.com/{uuid}",
    example_url="https://attleboroschools.apptegy.net/",
    notes="Found 12 PDFs via UUID pattern matching in page source",
)

# Record a failure
store.record_failure(
    strategy_name="BoardDocs SPA scraping",
    platform_type="boarddocs",
    pattern_type="navigation_flow",
    pattern_value="go.boarddocs.com SPA",
    notes="Requires Playwright — static HTML parsing insufficient",
)
```

## Using Strategies in Scrapers

```python
def run(self, url: str = "", **kwargs) -> ScrapeResult:
    store = StrategyStore()
    
    # Check for proven patterns before attempting
    suggestions = store.suggest(self.source_system)
    if suggestions:
        best = suggestions[0]
        print(f"Using proven pattern: {best['strategy_name']} "
              f"({best['success_count']}/{best['success_count'] + best['fail_count']})")
    
    # ... scraping logic ...
    
    # Record result
    if success:
        store.record_success("My scraper pattern", ...)
    else:
        store.record_failure("My scraper pattern", ...)
```
