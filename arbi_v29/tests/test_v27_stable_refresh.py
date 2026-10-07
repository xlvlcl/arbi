from pathlib import Path
from scanner import _safe_float


def test_safe_float_does_not_crash():
    assert _safe_float("2.50") == 2.5
    assert _safe_float("bad") == 0.0
    assert _safe_float(None) == 0.0


def test_workflow_forces_fast_profile():
    root = Path(__file__).resolve().parents[1]
    wf = (root / ".github/workflows/surebet.yml").read_text("utf-8")
    assert "FORCE_FAST_SCAN: '1'" in wf
    assert "FAST_SCAN_BUDGET_SECONDS: '60'" in wf


def test_provider_has_public_html_fallback():
    root = Path(__file__).resolve().parents[1]
    provider = (root / "app/providers/dobrybuk.py").read_text("utf-8")
    assert "scan_static_http_fallback" in provider
    assert "urllib.request.urlopen" in provider
