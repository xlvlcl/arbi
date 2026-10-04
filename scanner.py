from __future__ import annotations

import asyncio
import hashlib
import json
import time
from pathlib import Path

from app.config import ROOT, settings
from app.merge import event_key, market_key, merge_markets
from app.models import Quote
from app.providers.direct_books import scan_direct_books
from app.providers.dobrybuk import DobryBukProvider
from app.state import State
from app.surebet import detect
from app.telegram import send
from app.onesignal_push import send_push

DOCS_DATA = ROOT / "docs" / "data"
ALERT_STATE = ROOT / "data" / "state.json"

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


def _public_offer(item: dict) -> dict:
    return {
        "bookmaker": str(item.get("bookmaker", "")),
        "odds": round(float(item.get("odds", 0) or 0), 3),
        "bookmaker_url": item.get("bookmaker_url", "") or item.get("source_url", ""),
        "source_url": item.get("source_url", ""),
        "source_name": item.get("source_name", "DobryBuk"),
    }


def build_scan_preview(markets: list[dict], limit: int = 100) -> list[dict]:
    preview = []
    seen = set()
    for item in markets:
        key = (
            event_key(str(item.get("event", ""))),
            market_key(str(item.get("market", ""))),
        )
        if key in seen:
            continue
        seen.add(key)

        best = []
        for selection, quotes in (item.get("quotes") or {}).items():
            valid = [q for q in quotes if q.get("bookmaker") and q.get("odds")]
            if not valid:
                continue
            valid = sorted(valid, key=lambda x: float(x.get("odds", 0)), reverse=True)
            q = valid[0]
            best.append(
                {
                    "selection": str(selection),
                    **_public_offer(q),
                    "alternatives": [_public_offer(x) for x in valid[1:5]],
                }
            )

        preview.append(
            {
                "event": item.get("event", ""),
                "sport": item.get("sport", ""),
                "market": item.get("market", ""),
                "event_url": item.get("event_url", ""),
                "best": best[:8],
                "sources": item.get("source_names", [item.get("source_name", "DobryBuk")]),
            }
        )
        if len(preview) >= limit:
            break
    return preview


def build_coupon_catalog(markets: list[dict], limit: int = 350) -> list[dict]:
    catalog = []
    seen = set()
    for item in markets:
        ekey = event_key(str(item.get("event", "")))
        mkey = market_key(str(item.get("market", "")))
        key = (ekey, mkey)
        if not ekey or not mkey or key in seen:
            continue
        seen.add(key)

        selections = []
        for label, quotes in (item.get("quotes") or {}).items():
            per_book = {}
            for quote in quotes:
                book = str(quote.get("bookmaker", "")).strip()
                odd = float(quote.get("odds", 0) or 0)
                if not book or odd <= 1:
                    continue
                old = per_book.get(book)
                if old is None or odd > float(old.get("odds", 0)):
                    per_book[book] = quote
            offers = [_public_offer(q) for q in per_book.values()]
            offers.sort(key=lambda x: x["odds"], reverse=True)
            if offers:
                selections.append(
                    {
                        "selection": str(label),
                        "best_odds": offers[0]["odds"],
                        "best_bookmaker": offers[0]["bookmaker"],
                        "offers": offers,
                    }
                )

        if not selections:
            continue
        digest = hashlib.sha1(f"{ekey}|{mkey}".encode("utf-8")).hexdigest()[:14]
        catalog.append(
            {
                "id": digest,
                "event": item.get("event", ""),
                "sport": item.get("sport", ""),
                "market": item.get("market", ""),
                "event_url": item.get("event_url", ""),
                "sources": item.get("source_names", [item.get("source_name", "DobryBuk")]),
                "selections": selections,
            }
        )
        if len(catalog) >= limit:
            break
    return catalog


def _find_dobrybuk_confirmation_targets(candidates, dobrybuk_rows: list[dict]) -> list[dict]:
    index = {}
    for row in dobrybuk_rows:
        key = (event_key(row.get("event", "")), market_key(row.get("market", "")))
        if row.get("event_url"):
            index[key] = row

    targets = []
    seen = set()
    for arb in candidates:
        key = (event_key(arb.event), market_key(arb.market))
        row = index.get(key)
        if not row:
            continue
        target_key = (row.get("event_url", ""), row.get("market", ""))
        if target_key in seen:
            continue
        seen.add(target_key)
        targets.append(
            {
                "event": row.get("event", arb.event),
                "sport": row.get("sport", arb.sport),
                "market": row.get("market", arb.market),
                "event_url": row.get("event_url", ""),
            }
        )
    return targets


