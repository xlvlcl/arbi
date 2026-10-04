from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from app.config import ROOT, settings
from app.models import Quote
from app.providers.dobrybuk import DobryBukProvider
from app.state import State
from app.surebet import detect
from app.telegram import render, send


DOCS_DATA = ROOT / "docs" / "data"
ALERT_STATE = ROOT / "data" / "state.json"

# Zachowane z działającej wersji lokalnej.
# 1.00 = brak potrącenia od stawki w tym modelu; 0.88 = robocze 12%.
# Rzeczywiste zasady operatora/promocji trzeba zawsze sprawdzić przed zakładem.
DEFAULT_FACTORS = {
    "Betclic": 1.0,
    "Fortuna": 1.0,
    "eFortuna": 1.0,
    "Superbet": 0.88,
    "STS": 0.88,
    "Forbet": 0.88,
    "LVBet": 0.88,
    "ETOTO": 0.88,
    "eToto": 0.88,
    "Betfan": 0.88,
    "Fuksiarz": 0.88,
    "TotalBet": 0.88,
    "Total Bet": 0.88,
    "Betters": 0.88,
    "LeBull": 0.88,
    "AdmiralBet": 0.88,
    "BetSport": 0.88,
    "Betsport": 0.88,
    "ComeOn": 0.88,
    "PZBuk": 0.88,
}


def payout_factors() -> dict[str, float]:
    result = dict(DEFAULT_FACTORS)
    result.update(settings.bookmaker_payout_factors or {})
    return result


def event_to_quotes(event: dict) -> dict[str, list[Quote]]:
    qdict: dict[str, list[Quote]] = {}
    for selection, items in event["quotes"].items():
        for item in items:
            if item["bookmaker"] == "Unknown":
                continue
            qdict.setdefault(selection, []).append(
                Quote(
                    item["selection"],
                    item["odds"],
                    item["bookmaker"],
                    item["observed_at"],
                    item["source_url"],
                )
            )
    return qdict


async def detect_from_events(events: list[dict]):
    found = []
    factors = payout_factors()

    for event in events:
        found.extend(
            detect(
                event["event"],
                event["sport"],
                event["market"],
                event_to_quotes(event),
                settings.bankroll,
                factors,
                settings.min_profit_pct,
                settings.max_quote_age_seconds,
            )
        )

    # Unikalne okazje; zostaw najlepszą wersję tego samego klucza.
    unique = {}
    for arb in found:
        old = unique.get(arb.key())
        if old is None or arb.profit_pct > old.profit_pct:
            unique[arb.key()] = arb

    return sorted(unique.values(), key=lambda a: a.profit_pct, reverse=True)


async def scan_once() -> dict:
    started = time.time()
    provider = DobryBukProvider(settings)
    state = State(ALERT_STATE)
    errors: list[str] = []

    await provider.start()
    try:
        events, scan_errors = await provider.scan_all(settings.sports)
        errors.extend(scan_errors)

        # Bardzo ważne: nie publikujemy "0" jako poprawnego skanu, jeśli scraper
        # nic nie odczytał. Dzięki temu ostatnia dobra wersja strony zostaje online.
        if not events:
            raise RuntimeError(
                "Skaner nie odczytał żadnych wydarzeń. "
                "Nie publikuję pustego wyniku."
            )

        candidates = await detect_from_events(events)

        # Krótkie potwierdzenie tylko gdy faktycznie mamy kandydata.
        confirmed = []
        if candidates:
            await asyncio.sleep(max(1, min(3, int(settings.recheck_delay_seconds))))
            sports_to_recheck = sorted({arb.sport for arb in candidates})
            confirm_events, confirm_errors = await provider.scan_all(sports_to_recheck)
            errors.extend([f"Potwierdzenie: {x}" for x in confirm_errors])
            confirm_candidates = await detect_from_events(confirm_events)
            confirm_map = {arb.key(): arb for arb in confirm_candidates}
            confirmed = [confirm_map[a.key()] for a in candidates if a.key() in confirm_map]

        alerts_sent = 0
        for arb in confirmed:
            if (
                await state.should_alert(
                    arb.key(),
                    arb.profit_pct,
                    settings.dedupe_minutes,
                )
                and settings.telegram_token
                and settings.telegram_chat_id
            ):
                try:
                    await send(
                        settings.telegram_token,
                        settings.telegram_chat_id,
                        render(arb),
                    )
                    alerts_sent += 1
                except Exception as exc:
                    errors.append(f"Telegram: {exc}")

        now = time.time()
        markets = len(
            {
                (event["sport"], event["event"], event["market"])
                for event in events
            }
        )

        payload = {
            "generated_at": now,
            "last_scan": now,
            "latest": [arb.to_dict() for arb in confirmed[:200]],
            "stats": {
                "events": len(events),
                "markets": markets,
                "candidates": len(candidates),
                "surebets": len(confirmed),
                "alerts_sent": alerts_sent,
                "elapsed_seconds": round(time.time() - started, 2),
                "scanner": "playwright-known-good",
            },
            "errors": errors[-30:],
            "source": "DobryBuk public comparison",
        }

        DOCS_DATA.mkdir(parents=True, exist_ok=True)
        (DOCS_DATA / "latest.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return payload
    finally:
        await provider.stop()


if __name__ == "__main__":
    asyncio.run(scan_once())
