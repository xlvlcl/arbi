from app.merge import event_key, market_key, merge_markets
from app.providers.direct_books import DirectSource, parse_direct_listing


def test_betclic_like_three_way_link_parses_with_deep_link():
    html = '''
    <a href="/pilka-nozna-sfootball/uefa-liga-narodow-c22676/portugalia-norwegia-m1238830288998400">
      Portugalia 20:45 - Norwegia Portugalia 1,61 Remis 4,30 Norwegia 4,60
    </a>
    '''
    src = DirectSource("Betclic", ("https://www.betclic.pl/",), "https://www.betclic.pl/")
    rows = parse_direct_listing(html, src)
    assert len(rows) == 1
    assert rows[0]["market"] == "1X2"
    assert rows[0]["quotes"]["X"][0]["odds"] == 4.30
    assert rows[0]["quotes"]["1"][0]["bookmaker_url"].startswith("https://www.betclic.pl/")


def test_direct_two_way_never_invents_draw():
    html = '''
    <a href="/tenis/turniej/alcaraz-sinner-m123456789">
      Alcaraz - Sinner 1,90 2,05
    </a>
    '''
    src = DirectSource("Betclic", ("https://www.betclic.pl/",), "https://www.betclic.pl/")
    rows = parse_direct_listing(html, src)
    assert len(rows) == 1
    assert set(rows[0]["quotes"]) == {"1", "2"}
    assert rows[0]["market"] == "Winner"


def test_merge_preserves_direct_event_link_for_same_bookmaker():
    comparison = {
        "event": "Portugalia - Norwegia",
        "sport": "Piłka nożna",
        "market": "1X2",
        "event_url": "https://dobrybuk.pl/kursy/mecz/portugalia-norwegia",
        "source_name": "DobryBuk",
        "quotes": {
            "1": [{"selection":"1","odds":1.62,"bookmaker":"Betclic","observed_at":1,"source_url":"https://dobrybuk.pl/x","bookmaker_url":"https://dobrybuk.pl/out"}],
            "X": [{"selection":"X","odds":4.30,"bookmaker":"Betclic","observed_at":1,"source_url":"https://dobrybuk.pl/x","bookmaker_url":"https://dobrybuk.pl/out"}],
            "2": [{"selection":"2","odds":4.60,"bookmaker":"Betclic","observed_at":1,"source_url":"https://dobrybuk.pl/x","bookmaker_url":"https://dobrybuk.pl/out"}],
        },
    }
    direct = {
        "event": "Portugalia Norwegia",
        "sport": "Piłka nożna",
        "market": "1X2",
        "event_url": "https://www.betclic.pl/event",
        "source_name": "Betclic direct",
        "quotes": {
            "1": [{"selection":"1","odds":1.61,"bookmaker":"Betclic","observed_at":2,"source_url":"https://www.betclic.pl/event","bookmaker_url":"https://www.betclic.pl/event","source_name":"Betclic direct"}],
            "X": [{"selection":"X","odds":4.30,"bookmaker":"Betclic","observed_at":2,"source_url":"https://www.betclic.pl/event","bookmaker_url":"https://www.betclic.pl/event","source_name":"Betclic direct"}],
            "2": [{"selection":"2","odds":4.60,"bookmaker":"Betclic","observed_at":2,"source_url":"https://www.betclic.pl/event","bookmaker_url":"https://www.betclic.pl/event","source_name":"Betclic direct"}],
        },
    }
    merged = merge_markets([comparison, direct])
    assert len(merged) == 1
    assert merged[0]["quotes"]["1"][0]["odds"] == 1.62
    assert merged[0]["quotes"]["1"][0]["bookmaker_url"] == "https://www.betclic.pl/event"
    assert event_key("Portugalia - Norwegia") == event_key("Portugalia Norwegia")
    assert market_key("1X2") == "1x2"
