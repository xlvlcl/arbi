from __future__ import annotations

import hashlib
import time

from app.merge import event_key, market_key
from app.surebet import outcome_groups


def _factor(book: str, factors: dict[str, float]) -> float:
    return float(factors.get(book, 0.88))


def _fresh_best(markets_quotes: dict, max_age_seconds: int) -> dict[str, dict]:
    now = time.time()
    out: dict[str, dict] = {}
    for selection, quotes in (markets_quotes or {}).items():
        best = None
        best_effective = 0.0
        for q in quotes:
            book = str(q.get("bookmaker", "")).strip()
            odds = float(q.get("odds", 0) or 0)
            observed = float(q.get("observed_at", 0) or 0)
            if not book or odds <= 1.0:
                continue
            if observed and now - observed > max_age_seconds:
                continue
            # effective value is filled later because factor map is external
            if best is None or odds > float(best.get("odds", 0) or 0):
                best = q
        if best:
            out[str(selection)] = best
    return out


def detect_near_arbs(
    markets: list[dict],
    payout_factors: dict[str, float],
    *,
    max_gap_pct: float = 1.50,
    fallback_gap_pct: float = 35.0,
    min_results: int = 24,
    max_age_seconds: int = 7200,
    fresh_age_seconds: int = 300,
) -> list[dict]:
    """Return useful radar candidates, including clearly-labelled older/one-book markets.

    `near` is reserved for fresh complete markets close to the arb boundary and visible at
    multiple bookmakers. `watch` is a wider fresh band. `history` is a complete market from
    the rolling cache, and `market` means only one bookmaker is currently visible. The last
    two tiers are monitoring aids only; the UI never presents them as ready surebets.
    """
    candidates: list[dict] = []
    now = time.time()

    for market in markets:
        groups = outcome_groups(
            str(market.get("sport", "")),
            str(market.get("market", "")),
            list((market.get("quotes") or {}).keys()),
        )
        if not groups:
            continue

        for group in groups:
            legs = []
            inv_sum = 0.0
            selected_books = set()
            available_books = set()
            complete = True
            observed_times: list[float] = []

            for selection in group:
                choices = []
                for q in (market.get("quotes") or {}).get(selection, []):
                    book = str(q.get("bookmaker", "")).strip()
                    odds = float(q.get("odds", 0) or 0)
                    observed = float(q.get("observed_at", market.get("observed_at", 0)) or 0)
                    if not book or odds <= 1.0:
                        continue
                    age = now - observed if observed else 0
                    if observed and age > max_age_seconds:
                        continue
                    effective = odds * _factor(book, payout_factors)
                    if effective > 1.0:
                        choices.append((effective, q, observed))
                        available_books.add(book)

                if not choices:
                    complete = False
                    break

                effective, best, observed = max(choices, key=lambda x: x[0])
                inv_sum += 1.0 / effective
                selected_books.add(str(best.get("bookmaker", "")))
                if observed:
                    observed_times.append(observed)
                legs.append(
                    {
                        "selection": str(selection),
                        "bookmaker": str(best.get("bookmaker", "")),
                        "odds": round(float(best.get("odds", 0) or 0), 3),
                        "effective_odds": round(effective, 3),
                        "bookmaker_url": best.get("bookmaker_url", "")
                        or best.get("source_url", ""),
                        "source_url": best.get("source_url", ""),
                        "observed_at": observed,
                    }
                )

            if not complete or inv_sum <= 1.0:
                # Actual arbs belong to the surebet view, not the "almost" radar.
                continue

            gap_pct = (inv_sum - 1.0) * 100.0
            if gap_pct > max(fallback_gap_pct, max_gap_pct):
                continue

            event = str(market.get("event", ""))
            sport = str(market.get("sport", ""))
            market_name = str(market.get("market", ""))
            raw_key = "|".join(
                [event_key(event), sport.lower(), market_key(market_name)]
            )
            key = hashlib.sha1(raw_key.encode("utf-8")).hexdigest()[:20]
            source_count = len(set(market.get("source_names") or []))
            available_diversity = len(available_books)
            selected_diversity = len(selected_books)
            quote_age = max(0.0, now - min(observed_times)) if observed_times else 0.0
            is_fresh = quote_age <= max(1, int(fresh_age_seconds))

            if available_diversity < 2:
                tier = "market"
            elif not is_fresh:
                tier = "history"
            else:
                tier = "near" if gap_pct <= max_gap_pct else "watch"

            score = max(
                0.0,
                (fallback_gap_pct - gap_pct) / max(fallback_gap_pct, 0.01),
            ) * 100.0
            score += min(24.0, available_diversity * 3.0)
            score += min(10.0, source_count * 2.0)
            if not is_fresh:
                score *= 0.75
            if available_diversity < 2:
                score *= 0.65

            candidates.append(
                {
                    "key": key,
                    "event": event,
                    "sport": sport,
                    "market": market_name,
                    "event_url": market.get("event_url", ""),
                    "gap_pct": round(gap_pct, 4),
                    "inverse_sum": round(inv_sum, 6),
                    "score": round(score, 2),
                    "bookmakers": available_diversity,
                    "selected_bookmakers": selected_diversity,
                    "sources": market.get("source_names", []),
                    "legs": legs,
                    "radar_tier": tier,
                    "fresh": is_fresh,
                    "quote_age_seconds": round(quote_age, 1),
                }
            )

    unique = {}
    for item in candidates:
        old = unique.get(item["key"])
        if old is None or item["gap_pct"] < old["gap_pct"]:
            unique[item["key"]] = item

    tier_rank = {"near": 0, "watch": 1, "history": 2, "market": 3}
    ordered = sorted(
        unique.values(),
        key=lambda x: (
            tier_rank.get(x.get("radar_tier"), 9),
            x["gap_pct"],
            -x["bookmakers"],
            -x["score"],
        ),
    )
    strict = [x for x in ordered if x["radar_tier"] == "near"]
    if len(strict) >= min_results:
        return strict[:160]
    return ordered[:160]


def scan_quality(markets: list[dict]) -> dict:
    events = set()
    books = set()
    offers = 0
    selections = 0
    source_names = set()

    for market in markets:
        ekey = event_key(str(market.get("event", "")))
        if ekey:
            events.add(ekey)
        source_names.update(str(x) for x in (market.get("source_names") or []))
        for _, quotes in (market.get("quotes") or {}).items():
            if quotes:
                selections += 1
            for q in quotes:
                book = str(q.get("bookmaker", "")).strip()
                if book:
                    books.add(book)
                    offers += 1

    return {
        "events": len(events),
        "markets": len(markets),
        "selections": selections,
        "offers": offers,
        "bookmakers": len(books),
        "sources": len(source_names),
        "offers_per_market": round(offers / max(1, len(markets)), 2),
        "markets_per_event": round(len(markets) / max(1, len(events)), 2),
    }
