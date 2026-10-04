import time
from pathlib import Path

from app.market_cache import MarketCache


def quote(book, odds, observed):
    return {
        "bookmaker": book,
        "selection": "1",
        "odds": odds,
        "observed_at": observed,
        "source_name": "DobryBuk",
    }


def row(odds, observed):
    return {
        "event": "A - B",
        "sport": "Piłka nożna",
        "market": "1X2",
        "event_url": "https://example.test/event",
        "observed_at": observed,
        "quotes": {"1": [quote("STS", odds, observed)]},
        "source_names": ["DobryBuk"],
    }


def test_newest_quote_wins_not_highest_old_quote(tmp_path: Path):
    cache = MarketCache(tmp_path / "cache.json")
    now = time.time()
    cache.update([row(3.0, now - 60)])
    cache.update([row(2.5, now)])
    rows = cache.snapshot(300)
    assert len(rows) == 1
    assert rows[0]["quotes"]["1"][0]["odds"] == 2.5


def test_display_cache_can_outlive_fresh_analysis_window(tmp_path: Path):
    cache = MarketCache(tmp_path / "cache.json")
    now = time.time()
    cache.update([row(2.5, now - 600)])
    assert cache.snapshot(300) == []
    assert len(cache.snapshot(1800)) == 1


def test_cache_persists(tmp_path: Path):
    path = tmp_path / "cache.json"
    cache = MarketCache(path)
    cache.update([row(2.2, time.time())])
    cache.save()
    loaded = MarketCache(path)
    assert len(loaded.snapshot(300)) == 1
