import time
from app.valuebets import detect_valuebets
from app.onesignal_push import build_value_payload

def make_market():
    now=time.time()
    books=["Betclic","Fortuna","STS","Superbet","Betfan","LVBet","ETOTO"]
    quotes={"U 2.5":[],"O 2.5":[]}
    for i,book in enumerate(books):
        u=2.32 if book=="Betclic" else 2.00+(i%2)*0.02
        o=1.90+(i%3)*0.02
        source="Betclic direct" if book=="Betclic" else "DobryBuk"
        url="https://www.betclic.pl/event/abc" if book=="Betclic" else "https://dobrybuk.pl/kursy/mecz/a"
        for sel,odd in [("U 2.5",u),("O 2.5",o)]:
            quotes[sel].append({"selection":sel,"odds":odd,"bookmaker":book,"observed_at":now,"source_url":url,"bookmaker_url":url,"source_name":source})
    return {"event":"A - B","sport":"Piłka nożna","market":"U/O 2.5","quotes":quotes,"event_url":"https://dobrybuk.pl/kursy/mecz/a"}

def test_value_has_risk_and_exact_link_metadata():
    rows=detect_valuebets([make_market()],{b:1.0 for b in ["Betclic","Fortuna","STS","Superbet","Betfan","LVBet","ETOTO"]},min_edge_pct=5,min_reference_books=5)
    assert rows
    v=next(x for x in rows if x["bookmaker"]=="Betclic")
    assert 0 <= v["outcome_risk_pct"] <= 100
    assert 5 <= v["signal_risk_pct"] <= 95
    assert v["bookmaker_link_exact"] is True
    assert "/event/" in v["exact_bookmaker_url"]

def test_value_push_opens_app_and_exact_button():
    value={"event":"A - B","market":"U/O 2.5","selection":"U 2.5","bookmaker":"Betclic","odds":2.3,"edge_pct":6.0,"outcome_risk_pct":55.0,"exact_bookmaker_url":"https://www.betclic.pl/event/abc"}
    payload=build_value_payload("app",value,"https://xlvlcl.github.io/arbi/")
    assert payload["url"].endswith("/#value")
    assert payload["web_buttons"][0]["url"].endswith("/event/abc")
