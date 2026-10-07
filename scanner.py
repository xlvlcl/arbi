from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from pathlib import Path

from app.config import ROOT, settings
from scan_runtime import atomic_json, read_json
from app.merge import event_key, market_key, merge_markets
from app.models import Quote
from app.intelligence import detect_near_arbs, scan_quality
from app.market_cache import MarketCache
from app.providers.direct_books import scan_direct_books, scan_direct_books_browser
from app.providers.dobrybuk import DobryBukProvider
from app.state import State
from app.surebet import detect
from app.telegram import send
from app.valuebets import detect_valuebets
from app.onesignal_push import send_push, send_value_push

DOCS_DATA = ROOT / "docs" / "data"
ALERT_STATE = ROOT / "data" / "state.json"
MARKET_CACHE = ROOT / "data" / "market_cache.json"

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


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return float(default)


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
            try:
                odds = float(item.get("odds", 0) or 0)
                observed_at = float(
                    item.get("observed_at", event.get("observed_at", time.time()))
                    or time.time()
                )
            except (TypeError, ValueError):
                continue
            if odds <= 1.0:
                continue
            out.setdefault(selection, []).append(
                Quote(
                    selection=str(item.get("selection", selection)),
                    odds=odds,
                    bookmaker=bookmaker,
                    observed_at=observed_at,
                    source_url=item.get("source_url", event.get("event_url", "")),
                    bookmaker_url=item.get("bookmaker_url", ""),
                    source_name=item.get("source_name", ""),
                    link_exact=bool(
                        item.get("bookmaker_url")
                        and "direct" in str(item.get("source_name", "")).lower()
                    ),
                )
            )
    return out


def detect_from_markets(markets: list[dict]):
    found = []
    factors = payout_factors()
    for item in markets:
        try:
            event = str(item.get("event", "") or "")
            sport = str(item.get("sport", "Inne") or "Inne")
            market = str(item.get("market", "") or "")
            if not event or not market:
                continue
            found.extend(
                detect(
                    event,
                    sport,
                    market,
                    event_to_quotes(item),
                    settings.bankroll,
                    factors,
                    settings.min_profit_pct,
                    settings.max_quote_age_seconds,
                )
            )
        except Exception:
            continue
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
    source_name = str(item.get("source_name", "DobryBuk"))
    bookmaker_url = item.get("bookmaker_url", "") or ""
    exact_url = bookmaker_url if bookmaker_url and "direct" in source_name.lower() else ""
    return {
        "bookmaker": str(item.get("bookmaker", "")),
        "odds": round(_safe_float(item.get("odds", 0), 0.0), 3),
        "bookmaker_url": bookmaker_url or item.get("source_url", ""),
        "exact_bookmaker_url": exact_url,
        "bookmaker_link_exact": bool(exact_url),
        "source_url": item.get("source_url", ""),
        "source_name": source_name,
    }


def _event_identity(item: dict) -> str:
    url = str(item.get("event_url", "") or "").strip()
    if url:
        return url.split("#", 1)[0].split("?", 1)[0].rstrip("/").lower()
    return event_key(str(item.get("event", "")))


def build_scan_preview(markets: list[dict], limit: int = 100) -> list[dict]:
    preview = []
    seen = set()
    for item in markets:
        key = (
            _event_identity(item),
            market_key(str(item.get("market", ""))),
        )
        if key in seen:
            continue
        seen.add(key)

        best = []
        for selection, quotes in (item.get("quotes") or {}).items():
            valid = [
                q for q in quotes
                if q.get("bookmaker") and _safe_float(q.get("odds", 0), 0.0) > 1.0
            ]
            if not valid:
                continue
            valid = sorted(
                valid,
                key=lambda x: _safe_float(x.get("odds", 0), 0.0),
                reverse=True,
            )
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
        ekey = _event_identity(item)
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
                odd = _safe_float(quote.get("odds", 0), 0.0)
                if not book or odd <= 1:
                    continue
                old = per_book.get(book)
                if old is None or odd > _safe_float(old.get("odds", 0), 0.0):
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


