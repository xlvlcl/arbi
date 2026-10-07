import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_preferences_are_initialized_before_budget_uses_pref():
    js = (ROOT / "docs/app.js").read_text("utf-8")
    assert js.index("let uiPrefs=readPrefs()") < js.index("let budget=Math.max")


def test_auth_refreshes_config_and_remembers_forever():
    js = (ROOT / "docs/app.js").read_text("utf-8")
    assert "refreshAuthConfig" in js
    assert "Max-Age=315360000" in js
    assert "rememberAccess(expected)" in js


def test_help_dictionary_is_broad():
    js = (ROOT / "docs/app.js").read_text("utf-8")
    keys = [
        "surebet:", "radar:", "value:", "edge:", "fairOdds:", "fairChance:",
        "outcomeRisk:", "signalRisk:", "coverage:", "coupon:", "push:",
        "market:", "odds:", "stake:", "scanMode:", "watchlist:",
    ]
    assert all(key in js for key in keys)


def test_assets_have_cache_busting():
    html = (ROOT / "docs/index.html").read_text("utf-8")
    assert re.search(r"\./app\.js\?v=\d+", html)
    assert "./app.css?v=24" in html
    assert "./auth-config.js?v=24" in html
