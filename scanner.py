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

# Keep the tax/payout assumptions from the current project. They can be overridden
# in data/settings.json through bookmaker_payout_factors.
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
    "Etoto": 0.88,
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
    factors = dict(DEFAULT_FACTORS)
    factors.update(settings.bookmaker_payout_factors or {})
    return factors


def event_to_quotes(event: dict) -> dict[str, list[Quote]]:
    out: dict[str, list[Quote]] = {}
    for selection, items in (event.get("quotes") or {}).items():
        for item in items:
            bookmaker = item.get("bookmaker", "")
            if not bookmaker or bookmaker == "Unknown":
                continue
            out.setdefault(selection, []).append(
                Quote(
                    selection=item["selection"],
                    odds=float(item["odds"]),
                    bookmaker=bookmaker,
                    observed_at=float(item["observed_at"]),
                    source_url=item.get("source_url", event.get("event_url", "")),
                    bookmaker_url=item.get("bookmaker_url", ""),
                )
            )
    return out


def detect_from_markets(markets: list[dict]):
    found = []
    factors = payout_factors()
    for item in markets:
        found.extend(
            detect(
                item["event"],
                item["sport"],
                item["market"],
                event_to_quotes(item),
                settings.bankroll,
                factors,
                settings.min_profit_pct,
                settings.max_quote_age_seconds,
            )
        )
    return dedupe_surebets(found)


def dedupe_surebets(items):
    unique = {}
    for arb in items:
        key = (
            arb.event.strip().lower(),
            arb.sport.strip().lower(),
            arb.market.strip().lower(),
            tuple(
                sorted(
                    (
                        leg.selection.strip().lower(),
                        leg.bookmaker.strip().lower(),
                        round(leg.odds, 3),
                    )
                    for leg in arb.legs
                )
            ),
        )
        old = unique.get(key)
        if old is None or arb.profit_pct > old.profit_pct:
            unique[key] = arb
    return sorted(unique.values(), key=lambda x: x.profit_pct, reverse=True)


async def scan_once() -> dict:
    started = time.time()
    provider = DobryBukProvider(settings)
    state = State(ALERT_STATE)
    errors: list[str] = []

    await provider.start()
    try:
        # 1) Discover every event link from every supported sport visible on the source.
        events, discover_errors = await provider.discover_events(settings.sports)
        errors.extend(discover_errors)
        if not events:
            raise RuntimeError(
                "Skaner nie odczytał żadnych wydarzeń. Nie publikuję pustego wyniku."
            )

        # 2) Visit event detail pages and scan every visible market button.
        market_rows, market_errors, market_stats = await provider.scan_all_markets(
            events,
            max_events=settings.market_scan_max_events,
            max_seconds=settings.market_scan_budget_seconds,
            concurrency=settings.market_scan_concurrency,
        )
        errors.extend([f"Markety: {x}" for x in market_errors])
        if not market_rows:
            raise RuntimeError(
                "Znaleziono wydarzenia, ale nie odczytano pełnych tabel kursów. "
                "Nie publikuję pustego wyniku."
            )

        # 3) Detect only mathematically complete outcome sets.
        candidates = detect_from_markets(market_rows)

        # 4) Recheck exact candidate event+market combinations before showing/sending them.
        confirmed = []
        if candidates:
            await asyncio.sleep(max(0.5, min(2.0, float(settings.recheck_delay_seconds))))
            targets = [
                {
                    "event": arb.event,
                    "sport": arb.sport,
                    "market": arb.market,
                    "event_url": arb.event_url,
                }
                for arb in candidates
                if arb.event_url
            ]
            confirm_rows, confirm_errors = await provider.scan_specific_markets(
                targets,
                concurrency=settings.confirm_concurrency,
                max_seconds=90,
            )
            errors.extend([f"Potwierdzenie: {x}" for x in confirm_errors])
            confirmed = detect_from_markets(confirm_rows)

        alerts_sent = 0
        for arb in confirmed:
            if (
                settings.telegram_token
                and settings.telegram_chat_id
                and await state.should_alert(
                    arb.key(), arb.profit_pct, settings.dedupe_minutes
                )
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
        payload = {
            "generated_at": now,
            "last_scan": now,
            "latest": [arb.to_dict() for arb in confirmed[:200]],
            "stats": {
                "events": len(events),
                "sports_scanned": len(getattr(provider, "discovered_sports", []) or []),
                "sports": list(getattr(provider, "discovered_sports", []) or []),
                "detail_events_scanned": market_stats.get("detail_events_scanned", 0),
                "detail_events_total": market_stats.get("detail_events_total", len(events)),
                "markets": market_stats.get("markets_scanned", len(market_rows)),
                "markets_scanned": market_stats.get("markets_scanned", len(market_rows)),
                "exhaustive_complete": market_stats.get("exhaustive_complete", False),
                "candidates": len(candidates),
                "surebets": len(confirmed),
                "alerts_sent": alerts_sent,
                "elapsed_seconds": round(time.time() - started, 2),
                "scanner": "playwright-auto-sports-all-event-markets-v12",
            },
            "errors": errors[-40:],
            "source": "DobryBuk public comparison",
            "market_scan_note": (
                "Skan automatycznie wykrywa wszystkie sporty wystawione w porównywarce, "
                "a następnie odwiedza wydarzenia i widoczne na ich stronach rynki w ramach budżetu czasu. "
                "Niepełne/niejednoznaczne rynki są odrzucane."
            ),
        }

        DOCS_DATA.mkdir(parents=True, exist_ok=True)
        (DOCS_DATA / "latest.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print(
            json.dumps(
                {
                    "stats": payload["stats"],
                    "errors": payload["errors"][-10:],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return payload
    finally:
        await provider.stop()


if __name__ == "__main__":
    asyncio.run(scan_once())
