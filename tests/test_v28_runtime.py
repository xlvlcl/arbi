import asyncio
import json
import sys
from types import SimpleNamespace
from pathlib import Path

from scan_runtime import run, atomic_json, read_json
from app.providers.dobrybuk import DobryBukProvider


def prepare(tmp_path):
    atomic_json(tmp_path / 'docs/data/latest.json', {
        'last_scan': 100, 'latest': [{'id': 'old'}], 'valuebets': [{'id': 'old'}],
        'scan_preview': [{'id': 'old'}], 'data_fresh': True,
    })
    return tmp_path


def child(tmp_path, source):
    path = tmp_path / 'child.py'
    path.write_text(source)
    return [sys.executable, str(path)]


def test_success_publishes_new_data_and_captures_log(tmp_path):
    prepare(tmp_path)
    command = child(tmp_path, '''import json
from pathlib import Path
print("parsed fresh quotes", flush=True)
Path("docs/data/latest.json").write_text(json.dumps({"last_scan":200,"data_fresh":True,"latest":[{"id":"new"}]}))
''')
    result = run(tmp_path, command, timeout=3)
    data = read_json(tmp_path / 'docs/data/latest.json')
    assert result['state'] == 'ok'
    assert data['last_scan'] == 200
    assert data['latest'] == [{'id': 'new'}]
    assert 'parsed fresh quotes' in (tmp_path / 'scanner.log').read_text()
    assert read_json(tmp_path / 'docs/data/status.json')['state'] == 'ok'


def test_crash_preserves_last_success_and_clears_opportunities(tmp_path):
    prepare(tmp_path)
    result = run(tmp_path, child(tmp_path, 'raise RuntimeError("provider unavailable")'), 3)
    data = read_json(tmp_path / 'docs/data/latest.json')
    assert result['state'] == 'error'
    assert data['last_scan'] == 100
    assert data['latest'] == [] and data['valuebets'] == []
    assert data['scan_preview'] == [{'id': 'old'}]
    assert data['last_attempt'] > 100


def test_hung_process_is_terminated_and_status_saved(tmp_path):
    prepare(tmp_path)
    result = run(tmp_path, child(tmp_path, 'import time; time.sleep(30)'), 0.1)
    assert result['state'] == 'timeout'
    assert result['duration_seconds'] < 3
    assert read_json(tmp_path / 'docs/data/latest.json')['last_scan'] == 100


def test_unchanged_payload_is_not_a_success(tmp_path):
    prepare(tmp_path)
    result = run(tmp_path, child(tmp_path, 'print("no output")'), 3)
    assert result['state'] == 'error'


def test_degraded_payload_does_not_update_last_success(tmp_path):
    prepare(tmp_path)
    command = child(tmp_path, '''import json
from pathlib import Path
Path("docs/data/latest.json").write_text(json.dumps({"last_scan":999,"data_fresh":False,"scan_preview":[{"id":"cache"}]}))
''')
    result = run(tmp_path, command, 3)
    data = read_json(tmp_path / 'docs/data/latest.json')
    assert result['state'] == 'no_data'
    assert data['last_scan'] == 100
    assert data['scan_preview'] == [{'id': 'cache'}]


class Page:
    async def goto(self, *args, **kwargs): pass
    async def wait_for_load_state(self, *args, **kwargs): pass
    async def wait_for_timeout(self, *args, **kwargs): pass
    def locator(self, *args): return self
    async def inner_text(self, *args, **kwargs): return ''


def test_discovery_returns_completed_sports_when_next_sport_stalls(monkeypatch):
    monkeypatch.setenv('DISCOVERY_BUDGET_SECONDS', '0.1')
    provider = DobryBukProvider(SimpleNamespace(source_url='https://example.com'))
    provider.page = Page()
    async def nothing(*args): pass
    async def click(sport): return True
    async def collect(sport):
        if sport == 'First': return [{'event_url': '/one', 'sport': sport}]
        await asyncio.sleep(30)
    provider._dismiss_cookie_banner = nothing
    provider._prepare_all_upcoming = nothing
    provider._click_sport = click
    provider._collect_event_links = collect
    events, errors = asyncio.run(provider.discover_events(['First', 'Second']))
    assert events == [{'event_url': '/one', 'sport': 'First'}]
    assert any('TimeoutError' in error for error in errors)


def test_detail_budget_keeps_completed_event_when_next_event_stalls():
    provider = DobryBukProvider(SimpleNamespace())
    provider.page = Page()
    provider.context = object()
    async def scan(page, event):
        if event['event_url'] == '/one':
            return [{'event_url': '/one', 'market': '1X2', 'quotes': {}}], []
        await asyncio.sleep(30)
    provider._scan_event_markets = scan
    rows, errors, stats = asyncio.run(provider.scan_all_markets(
        [{'event_url': '/one'}, {'event_url': '/two'}], max_seconds=0.1, concurrency=1))
    assert len(rows) == 1 and rows[0]['event_url'] == '/one'
    assert stats['elapsed_seconds'] < 2
    assert any('TimeoutError' in error for error in errors)
