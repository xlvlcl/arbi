import time
from pathlib import Path

from app.intelligence import detect_near_arbs
from app.merge import merge_markets
from app.state import State


def q(selection, odds, book):
    return {
        "selection": selection,
        "odds": odds,
        "bookmaker": book,
        "observed_at": time.time(),
        "source_url": "https://example.test/event",
        "bookmaker_url": "https://example.test/book",
    }


def test_near_arb_detected_but_not_real_arb():
    market = {
        "event": "A - B",
        "sport": "Piłka nożna",
        "market": "U/O 2.5",
        "event_url": "https://example.test/event",
        "quotes": {
            "U 2.5": [q("U 2.5", 1.99, "Betclic")],
            "O 2.5": [q("O 2.5", 1.99, "Fortuna")],
        },
        "source_names": ["x"],
    }
    rows = detect_near_arbs(
        [market],
        {"Betclic": 1.0, "Fortuna": 1.0},
        max_gap_pct=1.5,
    )
    assert rows
    assert 0 < rows[0]["gap_pct"] < 1.5


def test_state_scan_plan_cycles(tmp_path: Path):
    state = State(tmp_path / "state.json")
    modes = [state.next_scan_plan(4)["mode"] for _ in range(5)]
    assert modes == ["deep", "fast", "fast", "deep", "fast"]


def test_value_stability_requires_two_scans(tmp_path: Path):
    state = State(tmp_path / "state.json")
    state.next_scan_plan(4)
    value = {
        "key": "v1",
        "event": "A-B",
        "market": "U/O 2.5",
        "selection": "O 2.5",
        "bookmaker": "Betclic",
        "edge_pct": 6.0,
        "reference_books": 6,
        "dispersion_pct": 3.0,
        "event_url": "https://example.test/e",
    }
    first = state.decorate_values([value], required_scans=2, elite_edge_pct=9.0)
    assert first[0]["push_ready"] is False
    state.next_scan_plan(4)
    second = state.decorate_values([value], required_scans=2, elite_edge_pct=9.0)
    assert second[0]["push_ready"] is True
    assert second[0]["stability_scans"] == 2


def test_drawless_winner_merges_with_1x2():
    now = time.time()
    a = {
        "event": "Player A - Player B",
        "sport": "Tenis",
        "market": "1X2",
        "quotes": {"1": [q("1", 1.8, "STS")], "2": [q("2", 2.0, "STS")]},
        "event_url": "https://example.test/a",
        "observed_at": now,
        "source_name": "DobryBuk",
    }
    b = {
        "event": "Player A - Player B",
        "sport": "Tenis",
        "market": "Winner",
        "quotes": {"1": [q("1", 1.85, "Betclic")], "2": [q("2", 2.05, "Betclic")]},
        "event_url": "https://example.test/b",
        "observed_at": now,
        "source_name": "Betclic direct",
    }
    merged = merge_markets([a, b])
    assert len(merged) == 1
    assert len(merged[0]["quotes"]["1"]) == 2