async def scan_once() -> dict:
    started = time.time()
    provider = DobryBukProvider(settings)
    state = State(ALERT_STATE)
    errors: list[str] = []

    # Direct bookmaker pages are lightweight HTTP requests, so run them in parallel
    # with the browser-based comparison scan instead of adding minutes to each cycle.
    direct_task = asyncio.create_task(
        scan_direct_books(
            enabled=bool(getattr(settings, "direct_sources_enabled", True)),
            timeout=float(getattr(settings, "direct_sources_timeout", 12)),
            concurrency=int(getattr(settings, "direct_sources_concurrency", 5)),
        )
    )

    await provider.start()
    try:
        scan_mode = "detail"
        events, discover_errors = await provider.discover_events(settings.sports)
        errors.extend(discover_errors)

        dobrybuk_rows = []
        market_errors = []
        market_stats = {
            "detail_events_scanned": 0,
            "detail_events_total": len(events),
            "exhaustive_complete": False,
        }

        if events:
            dobrybuk_rows, market_errors, market_stats = await provider.scan_all_markets(
                events,
                max_events=settings.market_scan_max_events,
                max_seconds=settings.market_scan_budget_seconds,
                concurrency=settings.market_scan_concurrency,
            )
            errors.extend([f"Markety: {x}" for x in market_errors])

        if not dobrybuk_rows:
            scan_mode = "listing-fallback"
            fallback_rows, fallback_errors = await provider.scan_listing_fallback(
                list(getattr(provider, "discovered_sports", []) or settings.sports)
            )
            errors.extend([f"Fallback: {x}" for x in fallback_errors])
            dobrybuk_rows = fallback_rows

            if fallback_rows:
                if not events:
                    events = [
                        {
                            "event": row.get("event", ""),
                            "sport": row.get("sport", ""),
                            "event_url": row.get("event_url", ""),
                        }
                        for row in fallback_rows
                    ]
                unique_events = {
                    (str(r.get("sport", "")).lower(), event_key(str(r.get("event", ""))))
                    for r in fallback_rows
                }
                market_stats = {
                    "detail_events_scanned": len(unique_events),
                    "detail_events_total": len(unique_events),
                    "exhaustive_complete": False,
                }

        try:
            direct_rows, direct_errors, direct_stats = await direct_task
        except Exception as exc:
            direct_rows, direct_errors, direct_stats = [], [f"direct: {exc}"], {"enabled": True, "sources": {}}
        errors.extend([f"Direct: {x}" for x in direct_errors])

        merged_rows = merge_markets(dobrybuk_rows + direct_rows)
        if not merged_rows:
            raise RuntimeError(
                "Żadne źródło nie zwróciło kursów. Nie nadpisuję poprawnych danych pustym skanem."
            )

        candidates = detect_from_markets(merged_rows)

        confirmed = []
        if candidates:
            await asyncio.sleep(max(0.5, min(2.0, float(settings.recheck_delay_seconds))))
            targets = _find_dobrybuk_confirmation_targets(candidates, dobrybuk_rows)
            confirm_rows = []
            if targets:
                confirm_rows, confirm_errors = await provider.scan_specific_markets(
                    targets,
                    concurrency=settings.confirm_concurrency,
                    max_seconds=90,
                )
                errors.extend([f"Potwierdzenie: {x}" for x in confirm_errors])

            # Re-fetch direct pages too so a multi-source candidate is never confirmed
            # using stale direct odds from the start of the scan.
            direct_confirm_rows, direct_confirm_errors, _ = await scan_direct_books(
                enabled=bool(getattr(settings, "direct_sources_enabled", True)),
                timeout=float(getattr(settings, "direct_sources_timeout", 12)),
                concurrency=int(getattr(settings, "direct_sources_concurrency", 5)),
            )
            errors.extend([f"Potwierdzenie direct: {x}" for x in direct_confirm_errors])
            confirmed = detect_from_markets(merge_markets(confirm_rows + direct_confirm_rows))

        alerts_sent = 0
        push_alerts_sent = 0
        telegram_alerts_sent = 0
        push_configured = bool(settings.onesignal_app_id and settings.onesignal_api_key)
        telegram_configured = bool(settings.telegram_token and settings.telegram_chat_id)

        for arb in confirmed:
            if not (push_configured or telegram_configured):
                continue

            should_send = await state.should_alert(
                arb.key(),
                arb.profit_pct,
                settings.dedupe_minutes,
                reappear_minutes=settings.alert_reappear_minutes,
                improvement_pct=settings.alert_improvement_pct,
            )
            if not should_send:
                continue

            delivered = False
            if push_configured:
                try:
                    result = await send_push(
                        settings.onesignal_app_id,
                        settings.onesignal_api_key,
                        arb,
                        settings.app_public_url,
                    )
                    push_alerts_sent += 1
                    delivered = True
                    if isinstance(result, dict) and result.get("errors"):
                        errors.append(f"OneSignal odpowiedź: {result.get('errors')}")
                except Exception as exc:
                    errors.append(f"OneSignal: {exc}")

            # Telegram zostaje opcjonalnym backupem. Możesz usunąć jego sekrety,
            # jeśli chcesz dostawać wyłącznie powiadomienia z aplikacji.
            if telegram_configured:
                try:
                    await send(
                        settings.telegram_token,
                        settings.telegram_chat_id,
                        arb,
                    )
                    telegram_alerts_sent += 1
                    delivered = True
                except Exception as exc:
                    errors.append(f"Telegram: {exc}")

            if delivered:
                alerts_sent += 1

        now = time.time()
        sources = {
            "DobryBuk": {
                "markets": len(dobrybuk_rows),
                "events": len({(event_key(str(r.get("event", ""))), str(r.get("sport", "")).lower()) for r in merged_rows}),
                "mode": "comparison",
            },
            **(direct_stats.get("sources", {}) if isinstance(direct_stats, dict) else {}),
        }
        coupon_catalog = build_coupon_catalog(
            merged_rows,
            int(getattr(settings, "coupon_catalog_limit", 1600)),
        )
        payload = {
            "generated_at": now,
            "last_scan": now,
            "latest": [arb.to_dict() for arb in confirmed[:200]],
            "scan_preview": build_scan_preview(merged_rows, 120),
            "coupon_catalog": coupon_catalog,
            "stats": {
                "events": len(events),
                "sports_scanned": len(getattr(provider, "discovered_sports", []) or []),
                "sports": list(getattr(provider, "discovered_sports", []) or []),
                "detail_events_scanned": market_stats.get("detail_events_scanned", 0),
                "detail_events_total": market_stats.get("detail_events_total", len(events)),
                "markets": len(merged_rows),
                "markets_scanned": len(merged_rows),
                "dobrybuk_markets": len(dobrybuk_rows),
                "direct_markets": len(direct_rows),
                "exhaustive_complete": market_stats.get("exhaustive_complete", False),
                "candidates": len(candidates),
                "surebets": len(confirmed),
                "alerts_sent": alerts_sent,
                "push_alerts_sent": push_alerts_sent,
                "telegram_alerts_sent": telegram_alerts_sent,
                "push_configured": push_configured,
                "elapsed_seconds": round(time.time() - started, 2),
                "scanner": "multi-source-v17-resilient-coupon",
                "scan_mode": scan_mode,
                "sources": sources,
            },
            "errors": errors[-80:],
            "source": "DobryBuk + direct bookmaker pages",
            "coupon_catalog_info": {
                "items": len(coupon_catalog),
                "mode": "bookmaker-first",
            },
            "market_scan_note": (
                "DobryBuk pozostaje głównym źródłem pełnych tabel rynków. Dodatkowo skaner "
                "pobiera konserwatywnie rozpoznane kursy bezpośrednio z publicznych stron bukmacherów "
                "i łączy je tylko przy zgodnym zdarzeniu oraz rynku. Niepewne fragmenty są pomijane."
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
                    "errors": payload["errors"][-12:],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return payload
    finally:
        if not direct_task.done():
            direct_task.cancel()
        await provider.stop()


if __name__ == "__main__":
    asyncio.run(scan_once())
