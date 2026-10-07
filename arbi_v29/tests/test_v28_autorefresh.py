from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_frontend_polls_every_three_seconds_and_refreshes_on_focus():
    js = (ROOT / "docs/app.js").read_text("utf-8")
    assert "const AUTO_REFRESH_MS=3000" in js
    assert 'window.addEventListener("focus",refreshSilently)' in js
    assert 'cache:"no-store"' in js
    assert "Date.now()" in js


def test_heartbeat_is_manual_when_external_trigger_is_active():
    wf = (ROOT / ".github/workflows/heartbeat.yml").read_text("utf-8")
    assert "workflow_dispatch" in wf
    assert "sleep 120" not in wf
    assert "schedule:" not in wf
    assert "https://api.github.com/repos/${REPOSITORY}/dispatches" in wf
    assert '"event_type":"surebet_scan"' in wf
    assert "contents: write" in wf


def test_automatic_scans_skip_full_pages_deploy():
    wf = (ROOT / ".github/workflows/surebet.yml").read_text("utf-8")
    assert "deploy_pages:" in wf
    assert "github.event_name == 'workflow_dispatch'" in wf
    assert "actions/deploy-pages@v4" in wf