def _enrich_market_metadata(markets: list[dict], events: list[dict]) -> list[dict]:
    by_url = {}
    by_key = {}
    for event in events or []:
        url = str(event.get("event_url", "") or "").split("#", 1)[0].split("?", 1)[0].rstrip("/")
        if url:
            by_url[url] = event
        key = event_key(str(event.get("event", "")))
        if key and event.get("sport") not in (None, "", "Inne"):
            by_key[key] = event

    out = []
    for row in markets:
        row = dict(row)
        url = str(row.get("event_url", "") or "").split("#", 1)[0].split("?", 1)[0].rstrip("/")
        meta = by_url.get(url) or by_key.get(event_key(str(row.get("event", ""))))
        if meta:
            if row.get("sport") in (None, "", "Inne") and meta.get("sport"):
                row["sport"] = meta.get("sport")
            discovered_name = str(meta.get("event", "") or "").strip()
            current_name = str(row.get("event", "") or "").strip()
            if discovered_name and (
                not current_name
                or " RYNEK " in current_name.upper()
                or len(discovered_name) < len(current_name)
            ):
                row["event"] = discovered_name
        out.append(row)
    return out


def _merge_event_priorities(*groups: list[dict]) -> list[dict]:
    out = []
    seen = set()
    for group in groups:
        for item in group or []:
            url = str(item.get("event_url", "")).split("#")[0]
            if not url or url in seen:
                continue
            seen.add(url)
            out.append(item)
    return out



def _rotate_event_catalog(
    events: list[dict],
    *,
    priority_urls: set[str],
    sequence: int,
    batch_size: int,
) -> tuple[list[dict], int]:
    """Priorities first, then rotate the remaining catalog between scans."""
    priority = []
    normal = []
    seen = set()

    for event in events:
        url = str(event.get("event_url", "") or "").split("#")[0]
        if not url or url in seen:
            continue
        seen.add(url)
        (priority if url in priority_urls else normal).append(event)

    if not normal:
        return priority, 0

    offset = ((max(1, int(sequence)) - 1) * max(1, int(batch_size))) % len(normal)
    return priority + normal[offset:] + normal[:offset], offset



KNOWN_COMPARISON_BOOKS = [
    "Superbet", "STS", "Fortuna", "Betclic", "Forbet", "LVBet", "ETOTO",
    "Betfan", "Fuksiarz", "TotalBet", "Betters", "LeBull", "AdmiralBet",
    "BetSport", "ComeOn", "PZBuk",
]


def find_confirmation_targets_from_values(values: list[dict], dobrybuk_rows: list[dict]) -> list[dict]:
    index = {}
    for row in dobrybuk_rows:
        key = (event_key(row.get("event", "")), market_key(row.get("market", "")))
        if row.get("event_url"):
            index[key] = row

    targets = []
    seen = set()
    for value in values:
        key = (event_key(value.get("event", "")), market_key(value.get("market", "")))
        row = index.get(key)
        if not row:
            continue
        target_key = (row.get("event_url", ""), row.get("market", ""))
        if target_key in seen:
            continue
        seen.add(target_key)
        targets.append(
            {
                "event": row.get("event", value.get("event", "")),
                "sport": row.get("sport", value.get("sport", "")),
                "market": row.get("market", value.get("market", "")),
                "event_url": row.get("event_url", ""),
            }
        )
    return targets


def build_coverage(markets: list[dict], direct_stats: dict, discovered_events: int, scanned_events: int) -> dict:
    per_book: dict[str, dict] = {
        book: {"events": set(), "markets": set(), "offers": 0, "direct_status": "not-configured"}
        for book in KNOWN_COMPARISON_BOOKS
    }

    for market in markets:
        ekey = event_key(str(market.get("event", "")))
        mkey = market_key(str(market.get("market", "")))
        for _, quotes in (market.get("quotes") or {}).items():
            for quote in quotes:
                book = str(quote.get("bookmaker", "")).strip()
                if not book:
                    continue
                canonical = {
                    "eFortuna": "Fortuna",
                    "eToto": "ETOTO",
                    "Etoto": "ETOTO",
                    "BETFAN": "Betfan",
                    "Betsport": "BetSport",
                    "Total Bet": "TotalBet",
                    "Totalbet": "TotalBet",
                }.get(book, book)
                if canonical not in per_book:
                    per_book[canonical] = {
                        "events": set(),
                        "markets": set(),
                        "offers": 0,
                        "direct_status": "unknown",
                    }
                if ekey:
                    per_book[canonical]["events"].add(ekey)
                if ekey and mkey:
                    per_book[canonical]["markets"].add(f"{ekey}|{mkey}")
                per_book[canonical]["offers"] += 1

    direct_sources = (
        direct_stats.get("sources", {})
        if isinstance(direct_stats, dict)
        else {}
    )
    for book, info in per_book.items():
        direct = direct_sources.get(book, {})
        if direct:
            if int(direct.get("markets", 0) or 0) > 0:
                info["direct_status"] = "working"
            elif direct.get("ok"):
                info["direct_status"] = "reachable-no-markets"
            else:
                info["direct_status"] = "blocked-or-failed"

    result = {}
    for book, info in sorted(per_book.items()):
        result[book] = {
            "events": len(info["events"]),
            "markets": len(info["markets"]),
            "offers": int(info["offers"]),
            "direct_status": info["direct_status"],
        }

    completion = (
        round(scanned_events / discovered_events * 100.0, 1)
        if discovered_events
        else 0.0
    )
    return {
        "full_bookmaker_inventory_guaranteed": False,
        "scope": (
            "Kursy i zdarzenia widoczne w aktualnie skanowanym zakresie DobryBuk "
            "+ konserwatywne dane bezpośrednie. To nie jest gwarancja 100% pełnej "
            "oferty każdego bukmachera."
        ),
        "comparison_bookmakers": 16,
        "discovered_events": int(discovered_events),
        "detail_events_scanned": int(scanned_events),
        "detail_completion_pct": completion,
        "books": result,
    }


