import time

from app.intelligence import detect_near_arbs
from scanner import _rotate_event_catalog


def q(sel, odds, book):
    return {
        "selection": sel,
        "odds": odds,
        "bookmaker": book,
        "observed_at": time.time(),
        "source_url": "https://example.test/e",
    }


def test_radar_fallback_returns_watch_market():
    market = {
        "event": "A - B",
        "sport": "Piłka nożna",
        "market": "U/O 2.5",
        "event_url": "https://example.test/e",
        "quotes": {
            "U 2.5": [q("U 2.5", 1.90, "Betclic")],
            "O 2.5": [q("O 2.5", 1.90, "STS")],
        },
        "source_names": ["DobryBuk"],
    }
    rows = detect_near_arbs(
        [market],
        {"Betclic": 1.0, "STS": 1.0},
        max_gap_pct=1.5,
        fallback_gap_pct=15.0,
        min_results=1,
    )
    assert rows
    assert rows[0]["radar_tier"] in {"near", "watch"}
    assert rows[0]["gap_pct"] > 0


def test_rotation_changes_catalog_order():
    events = [
        {"event": f"E{i}", "event_url": f"https://example.test/e{i}"}
        for i in range(10)
    ]
    first, off1 = _rotate_event_catalog(
        events, priority_urls=set(), sequence=1, batch_size=3
    )
    second, off2 = _rotate_event_catalog(
        events, priority_urls=set(), sequence=2, batch_size=3
    )
    assert off1 == 0
    assert off2 == 3
    assert first[0]["event"] != second[0]["event"]
