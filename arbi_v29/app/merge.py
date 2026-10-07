from __future__ import annotations

import re
import unicodedata
from collections import defaultdict


def _ascii(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return value.lower()


def event_key(value: str) -> str:
    value = _ascii(value)
    value = value.replace(" vs ", " ").replace(" v ", " ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    stop = {"fc", "cf", "fk", "sc", "club"}
    tokens = [x for x in value.split() if x not in stop]
    return " ".join(tokens)


def market_key(value: str) -> str:
    value = _ascii(value)
    value = re.sub(r"\s+", " ", value).strip()
    compact = re.sub(r"[^a-z0-9]+", "", value)
    if compact in {"1x2", "mecz", "wynikmeczu", "wynikspotkania"}:
        return "1x2"
    if any(x in value for x in ("winner", "zwyciezca", "kto wygra", "match winner")):
        return "winner"
    return value



DRAWLESS_SPORTS = {
    "tenis", "tenis stolowy", "siatkowka", "mma", "boks", "baseball",
}


def market_key_for_item(item: dict) -> str:
    mkey = market_key(item.get("market", ""))
    sport = _ascii(item.get("sport", "")).strip()
    if sport in DRAWLESS_SPORTS and mkey in {"1x2", "winner"}:
        return "winner"
    return mkey

def selection_key(value: str) -> str:
    value = _ascii(value).strip()
    if value in {"remis", "draw", "x"}:
        return "x"
    if value in {"1", "home", "gospodarz"}:
        return "1"
    if value in {"2", "away", "gosc", "goscIE".lower()}:
        return "2"
    return re.sub(r"\s+", " ", value)


def _quality(item: dict) -> int:
    score = 0
    if item.get("event_url"):
        score += 3
    if item.get("sport") and item.get("sport") != "Inne":
        score += 2
    if "dobrybuk" in str(item.get("source_name", item.get("source_url", ""))).lower():
        score += 1
    score += min(5, sum(len(v) for v in (item.get("quotes") or {}).values()))
    return score


def merge_markets(rows: list[dict]) -> list[dict]:
    """Merge exact-looking same event/market rows from comparison + direct sources.

    Only canonical event+market matches are combined. We intentionally do not fuzzy-match
    unrelated names because false market joins are more dangerous than missing an opportunity.
    """
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    passthrough: list[dict] = []

    for item in rows:
        ekey = event_key(item.get("event", ""))
        mkey = market_key_for_item(item)
        if not ekey or not mkey:
            passthrough.append(item)
            continue
        groups[(ekey, mkey)].append(item)

    merged: list[dict] = []
    for _, items in groups.items():
        base = max(items, key=_quality)
        out = {
            "event": base.get("event", ""),
            "sport": base.get("sport", "Inne"),
            "market": base.get("market", "Rynek"),
            "event_url": base.get("event_url", ""),
            "source_url": base.get("source_url", ""),
            "observed_at": max(float(x.get("observed_at", 0) or 0) for x in items),
            "quotes": {},
            "source_names": sorted({str(x.get("source_name", "DobryBuk")) for x in items}),
        }

        by_sel: dict[str, dict[str, dict]] = defaultdict(dict)
        label_for_key: dict[str, str] = {}
        for item in items:
            if out["sport"] == "Inne" and item.get("sport") not in (None, "", "Inne"):
                out["sport"] = item.get("sport")
            for label, quotes in (item.get("quotes") or {}).items():
                skey = selection_key(label)
                label_for_key.setdefault(skey, label)
                for quote in quotes:
                    bookmaker = str(quote.get("bookmaker", "")).strip()
                    if not bookmaker:
                        continue
                    old = by_sel[skey].get(bookmaker)
                    q = dict(quote)
                    q.setdefault("source_name", item.get("source_name", "DobryBuk"))
                    if old is None or float(q.get("odds", 0)) > float(old.get("odds", 0)):
                        # If the better quote came from the comparison but a direct source already
                        # gave us the exact bookmaker event URL, preserve that deep link.
                        if old and "direct" in str(old.get("source_name", "")).lower():
                            q["bookmaker_url"] = old.get("bookmaker_url", q.get("bookmaker_url", ""))
                        by_sel[skey][bookmaker] = q
                    elif "direct" in str(q.get("source_name", "")).lower():
                        # Keep the higher odds but enrich it with the exact direct event URL.
                        old_link = str(old.get("bookmaker_url", ""))
                        if not old_link or "dobrybuk.pl" in old_link:
                            old["bookmaker_url"] = q.get("bookmaker_url", "")
                            old["direct_url_source"] = q.get("source_name", "")

        for skey, per_book in by_sel.items():
            label = label_for_key.get(skey, skey)
            out["quotes"][label] = sorted(
                per_book.values(),
                key=lambda q: float(q.get("odds", 0)),
                reverse=True,
            )

        merged.append(out)

    merged.extend(passthrough)
    return merged