async def scan_once() -> dict:
    started = time.time()
    provider = DobryBukProvider(settings)
    state = State(ALERT_STATE)
    market_cache = MarketCache(MARKET_CACHE)
    plan = state.next_scan_plan(settings.deep_scan_every)
    force_fast = str(os.getenv("FORCE_FAST_SCAN", "1")).strip().lower() not in {"0", "false", "no"}
    if force_fast:
        plan["mode"] = "fast"
        plan["next_deep_in"] = 0
    scan_mode = "stable-fast" if force_fast else f"adaptive-{plan['mode']}"
    errors: list[str] = []
    watch_targets = state.priority_targets(settings.watch_scan_limit)

    await state.save()
    provider.discovery_sequence = plan["sequence"]
    async def bounded(label, operation, seconds, fallback):
        print(f"ETAP: {label}; limit {seconds}s", flush=True)
        try:
            return await asyncio.wait_for(operation, timeout=seconds)
        except Exception as exc:
            errors.append(f"{label}: {type(exc).__name__}: {exc}")
            return fallback

    # Direct bookmaker pages are lightweight HTTP requests, so run them in parallel
    # with the browser-based comparison scan instead of adding minutes to each cycle.
    direct_task = asyncio.create_task(
        scan_direct_books(
            enabled=bool(getattr(settings, "direct_sources_enabled", True)),
            timeout=float(getattr(settings, "direct_sources_timeout", 12)),
            concurrency=int(getattr(settings, "direct_sources_concurrency", 5)),
        )
    )

    print("ETAP: start przeglądarki", flush=True)
    try:
        await asyncio.wait_for(provider.start(), timeout=30)
    except BaseException:
        direct_task.cancel()
        try:
            await asyncio.wait_for(provider.stop(), timeout=8)
        except Exception:
            pass
        raise
    # v29: direct bookmaker browser fallback runs on EVERY cycle. v28 accidentally
    # disabled it whenever FORCE_FAST_SCAN=1, which is exactly how GitHub Actions is
    # configured. That made Betclic/Fortuna/STS effectively unreachable as fallbacks.
    browser_direct_task = None
    try:
        browser_direct_task = asyncio.create_task(
            scan_direct_books_browser(
                provider.context,
                enabled=bool(getattr(settings, "direct_sources_enabled", True)),
                max_seconds=int(getattr(settings, "direct_browser_seconds", 75)),
                concurrency=int(getattr(settings, "direct_browser_concurrency", 4)),
            )
        )
    except Exception as exc:
        errors.append(f"Direct browser init: {type(exc).__name__}: {exc}")

    try:
        # Discovery jobs run in parallel:
        # - DobryBuk value/stat pages -> prioritize likely interesting events,
        # - broad main-listing sweep -> hunt candidate arbs across ALL visible dates.
        priority_task = asyncio.create_task(bounded("Priorytety", provider.discover_priority_events(), 45, ([], [])))
        signal_task = asyncio.create_task(bounded("Sygnały", provider.discover_signal_events(), 45, ([], [])))
        broad_budget = (
            min(120, max(55, int(settings.market_scan_budget_seconds * 0.35)))
            if plan["mode"] == "deep"
            else min(80, max(45, int(settings.fast_scan_budget_seconds * 0.55)))
        )
        broad_task = asyncio.create_task(
            bounded("Szeroki podgląd", provider.scan_broad_listing_markets(max_seconds=broad_budget), broad_budget + 10, ([], [], {}))
        )
        watch_task = None
        if watch_targets:
            watch_task = asyncio.create_task(
                provider.scan_specific_markets(
                    watch_targets,
                    concurrency=settings.confirm_concurrency,
                    max_seconds=settings.watch_scan_seconds,
                )
            )

        events, discover_errors = await bounded("Wykrywanie wydarzeń", provider.discover_events(settings.sports), 65, ([], []))
        errors.extend(discover_errors)

        try:
            priority_events, priority_errors = await priority_task
        except Exception as exc:
            priority_events, priority_errors = [], [f"priority: {exc}"]
        errors.extend([f"Priority: {x}" for x in priority_errors])

        try:
            signal_events, signal_errors = await signal_task
        except Exception as exc:
            signal_events, signal_errors = [], [f"signals: {exc}"]
        errors.extend([f"Signals: {x}" for x in signal_errors])

        # Preserve accurate names/sports from normal discovery, while putting:
        # persistent near-arbs -> market movements -> value/stat pages -> normal events.
        normal_by_url = {
            e.get("event_url", "").split("#")[0]: e
            for e in events
            if e.get("event_url")
        }
        watch_events = []
        for w in watch_targets:
            url = str(w.get("event_url", "")).split("#")[0]
            watch_events.append(normal_by_url.get(url, w))

        prioritized = _merge_event_priorities(
            watch_events,
            signal_events,
            priority_events,
            events,
        )
        events = [normal_by_url.get(str(e.get("event_url", "")).split("#")[0], e) for e in prioritized]

        priority_urls = {
            str(e.get("event_url", "") or "").split("#")[0]
            for e in (watch_events + signal_events + priority_events)
            if e.get("event_url")
        }
        planned_batch = (
            settings.market_scan_max_events
            if plan["mode"] == "deep"
            else settings.fast_scan_max_events
        )
        events_for_scan, rotation_offset = _rotate_event_catalog(
            events,
            priority_urls=priority_urls,
            sequence=plan["sequence"],
            batch_size=planned_batch,
        )

        dobrybuk_rows = []
        market_errors = []
        market_stats = {
            "detail_events_scanned": 0,
            "detail_events_total": len(events),
            "exhaustive_complete": False,
        }

        if events:
            detail_max_events = (
                settings.market_scan_max_events
                if plan["mode"] == "deep"
                else settings.fast_scan_max_events
            )
            detail_budget = (
                settings.market_scan_budget_seconds
                if plan["mode"] == "deep"
                else settings.fast_scan_budget_seconds
            )
            dobrybuk_rows, market_errors, market_stats = await provider.scan_all_markets(
                events_for_scan,
                max_events=detail_max_events,
                max_seconds=detail_budget,
                concurrency=settings.market_scan_concurrency,
            )
            errors.extend([f"Markety: {x}" for x in market_errors])

        if not dobrybuk_rows:
            scan_mode += "+fallback"
            fallback_rows, fallback_errors = await bounded("Fallback tabeli", provider.scan_listing_fallback(
                list(getattr(provider, "discovered_sports", []) or settings.sports)
            ), 25, ([], []))
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

        watch_rows = []
        if watch_task is not None:
            try:
                watch_rows, watch_errors = await watch_task
                errors.extend([f"Watch: {x}" for x in watch_errors])
            except Exception as exc:
                errors.append(f"Watch: {type(exc).__name__}: {exc}")

        try:
            broad_rows, broad_errors, broad_stats = await broad_task
        except Exception as exc:
            broad_rows, broad_errors, broad_stats = [], [f"broad: {exc}"], {
                "broad_listing_pairs": 0,
                "broad_listing_markets": 0,
                "broad_listing_elapsed": 0,
            }
        errors.extend([f"Broad: {x}" for x in broad_errors])

        try:
            direct_rows, direct_errors, direct_stats = await direct_task
        except Exception as exc:
            direct_rows, direct_errors, direct_stats = [], [f"direct: {exc}"], {"enabled": True, "sources": {}}
        errors.extend([f"Direct: {x}" for x in direct_errors])

        browser_direct_rows = []
        browser_direct_stats = {"enabled": False, "sources": {}, "markets": 0}
        if browser_direct_task is not None:
            try:
                browser_direct_rows, browser_direct_errors, browser_direct_stats = await browser_direct_task
                errors.extend([f"Direct browser: {x}" for x in browser_direct_errors])
            except Exception as exc:
                errors.append(f"Direct browser: {type(exc).__name__}: {exc}")

        all_direct_rows = direct_rows + browser_direct_rows
        merged_rows = merge_markets(
            watch_rows + dobrybuk_rows + broad_rows + all_direct_rows
        )
        merged_rows = _enrich_market_metadata(merged_rows, events)

        static_fallback_rows = []
        if not merged_rows:
            static_fallback_rows, static_fallback_errors = await bounded("Publiczny HTML", provider.scan_static_http_fallback(), 22, ([], []))
            errors.extend([f"Static fallback: {x}" for x in static_fallback_errors])
            if static_fallback_rows:
                merged_rows = merge_markets(static_fallback_rows)
                scan_mode += "+static-http"

        # Rolling cache prevents FAST/DEEP rotation from making the UI look as if
        # hundreds of markets suddenly disappeared. Opportunity math still uses
        # only quotes younger than MAX_QUOTE_AGE_SECONDS.
        try:
            market_cache.update(merged_rows)
            market_cache.prune(keep_seconds=6 * 3600)
            analysis_rows = market_cache.snapshot(settings.max_quote_age_seconds)
            display_rows = market_cache.snapshot(2 * 3600)
        except Exception as exc:
            errors.append(f"Market cache fallback: {type(exc).__name__}: {exc}")
            analysis_rows = merged_rows
            display_rows = merged_rows

        if not analysis_rows:
            static_rows, static_errors = await bounded("Publiczny HTML", provider.scan_static_http_fallback(), 22, ([], []))
            errors.extend([f"Static recovery: {x}" for x in static_errors])
            if static_rows:
                analysis_rows = merge_markets(static_rows)
                display_rows = analysis_rows
                merged_rows = analysis_rows
                scan_mode += "+recovered"
            else:
                # Don't destroy the site because one provider cycle was empty.
                # Use recent rolling cache for display, but do NOT create surebet/value
                # candidates from old quotes.
                stale_display = market_cache.snapshot(7 * 24 * 3600)
                if stale_display:
                    display_rows = stale_display
                    analysis_rows = []
                    errors.append(
                        "Brak świeżych kursów: opublikowano wyłącznie stary podgląd; "
                        "surebet/value wyłączone dla tego cyklu."
                    )
                else:
                    # v29: one blocked comparison source must never crash the whole run.
                    # Publish an honest no-data status; scan_runtime will preserve the last
                    # successful opportunities (clearly marked stale in the UI) if present.
                    display_rows = []
                    analysis_rows = []
                    scan_mode += "+no-fresh-data"
                    errors.append(
                        "Żadne źródło nie zwróciło świeżych kursów w tym cyklu. "
                        "Nie nadpisuję ostatniego poprawnego wyniku pustymi danymi."
                    )

        candidates = detect_from_markets(analysis_rows) if analysis_rows else []
        value_candidates = (
            detect_valuebets(
                analysis_rows,
                payout_factors(),
                min_edge_pct=settings.value_min_edge_pct,
                min_reference_books=settings.value_min_reference_books,
                max_dispersion=settings.value_max_dispersion,
                max_price_gap=settings.value_max_price_gap,
                min_odds=settings.value_min_odds,
                max_odds=settings.value_max_odds,
                max_age_seconds=settings.max_quote_age_seconds,
            )
            if settings.value_bets_enabled
            else []
        )
        # Radar uses the longer display cache so it does not collapse to zero when a
        # single fast cycle sees only a small slice of the catalogue. Older entries and
        # one-book markets are labelled explicitly by detect_near_arbs and are never
        # promoted to confirmed surebets.
        radar_rows = display_rows or analysis_rows
        near_arbs = detect_near_arbs(
            radar_rows,
            payout_factors(),
            max_gap_pct=settings.near_arb_gap_pct,
            fallback_gap_pct=max(35.0, settings.near_arb_gap_pct),
            min_results=24,
            max_age_seconds=2 * 3600,
            fresh_age_seconds=settings.max_quote_age_seconds,
        ) if radar_rows else []

        confirmed = []
        confirmed_values = []
        if candidates or value_candidates:
            await asyncio.sleep(max(0.5, min(2.0, float(settings.recheck_delay_seconds))))
            targets = _find_dobrybuk_confirmation_targets(candidates, analysis_rows)
            value_targets = find_confirmation_targets_from_values(
                value_candidates, analysis_rows
            )
            target_map = {
                (x.get("event_url", ""), x.get("market", "")): x
                for x in (targets + value_targets)
                if x.get("event_url")
            }

            confirm_rows = []
            if target_map:
                confirm_rows, confirm_errors = await bounded("Potwierdzenie kursów", provider.scan_specific_markets(
                    list(target_map.values()),
                    concurrency=settings.confirm_concurrency,
                    max_seconds=25,
                ), 30, ([], []))
                errors.extend([f"Potwierdzenie: {x}" for x in confirm_errors])

            # Re-fetch direct pages too so no alert is based solely on stale direct data.
            direct_confirm_rows, direct_confirm_errors, _ = await scan_direct_books(
                enabled=bool(getattr(settings, "direct_sources_enabled", True)),
                timeout=float(getattr(settings, "direct_sources_timeout", 12)),
                concurrency=int(getattr(settings, "direct_sources_concurrency", 5)),
            )
            errors.extend([f"Potwierdzenie direct HTTP: {x}" for x in direct_confirm_errors])

            # v29: candidates found on rendered Betclic/Fortuna/STS pages must also be
            # confirmable. v28 confirmed direct candidates only with plain HTTP, so a
            # browser-only quote could never become a surebet alert.
            direct_confirm_browser_rows = []
            try:
                direct_confirm_browser_rows, direct_confirm_browser_errors, _ = await scan_direct_books_browser(
                    provider.context,
                    enabled=bool(getattr(settings, "direct_sources_enabled", True)),
                    max_seconds=int(getattr(settings, "direct_confirm_browser_seconds", 35)),
                    concurrency=int(getattr(settings, "direct_browser_concurrency", 4)),
                )
                errors.extend([f"Potwierdzenie direct browser: {x}" for x in direct_confirm_browser_errors])
            except Exception as exc:
                errors.append(f"Potwierdzenie direct browser: {type(exc).__name__}: {exc}")

            confirmation_merged = merge_markets(
                confirm_rows + direct_confirm_rows + direct_confirm_browser_rows
            )

            confirmed = detect_from_markets(confirmation_merged)
            confirmed_values = (
                detect_valuebets(
                    confirmation_merged,
                    payout_factors(),
                    min_edge_pct=settings.value_min_edge_pct,
                    min_reference_books=settings.value_min_reference_books,
                    max_dispersion=settings.value_max_dispersion,
                    max_price_gap=settings.value_max_price_gap,
                    min_odds=settings.value_min_odds,
                    max_odds=settings.value_max_odds,
                    max_age_seconds=settings.max_quote_age_seconds,
                )
                if settings.value_bets_enabled
                else []
            )

            # If a market is already a strict surebet, show it as surebet rather than value bet.
            arb_markets = {
                (event_key(x.event), market_key(x.market))
                for x in confirmed
            }
            confirmed_values = [
                x for x in confirmed_values
                if (event_key(x.get("event", "")), market_key(x.get("market", "")))
                not in arb_markets
            ]

        confirmed_values = state.decorate_values(
            confirmed_values,
            required_scans=settings.value_stability_scans,
            elite_edge_pct=settings.value_elite_edge_pct,
        )
        stable_values = [v for v in confirmed_values if v.get("push_ready")]
        near_arbs = state.update_watchlist(near_arbs, confirmed_values)

        alerts_sent = 0
        push_alerts_sent = 0
        value_push_alerts_sent = 0
        telegram_alerts_sent = 0
        push_configured = bool(settings.onesignal_app_id and settings.onesignal_api_key)
        telegram_configured = bool(settings.telegram_token and settings.telegram_chat_id)

        alert_deadline = time.monotonic() + 20
        for arb in confirmed:
            if time.monotonic() >= alert_deadline:
                errors.append("Alerty: limit czasu powiadomień; pozostałe okazje wrócą przy następnym skanie.")
                break
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
                    result = await asyncio.wait_for(send_push(
                        settings.onesignal_app_id,
                        settings.onesignal_api_key,
                        arb,
                        settings.app_public_url,
                    ), timeout=max(0.1, min(8, alert_deadline - time.monotonic())))
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
                    await asyncio.wait_for(send(
                        settings.telegram_token,
                        settings.telegram_chat_id,
                        arb,
                    ), timeout=max(0.1, min(8, alert_deadline - time.monotonic())))
                    telegram_alerts_sent += 1
                    delivered = True
                except Exception as exc:
                    errors.append(f"Telegram: {exc}")

            if delivered:
                alerts_sent += 1

        # Value bets are intentionally push-only and clearly separated from surebets.
        # They are NOT guaranteed wins; they are high-confidence consensus mispricings.
        if push_configured:
            for value in stable_values:
                if time.monotonic() >= alert_deadline:
                    errors.append("Alerty value: budżet powiadomień wyczerpany.")
                    break
                should_send_value = await state.should_alert(
                    "value|" + str(value.get("key", "")),
                    float(value.get("edge_pct", 0) or 0),
                    settings.value_alert_cooldown_minutes,
                    reappear_minutes=15,
                    improvement_pct=0.75,
                )
                if not should_send_value:
                    continue
                try:
                    result = await asyncio.wait_for(send_value_push(
                        settings.onesignal_app_id,
                        settings.onesignal_api_key,
                        value,
                        settings.app_public_url,
                    ), timeout=max(0.1, min(8, alert_deadline - time.monotonic())))
                    value_push_alerts_sent += 1
                    if isinstance(result, dict) and result.get("errors"):
                        errors.append(
                            f"OneSignal value odpowiedź: {result.get('errors')}"
                        )
                except Exception as exc:
                    errors.append(f"OneSignal value: {exc}")

        now = time.time()
        try:
            quality = scan_quality(analysis_rows)
        except Exception as exc:
            errors.append(f"Quality fresh: {type(exc).__name__}: {exc}")
            quality = {}
        try:
            current_quality = scan_quality(merged_rows)
        except Exception as exc:
            errors.append(f"Quality current: {type(exc).__name__}: {exc}")
            current_quality = {}
        try:
            display_quality = scan_quality(display_rows)
        except Exception as exc:
            errors.append(f"Quality display: {type(exc).__name__}: {exc}")
            display_quality = {}

        direct_source_summary = {}
        http_sources = direct_stats.get("sources", {}) if isinstance(direct_stats, dict) else {}
        browser_sources = browser_direct_stats.get("sources", {}) if isinstance(browser_direct_stats, dict) else {}
        for name in set(http_sources) | set(browser_sources):
            http_info = http_sources.get(name, {})
            browser_info = browser_sources.get(name, {})
            direct_source_summary[name] = {
                "markets": int(http_info.get("markets", 0) or 0)
                + int(browser_info.get("markets", 0) or 0),
                "http_markets": int(http_info.get("markets", 0) or 0),
                "browser_markets": int(browser_info.get("markets", 0) or 0),
                "ok": bool(http_info.get("ok") or browser_info.get("ok")),
                "mode": "http + public-browser",
            }

        merged_direct_stats = {
            "enabled": True,
            "sources": direct_source_summary,
            "markets": len(all_direct_rows),
        }

        source_health = state.update_source_health(
            merged_direct_stats,
            dobrybuk_ok=bool(dobrybuk_rows or broad_rows),
        )
        coverage = build_coverage(
            analysis_rows,
            merged_direct_stats,
            len(events),
            int(market_stats.get("detail_events_scanned", 0) or 0),
        )
        sources = {
            "DobryBuk": {
                "markets": len(dobrybuk_rows),
                "broad_candidate_markets": len(broad_rows),
                "events": len({
                    (event_key(str(r.get("event", ""))), str(r.get("sport", "")).lower())
                    for r in merged_rows
                }),
                "mode": "detail + all-date candidate sweep",
            },
            **direct_source_summary,
        }
        try:
            coupon_catalog = build_coupon_catalog(
                display_rows,
                int(getattr(settings, "coupon_catalog_limit", 1600)),
            )
        except Exception as exc:
            errors.append(f"Coupon catalog: {type(exc).__name__}: {exc}")
            coupon_catalog = []

        try:
            scan_preview = build_scan_preview(display_rows, 1200)
        except Exception as exc:
            errors.append(f"Scan preview: {type(exc).__name__}: {exc}")
            scan_preview = []

        fresh_data = bool(merged_rows) and bool(analysis_rows)
        payload = {
            "generated_at": now,
            "last_scan": now if fresh_data else read_json(DOCS_DATA / "latest.json").get("last_scan"),
            "last_attempt": now,
            "data_fresh": fresh_data,
            "data_status": "fresh" if fresh_data else "degraded-cache",
            "latest": [arb.to_dict() for arb in confirmed[:200]],
            "valuebets": stable_values[:150],
            "near_arbs": near_arbs[:120],
            "scan_preview": scan_preview,
            "coupon_catalog": coupon_catalog,
            "stats": {
                "events": len(events),
                "sports_scanned": len(getattr(provider, "discovered_sports", []) or []),
                "sports": list(getattr(provider, "discovered_sports", []) or []),
                "detail_events_scanned": market_stats.get("detail_events_scanned", 0),
                "detail_events_total": market_stats.get("detail_events_total", len(events)),
                "markets": len(display_rows),
                "markets_scanned": len(merged_rows),
                "markets_scanned_current": len(merged_rows),
                "active_markets_5m": len(analysis_rows),
                "active_markets_2h": len(display_rows),
                "active_events_2h": display_quality.get("events", 0),
                "dobrybuk_markets": len(dobrybuk_rows),
                "direct_markets": len(all_direct_rows),
                "direct_http_markets": len(direct_rows),
                "direct_browser_markets": len(browser_direct_rows),
                "broad_candidate_markets": len(broad_rows),
                "broad_listing_pairs": broad_stats.get("broad_listing_pairs", 0),
                "priority_events": len(priority_events),
                "signal_events": len(signal_events),
                "watch_targets": len(watch_targets),
                "watch_rows": len(watch_rows),
                "catalog_events": len(events),
                "rotation_offset": rotation_offset,
                "near_arbs": len(near_arbs),
                "exhaustive_complete": market_stats.get("exhaustive_complete", False),
                "candidates": len(candidates),
                "surebets": len(confirmed),
                "value_candidates": len(value_candidates),
                "value_confirmed": len(confirmed_values),
                "valuebets": len(stable_values),
                "alerts_sent": alerts_sent,
                "push_alerts_sent": push_alerts_sent,
                "value_push_alerts_sent": value_push_alerts_sent,
                "telegram_alerts_sent": telegram_alerts_sent,
                "push_configured": push_configured,
                "elapsed_seconds": round(time.time() - started, 2),
                "scanner": "multi-source-v30-sane-arbs-radar",
                "scan_mode": scan_mode,
                "scan_sequence": plan["sequence"],
                "deep_every": plan["deep_every"],
                "next_deep_in": plan["next_deep_in"],
                "quality": quality,
                "current_quality": current_quality,
                "display_quality_2h": display_quality,
                "sources": sources,
            },
            "coverage": coverage,
            "intelligence": {
                "scan_plan": plan,
                "quality": quality,
                "current_quality": current_quality,
                "display_quality_2h": display_quality,
                "source_health": source_health,
                "watchlist_size": len(state.watchlist),
                "stable_valuebets": len(stable_values),
                "confirmed_value_candidates": len(confirmed_values),
                "near_arb_limit_pct": settings.near_arb_gap_pct,
            },
            "errors": errors[-100:],
            "source": "multi-source: comparison + direct public bookmaker pages",
            "coupon_catalog_info": {
                "items": len(coupon_catalog),
                "mode": "bookmaker-first",
            },
            "market_scan_note": (
                "Skan adaptacyjny: szybkie cykle śledzą watchlistę, ruchy kursów i szeroki all-date sweep, "
                "a katalog/radar korzysta z rolling cache do 2 godzin (starsze pozycje są oznaczone). "
                "Arbitraże są liczone wyłącznie z kompletnych, wzajemnie wykluczających się rynków "
                "bez push/half-win i ponownie potwierdzane przed alertem. Value bet wymaga co najmniej "
                f"{settings.value_min_reference_books} innych kompletnych bukmacherów, "
                f"edge >= {settings.value_min_edge_pct:.1f}% po uwzględnieniu współczynnika wypłaty "
                "oraz niskiej rozbieżności konsensusu. Pokrycie nie oznacza 100% pełnej oferty "
                "każdego bukmachera."
            ),
        }

        await state.save()
        try:
            market_cache.save()
        except Exception as exc:
            errors.append(f"Market cache save: {type(exc).__name__}: {exc}")

        DOCS_DATA.mkdir(parents=True, exist_ok=True)
        atomic_json(DOCS_DATA / "latest.json", payload)

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
        if browser_direct_task is not None and not browser_direct_task.done():
            browser_direct_task.cancel()
        try:
            await asyncio.wait_for(provider.stop(), timeout=8)
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(scan_once())
