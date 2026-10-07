"""Run the scanner in a bounded process and always publish an honest status.

v30 keeps the last successful opportunities visible when a provider is temporarily
blocked, but explicitly marks them as stale. This prevents one Cloudflare incident from
blanking the whole site while avoiding the dangerous impression that old odds are fresh.
"""
from __future__ import annotations
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read_json(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def stop_process(process):
    if process.poll() is not None:
        return
    if os.name == "posix":
        os.killpg(process.pid, signal.SIGTERM)
    else:
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait()


def _stale_copy(items, stale_since):
    out = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        copy = dict(item)
        copy["stale"] = True
        copy["stale_since"] = stale_since
        out.append(copy)
    return out


def run(root=ROOT, command=None, timeout=None):
    root = Path(root)
    output = root / "docs/data/latest.json"
    previous = read_json(output)
    started = time.time()
    deadline = float(timeout if timeout is not None else os.getenv("SCAN_DEADLINE_SECONDS", "260"))
    command = command or [sys.executable, "-u", str(root / "scanner.py")]
    state, message, code = "error", "", None
    before = output.read_bytes() if output.exists() else None

    try:
        with (root / "scanner.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                command,
                cwd=root,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=(os.name == "posix"),
            )
            try:
                code = process.wait(timeout=deadline)
            except subprocess.TimeoutExpired:
                stop_process(process)
                state, message = "timeout", f"Skan przekroczył limit {deadline:g} sekund."

        if not message:
            current = read_json(output)
            changed = output.exists() and output.read_bytes() != before
            if code != 0:
                message = f"Skaner zakończył się błędem (kod {code}). Sprawdź log skanera w Actions."
            elif not changed or not current:
                message = "Skaner nie zapisał nowego wyniku. Sprawdź log skanera w Actions."
            elif current.get("data_fresh") is not True:
                state, message = (
                    "no_data",
                    "Brak świeżych kursów z dostępnych źródeł. Ostatni poprawny wynik pozostaje widoczny jako STARY.",
                )
            else:
                state, message = "ok", "Nowy skan zakończony."
    except Exception as exc:
        message = f"Nie udało się uruchomić skanera: {type(exc).__name__}. Sprawdź Actions."

    finished = time.time()
    current = read_json(output)

    if state == "ok":
        payload = current
        # Fresh payloads must not carry stale flags inherited from an old run.
        for key in ("latest", "valuebets", "near_arbs"):
            if isinstance(payload.get(key), list):
                for item in payload[key]:
                    if isinstance(item, dict):
                        item.pop("stale", None)
                        item.pop("stale_since", None)
    else:
        # Keep current diagnostics/source-health when scanner managed to write them, while
        # preserving only the LAST SUCCESSFUL betting opportunities. Old odds are visibly
        # marked stale and the page status stays red/warning until fresh data returns.
        payload = dict(current) if current else dict(previous)
        if not payload:
            payload = {
                "last_scan": None,
                "latest": [],
                "valuebets": [],
                "near_arbs": [],
                "scan_preview": [],
                "coupon_catalog": [],
                "stats": {},
            }
        payload["last_scan"] = previous.get("last_scan")
        payload["latest"] = _stale_copy(previous.get("latest", []), finished)
        payload["valuebets"] = _stale_copy(previous.get("valuebets", []), finished)
        payload["near_arbs"] = _stale_copy(previous.get("near_arbs", []), finished)
        if not payload.get("scan_preview"):
            payload["scan_preview"] = previous.get("scan_preview", [])
        if not payload.get("coupon_catalog"):
            payload["coupon_catalog"] = previous.get("coupon_catalog", [])
        payload["data_fresh"] = False
        payload["data_status"] = "stale-last-good" if previous.get("last_scan") else state

    runtime = {
        "version": 30,
        "state": state,
        "message": message,
        "attempt_started_at": started,
        "attempt_finished_at": finished,
        "duration_seconds": round(finished - started, 2),
        "last_success_at": payload.get("last_scan"),
        "scanner_exit_code": code,
        "run_url": (
            f"https://github.com/{os.getenv('GITHUB_REPOSITORY')}/actions/runs/{os.getenv('GITHUB_RUN_ID')}"
            if os.getenv("GITHUB_REPOSITORY") and os.getenv("GITHUB_RUN_ID")
            else ""
        ),
    }
    payload["runtime"] = runtime
    payload["last_attempt"] = finished
    atomic_json(output, payload)
    atomic_json(root / "docs/data/status.json", runtime)
    print(json.dumps(runtime, ensure_ascii=False), flush=True)
    if os.getenv("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write(f"scanner_state={state}\n")
    return runtime


if __name__ == "__main__":
    run()
