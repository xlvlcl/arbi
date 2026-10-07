from app.providers.dobrybuk import DobryBukProvider


def test_market_label_hints_cover_visible_dobrybuk_markets():
    provider = object.__new__(DobryBukProvider)
    labels = [
        "1x2",
        "1X / X2 / 12",
        "U/O 1.5",
        "U/O 2.5",
        "U/O 3.5",
        "BTS",
        "DNB",
        "H -2.5",
        "H +1.5",
        "Celne strzały",
        "Strzały",
        "Spalone",
        "Faule",
    ]
    assert all(provider._looks_like_market_label(x) for x in labels)
