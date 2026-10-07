from pathlib import Path
from app.market_cache import MarketCache


def test_cache_tolerates_bad_values(tmp_path: Path):
    cache = MarketCache(tmp_path / "cache.json")
    cache.update([{
        "event":"A - B","sport":"Inne","market":"1X2",
        "event_url":"https://example.test/a",
        "observed_at":"bad-time","source_names":"DobryBuk",
        "quotes":{"1":[{"selection":"1","bookmaker":"STS","odds":2.1,"observed_at":"bad-time"}]},
    }])
    rows = cache.snapshot(300)
    assert len(rows) == 1
    assert rows[0]["source_names"] == ["DobryBuk"]


def test_workflow_captures_log():
    root = Path(__file__).resolve().parents[1]
    wf = (root / ".github/workflows/surebet.yml").read_text("utf-8")
    assert "python -u scan_runtime.py" in wf
    assert "scanner.log" in wf
    assert "scanner-debug-${{ github.run_id }}" in wf
