import time

from app.valuebets import detect_valuebets


def market_two_way(target_odds=2.30, target_book="Betclic", refs=6):
    now = time.time()
    books = ["Betclic", "Fortuna", "STS", "Superbet", "Betfan", "LVBet", "ETOTO"][: refs + 1]
    quotes = {"U 2.5": [], "O 2.5": []}
    for i, book in enumerate(books):
        u = target_odds if book == target_book else 2.00 + (i % 2) * 0.02
        o = 1.90 + (i % 3) * 0.02
        quotes["U 2.5"].append(
            {
                "selection": "U 2.5",
                "odds": u,
                "bookmaker": book,
                "observed_at": now,
                "source_url": "https://example.test/e",
                "bookmaker_url": "https://example.test/book",
            }
        )
        quotes["O 2.5"].append(
            {
                "selection": "O 2.5",
                "odds": o,
                "bookmaker": book,
                "observed_at": now,
                "source_url": "https://example.test/e",
                "bookmaker_url": "https://example.test/book",
            }
        )
    return {
        "event": "A - B",
        "sport": "Piłka nożna",
        "market": "U/O 2.5",
        "quotes": quotes,
        "event_url": "https://example.test/e",
    }


def test_strong_consensus_value_is_detected():
    values = detect_valuebets(
        [market_two_way()],
        {"Betclic": 1.0, "Fortuna": 1.0, "STS": 1.0, "Superbet": 1.0, "Betfan": 1.0, "LVBet": 1.0, "ETOTO": 1.0},
        min_edge_pct=5.0,
        min_reference_books=5,
        max_dispersion=0.08,
        max_price_gap=0.30,
    )
    assert values
    assert values[0]["bookmaker"] == "Betclic"
    assert values[0]["edge_pct"] >= 5.0
    assert values[0]["confidence"] == "high"


def test_tax_factor_can_remove_fake_value():
    values = detect_valuebets(
        [market_two_way(target_odds=2.18, target_book="STS")],
        {"Betclic": 1.0, "Fortuna": 1.0, "STS": 0.88, "Superbet": 1.0, "Betfan": 1.0, "LVBet": 1.0, "ETOTO": 1.0},
        min_edge_pct=5.0,
        min_reference_books=5,
        max_dispersion=0.08,
        max_price_gap=0.30,
    )
    assert not any(v["bookmaker"] == "STS" for v in values)


def test_not_enough_reference_books_is_rejected():
    values = detect_valuebets(
        [market_two_way(refs=3)],
        {"Betclic": 1.0, "Fortuna": 1.0, "STS": 1.0, "Superbet": 1.0},
        min_edge_pct=5.0,
        min_reference_books=5,
    )
    assert values == []
