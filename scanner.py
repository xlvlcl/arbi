from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from app.config import settings
from app.source.dobrybuk_http import DobryBukHTTP
from app.surebet import detect
from app.state import AlertState
from app.telegram import send


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "docs" / "data"
STATE = ROOT / "data" / "alerts.json"


async def scan_once() -> dict:
    provider = DobryBukHTTP(
        settings.source_url,
        concurrency=settings.concurrency,
        timeout=settings.request_timeout,
    )
    state = AlertState(STATE)

    await provider.start()
    try:
        result = await provider.scan(
            max_events=settings.max_events,
            max_markets=settings.max_markets_per_event,
        )

        found = []
        for item in result["markets"]:
            arbs = detect(
                item["event"],
                item["sport"],
                item["market"],
                item["quotes"],
                settings.bankroll,
                settings.min_profit_pct,
            )
            found.extend(arbs)

        unique = {}
        for arb in found:
            old = unique.get(arb.key())
            if old is None or arb.profit_pct > old.profit_pct:
                unique[arb.key()] = arb

        surebets = sorted(unique.values(), key=lambda x: x.profit_pct, reverse=True)

        alerts_sent = 0
        for arb in surebets:
            if state.should_alert(arb.key(), arb.profit_pct, settings.dedupe_minutes):
                if settings.telegram_token and settings.telegram_chat_id:
                    try:
                        await send(settings.telegram_token, settings.telegram_chat_id, arb)
                        alerts_sent += 1
                    except Exception as exc:
                        result["errors"].append(f"Telegram: {exc}")

        payload = {
            "generated_at": time.time(),
            "last_scan": time.time(),
            "latest": [x.to_dict() for x in surebets[:200]],
            "stats": {
                "events": len(result["events"]),
                "markets": len(result["markets"]),
                "surebets": len(surebets),
                "alerts_sent": alerts_sent,
                "elapsed_seconds": result["elapsed"],
                "scanner": "httpx-no-playwright",
            },
            "errors": result["errors"][-20:],
            "source": "DobryBuk public comparison",
        }

        DATA.mkdir(parents=True, exist_ok=True)
        (DATA / "latest.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return payload
    finally:
        await provider.stop()


async def main():
    payload = await scan_once()
    print(json.dumps(payload["stats"], ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
