import time

from app.providers.external_feeds import (
    parse_arbiscan_events,
    parse_odds_api_io_events,
)


def test_parse_arbiscan_h2h_merges_polish_books():
    now_iso = "2026-10-07T20:00:00Z"
    payload = [
        {
            "id": "evt-1",
            "sport": "Football",
            "home_team": "Alpha",
            "away_team": "Beta",
            "bookmakers": [
                {
                    "key": "Betclic",
                    "last_update": now_iso,
                    "markets": [
                        {
                            "key": "h2h",
                            "last_update": now_iso,
                            "outcomes": [
                                {"name": "Home", "price": 2.2, "last_update": now_iso},
                                {"name": "Draw", "price": 3.3, "last_update": now_iso},
                                {"name": "Away", "price": 3.6, "last_update": now_iso},
                            ],
                        }
                    ],
                },
                {
                    "key": "Fortuna",
                    "last_update": now_iso,
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": "Home", "price": 2.1, "last_update": now_iso},
                                {"name": "Draw", "price": 3.5, "last_update": now_iso},
                                {"name": "Away", "price": 3.8, "last_update": now_iso},
                            ],
                        }
                    ],
                },
            ],
        }
    ]
    rows = parse_arbiscan_events(payload, fetched_at=time.time())
    assert len(rows) == 1
    row = rows[0]
    assert row["event"] == "Alpha vs Beta"
    assert row["market"] == "1X2"
    assert set(row["quotes"]) == {"1", "X", "2"}
    assert {q["bookmaker"] for q in row["quotes"]["2"]} == {"Betclic", "Fortuna"}
    assert all(q["source_name"] == "ArbiScan API" for q in row["quotes"]["1"])


def test_parse_arbiscan_total_keeps_line():
    payload = [
        {
            "id": "evt-2",
            "sport": "Football",
            "home_team": "A",
            "away_team": "B",
            "bookmakers": [
                {
                    "key": "STS",
                    "markets": [
                        {
                            "key": "Total|2.5",
                            "outcomes": [
                                {"name": "Over", "price": 1.95},
                                {"name": "Under", "price": 1.9},
                            ],
                        }
                    ],
                }
            ],
        }
    ]
    rows = parse_arbiscan_events(payload)
    assert rows[0]["market"] == "Total 2.5"
    assert set(rows[0]["quotes"]) == {"Over", "Under"}


def test_parse_odds_api_io_common_markets_and_canonical_books():
    payload = [
        {
            "id": 123,
            "home": "Home FC",
            "away": "Away FC",
            "sport": {"name": "Football", "slug": "football"},
            "urls": {
                "Betclic PL": "https://www.betclic.pl/example",
                "eFortuna PL": "https://www.efortuna.pl/example",
            },
            "bookmakers": {
                "Betclic PL": [
                    {
                        "name": "Moneyline",
                        "updatedAt": "2026-10-07T20:00:00Z",
                        "odds": [{"home": "2.20", "draw": "3.50", "away": "3.40"}],
                    },
                    {
                        "name": "Totals",
                        "odds": [{"hdp": 2.5, "over": "1.95", "under": "1.90"}],
                    },
                ],
                "eFortuna PL": [
                    {
                        "name": "Moneyline",
                        "odds": [{"home": "2.15", "draw": "3.60", "away": "3.55"}],
                    }
                ],
            },
        }
    ]
    rows = parse_odds_api_io_events(payload, fetched_at=1_800_000_000)
    by_market = {row["market"]: row for row in rows}
    assert "1X2" in by_market
    assert "Total 2.5" in by_market
    moneyline = by_market["1X2"]
    assert {q["bookmaker"] for q in moneyline["quotes"]["1"]} == {"Betclic", "Fortuna"}
    assert all(q["observed_at"] == 1_800_000_000 for q in moneyline["quotes"]["1"])
    assert any(q["link_exact"] for q in moneyline["quotes"]["1"])
