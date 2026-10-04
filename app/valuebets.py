from __future__ import annotations

import hashlib
import statistics
import time

from app.surebet import outcome_groups


def _factor(bookmaker: str, factors: dict[str, float]) -> float:
    return float(factors.get(bookmaker, 0.88))


def _median(values: list[float]) -> float:
    return float(statistics.median(values)) if values else 0.0


def _mad_ratio(values: list[float]) -> float:
    """Median absolute deviation / median.

    A low value means the reference bookmakers broadly agree on probability.
    """
    if len(values) < 2:
        return 0.0
    med = _median(values)
    if med <= 0:
        return 999.0
    mad = _median([abs(x - med) for x in values])
    return mad / med



def _risk_level(percent: float) -> str:
    if percent <= 40.0:
        return "low"
    if percent <= 65.0:
        return "medium"
    return "high"


def _signal_risk_pct(
    *,
    edge_pct: float,
    reference_books: int,
    dispersion_pct: float,
    price_gap_pct: float,
    odds: float,
) -> float:
    """Heuristic uncertainty of the value signal itself, not loss probability."""
    risk = 34.0
    risk += min(22.0, max(0.0, dispersion_pct) * 3.0)
    risk += min(18.0, max(0.0, price_gap_pct - 2.0) * 0.75)
    risk += min(18.0, max(0.0, odds - 2.0) * 4.0)
    risk -= min(16.0, max(0.0, edge_pct - 5.0) * 1.8)
    risk -= min(14.0, max(0, reference_books - 5) * 3.0)
    return round(min(95.0, max(5.0, risk)), 1)


def _is_exact_direct_quote(quote: dict) -> bool:
    source_name = str(quote.get("source_name", "")).lower()
    url = str(quote.get("bookmaker_url", "") or "").strip()
    return bool(url and "direct" in source_name)

def _fresh_best_quotes(
    market: dict,
    max_age_seconds: int,
) -> dict[str, dict[str, dict]]:
    """selection -> bookmaker -> best fresh quote"""
    now = time.time()
    out: dict[str, dict[str, dict]] = {}

    for selection, quotes in (market.get("quotes") or {}).items():
        per_book: dict[str, dict] = {}
        for quote in quotes:
            book = str(quote.get("bookmaker", "")).strip()
            odds = float(quote.get("odds", 0) or 0)
            observed = float(quote.get("observed_at", market.get("observed_at", 0)) or 0)
            if not book or odds <= 1.0:
                continue
            if observed and now - observed > max_age_seconds:
                continue
            old = per_book.get(book)
            if old is None or odds > float(old.get("odds", 0) or 0):
                per_book[book] = quote
        if per_book:
            out[str(selection)] = per_book

    return out


