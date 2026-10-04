from types import SimpleNamespace
from app.onesignal_push import build_payload


def test_build_push_payload():
    arb = SimpleNamespace(
        profit_pct=2.34,
        event="Polska - Niemcy",
        sport="Piłka nożna",
        market="1X2",
        legs=[
            SimpleNamespace(bookmaker="Betclic", selection="1", odds=2.10, bookmaker_url="https://example.com/a", source_url=""),
            SimpleNamespace(bookmaker="STS", selection="X2", odds=2.05, bookmaker_url="https://example.com/b", source_url=""),
        ],
    )
    payload = build_payload("app-id", arb, "https://xlvlcl.github.io/arbi/")
    assert payload["app_id"] == "app-id"
    assert payload["target_channel"] == "push"
    assert payload["included_segments"] == ["Subscribed Users"]
    assert "+2.34%" in payload["headings"]["pl"]
    assert payload["url"].startswith("https://")
    assert len(payload["web_buttons"]) == 2
