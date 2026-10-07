import asyncio
import json
import time
from pathlib import Path

from app.state import State


def run(coro):
    return asyncio.run(coro)


def test_first_alert_and_no_immediate_spam(tmp_path: Path):
    state = State(tmp_path / "state.json")
    assert run(state.should_alert("x", 1.00, 120, 6, 0.15)) is True
    assert run(state.should_alert("x", 1.05, 120, 6, 0.15)) is False


def test_profit_improvement_realerts(tmp_path: Path):
    state = State(tmp_path / "state.json")
    assert run(state.should_alert("x", 1.00, 120, 6, 0.15)) is True
    assert run(state.should_alert("x", 1.16, 120, 6, 0.15)) is True


def test_reappearance_realerts(tmp_path: Path):
    path = tmp_path / "state.json"
    state = State(path)
    assert run(state.should_alert("x", 1.00, 120, 6, 0.15)) is True

    payload = json.loads(path.read_text("utf-8"))
    payload["sent"]["x"]["last_seen"] = time.time() - 7 * 60
    path.write_text(json.dumps(payload), encoding="utf-8")

    state2 = State(path)
    assert run(state2.should_alert("x", 1.01, 120, 6, 0.15)) is True