def detect_valuebets(
    markets: list[dict],
    payout_factors: dict[str, float],
    *,
    min_edge_pct: float = 5.0,
    min_reference_books: int = 5,
    max_dispersion: float = 0.08,
    max_price_gap: float = 0.30,
    min_odds: float = 1.35,
    max_odds: float = 8.0,
    max_age_seconds: int = 300,
) -> list[dict]:
    """Find only high-confidence market-consensus value bets.

    Rules:
    - market must be a known mutually-exclusive and exhaustive outcome set;
    - target quote is compared against de-vigged probabilities from OTHER books;
    - at least `min_reference_books` other complete books must exist;
    - reference probabilities must agree (MAD/median <= max_dispersion);
    - target quote cannot be an absurd isolated outlier vs second-best quote;
    - tax/payout factor is applied to the target bookmaker before EV calculation.

    This does NOT make a value bet guaranteed. It only makes the filter conservative.
    """
    results: list[dict] = []

    for market in markets:
        event = str(market.get("event", "")).strip()
        sport = str(market.get("sport", "")).strip()
        market_name = str(market.get("market", "")).strip()
        by_selection = _fresh_best_quotes(market, max_age_seconds)

        if len(by_selection) < 2:
            continue

        groups = outcome_groups(sport, market_name, list(by_selection))
        if not groups:
            continue

        for group in groups:
            # Build books with a COMPLETE quote set for this market group.
            books = set()
            for selection in group:
                books.update(by_selection.get(selection, {}).keys())

            complete_books = [
                book
                for book in books
                if all(book in by_selection.get(selection, {}) for selection in group)
            ]
            if len(complete_books) < min_reference_books + 1:
                continue

            for selection in group:
                candidates: list[dict] = []

                # Raw same-selection prices, used only for stale/outlier protection.
                all_prices = sorted(
                    [
                        float(by_selection[selection][book]["odds"])
                        for book in complete_books
                        if book in by_selection[selection]
                    ],
                    reverse=True,
                )

                for target_book in complete_books:
                    target = by_selection[selection][target_book]
                    target_odds = float(target.get("odds", 0) or 0)
                    if target_odds < min_odds or target_odds > max_odds:
                        continue

                    refs = [book for book in complete_books if book != target_book]
                    if len(refs) < min_reference_books:
                        continue

                    ref_probs: list[float] = []
                    for ref_book in refs:
                        inverse = []
                        valid = True
                        for outcome in group:
                            q = by_selection.get(outcome, {}).get(ref_book)
                            if not q:
                                valid = False
                                break
                            odd = float(q.get("odds", 0) or 0)
                            if odd <= 1:
                                valid = False
                                break
                            inverse.append((outcome, 1.0 / odd))
                        if not valid:
                            continue
                        overround = sum(x[1] for x in inverse)
                        if overround <= 0:
                            continue
                        selected = next(
                            (inv for out, inv in inverse if out == selection),
                            None,
                        )
                        if selected is not None:
                            ref_probs.append(selected / overround)

                    if len(ref_probs) < min_reference_books:
                        continue

                    fair_prob = _median(ref_probs)
                    dispersion = _mad_ratio(ref_probs)
                    if fair_prob <= 0 or dispersion > max_dispersion:
                        continue

                    # Protect against broken/stale single quotes.
                    other_prices = sorted(
                        [
                            float(by_selection[selection][book]["odds"])
                            for book in complete_books
                            if book != target_book
                        ],
                        reverse=True,
                    )
                    second_reference = other_prices[0] if other_prices else 0.0
                    if second_reference > 0:
                        price_gap = target_odds / second_reference - 1.0
                        if price_gap > max_price_gap:
                            continue
                    else:
                        price_gap = 0.0

                    effective_target_odds = target_odds * _factor(
                        target_book, payout_factors
                    )
                    edge = effective_target_odds * fair_prob - 1.0
                    edge_pct = edge * 100.0
                    if edge_pct + 1e-9 < min_edge_pct:
                        continue

                    fair_odds = 1.0 / fair_prob
                    reference_odds = _median(
                        [
                            float(by_selection[selection][book]["odds"])
                            for book in refs
                        ]
                    )

                    dispersion_pct = dispersion * 100.0
                    price_gap_pct = price_gap * 100.0
                    outcome_risk_pct = max(0.0, min(100.0, (1.0 - fair_prob) * 100.0))
                    signal_risk_pct = _signal_risk_pct(
                        edge_pct=edge_pct,
                        reference_books=len(ref_probs),
                        dispersion_pct=dispersion_pct,
                        price_gap_pct=price_gap_pct,
                        odds=target_odds,
                    )
                    exact_bookmaker_url = (
                        str(target.get("bookmaker_url", "") or "")
                        if _is_exact_direct_quote(target)
                        else ""
                    )

                    candidates.append(
                        {
                            "event": event,
                            "sport": sport,
                            "market": market_name,
                            "selection": selection,
                            "bookmaker": target_book,
                            "odds": round(target_odds, 3),
                            "effective_odds": round(effective_target_odds, 3),
                            "fair_probability": round(fair_prob, 6),
                            "fair_odds": round(fair_odds, 3),
                            "reference_odds": round(reference_odds, 3),
                            "edge_pct": round(edge_pct, 3),
                            "reference_books": len(ref_probs),
                            "dispersion_pct": round(dispersion_pct, 3),
                            "price_gap_pct": round(price_gap_pct, 3),
                            "outcome_risk_pct": round(outcome_risk_pct, 1),
                            "outcome_risk_level": _risk_level(outcome_risk_pct),
                            "signal_risk_pct": signal_risk_pct,
                            "signal_risk_level": _risk_level(signal_risk_pct),
                            "bookmaker_url": target.get("bookmaker_url", "")
                            or target.get("source_url", ""),
                            "exact_bookmaker_url": exact_bookmaker_url,
                            "bookmaker_link_exact": bool(exact_bookmaker_url),
                            "source_name": target.get("source_name", ""),
                            "source_url": target.get("source_url", "")
                            or market.get("event_url", ""),
                            "event_url": market.get("event_url", "")
                            or target.get("source_url", ""),
                            "confidence": "high",
                        }
                    )

                # Only the strongest value offer for one selection is surfaced.
                if candidates:
                    candidates.sort(key=lambda x: x["edge_pct"], reverse=True)
                    best = candidates[0]
                    key_raw = "|".join(
                        [
                            sport.lower(),
                            event.lower(),
                            market_name.lower(),
                            str(selection).lower(),
                            best["bookmaker"].lower(),
                        ]
                    )
                    best["key"] = hashlib.sha1(
                        key_raw.encode("utf-8")
                    ).hexdigest()[:20]
                    results.append(best)

    # Avoid duplicate same event/market/selection after merging sources.
    unique: dict[tuple[str, str, str, str], dict] = {}
    for item in results:
        key = (
            item["sport"].lower(),
            item["event"].lower(),
            item["market"].lower(),
            str(item["selection"]).lower(),
        )
        old = unique.get(key)
        if old is None or item["edge_pct"] > old["edge_pct"]:
            unique[key] = item

    return sorted(unique.values(), key=lambda x: x["edge_pct"], reverse=True)
