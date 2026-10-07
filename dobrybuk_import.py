from __future__ import annotations

"""Manual DobryBuk snapshot importer.

This tool NEVER downloads DobryBuk and does not bypass access controls.
It only parses HTML files that the user manually saved from a page they opened in a browser.

Usage:
    python dobrybuk_import.py imports
    python dobrybuk_import.py path/to/page.html --sport "Piłka nożna" --market "1X2"

The generated payload is compatible with the existing web UI and is written to
``docs/data/latest.json`` by default.
"""

import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from bs4 import BeautifulSoup

from app.intelligence import detect_near_arbs, scan_quality
from app.merge import merge_markets
from app.models import Quote
from app.providers.dobrybuk import (
    BOOKS,
    ALIASES,
    clean,
    clean_event_name,
    extract_listing_market,
    extract_listing_tables,
    normalize_label,
    odds_from_text,
)
from app.surebet import detect

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "docs" / "data" / "latest.json"
DOBRYBUK_URL = "https://dobrybuk.pl/kursy"

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
    "Traf": 0.88,
    "WettArena": 0.88,
}

BOOK_HOME = {
    "Betclic": "https://www.betclic.pl/",
    "Fortuna": "https://www.efortuna.pl/",
    "STS": "https://www.sts.pl/",
    "Superbet": "https://superbet.pl/",
    "Betfan": "https://betfan.pl/",
    "Forbet": "https://www.iforbet.pl/",
    "LVBet": "https://lvbet.pl/",
    "ETOTO": "https://www.etoto.pl/",
    "Fuksiarz": "https://fuksiarz.pl/",
    "TotalBet": "https://totalbet.pl/",
    "Betters": "https://betters.pl/",
    "LeBull": "https://lebull.pl/",
    "AdmiralBet": "https://admiralbet.pl/",
    "BetSport": "https://betsport.pl/",
    "ComeOn": "https://comeon.pl/",
    "PZBuk": "https://www.pzbuk.pl/",
    "Traf": "https://trafonline.pl/",
    "WettArena": "https://wettarena.pl/",
}

BLOCK_MARKERS = (
    "sorry, you have been blocked",
    "you are unable to access dobrybuk.pl",
    "attention required! | cloudflare",
    "access denied",
)

SPORT_BY_FILENAME = {
    "pilka-nozna": "Piłka nożna",
    "piłka-nożna": "Piłka nożna",
    "football": "Piłka nożna",
    "tenis": "Tenis",
    "tennis": "Tenis",
    "koszykowka": "Koszykówka",
    "koszykówka": "Koszykówka",
    "basketball": "Koszykówka",
    "siatkowka": "Siatkówka",
    "siatkówka": "Siatkówka",
    "volleyball": "Siatkówka",
    "hokej": "Hokej",
    "hockey": "Hokej",
    "reczna": "Piłka ręczna",
    "ręczna": "Piłka ręczna",
    "handball": "Piłka ręczna",
    "mma": "MMA",
    "boks": "Boks",
    "boxing": "Boks",
    "dart": "Dart",
    "esport": "Esport",
}


def _canonical_book(raw: str) -> str | None:
    text = clean(raw)
    low = text.lower()
    if low in ALIASES:
        return ALIASES[low]
    # Exact / substring matching against known brands.
    for name in sorted(BOOKS, key=len, reverse=True):
        if name.lower() in low:
            return ALIASES.get(name.lower(), name)
    return None


def _infer_sport(path: Path, explicit: str | None) -> str:
    if explicit:
        return explicit
    name = path.stem.lower().replace("_", "-").replace(" ", "-")
    for token, sport in SPORT_BY_FILENAME.items():
        if token in name:
            return sport
    return "Inne"


def _blocked(html: str) -> bool:
    low = html.lower()
    return any(marker in low for marker in BLOCK_MARKERS)


def _nearest_heading(table) -> str:
    node = table
    for _ in range(8):
        node = getattr(node, "previous_sibling", None)
        if node is None:
            break
        try:
            if getattr(node, "name", None) in {"h1", "h2", "h3", "h4", "h5", "strong"}:
                text = clean(node.get_text(" ", strip=True))
                if text:
                    return text
            found = getattr(node, "find", lambda *a, **k: None)(["h1", "h2", "h3", "h4", "h5"])
            if found:
                text = clean(found.get_text(" ", strip=True))
                if text:
                    return text
        except Exception:
            pass
    return ""


def _event_from_page(soup: BeautifulSoup, path: Path) -> str:
    for selector in ("h1", "main h2", "article h2"):
        try:
            node = soup.select_one(selector)
        except Exception:
            node = None
        if node:
            text = clean_event_name(node.get_text(" ", strip=True))
            if len(text) >= 4:
                return text
    if soup.title:
        title = clean(soup.title.get_text(" ", strip=True))
        title = re.sub(r"\s*[|–—-]\s*DobryBuk.*$", "", title, flags=re.I)
        title = clean_event_name(title)
        if len(title) >= 4:
            return title
    return clean_event_name(path.stem.replace("_", " ").replace("-", " ")) or "Wydarzenie DobryBuk"


def extract_detail_tables_generic(html: str, path: Path, sport: str, source_url: str) -> list[dict]:
    """Parse saved event detail pages without knowing the route/market in advance."""
    soup = BeautifulSoup(html, "html.parser")
    now = time.time()
    event = _event_from_page(soup, path)
    out: list[dict] = []

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        header = []
        header_idx = -1
        for idx, row in enumerate(rows[:12]):
            cells = [normalize_label(x.get_text(" ", strip=True)) for x in row.find_all(["th", "td"])]
            if len(cells) >= 3 and cells[0].strip().lower() in {"bukmacher", "bookmaker"}:
                header = cells
                header_idx = idx
                break
        if not header:
            continue
        labels = [x for x in header[1:] if x]
        if len(labels) < 2:
            continue

        heading = _nearest_heading(table)
        low_labels = {x.lower() for x in labels}
        if {"1", "x", "2"}.issubset(low_labels):
            market = "1X2"
        elif len(labels) == 2 and low_labels <= {"1", "2"}:
            market = "Winner"
        else:
            market = heading or "Rynek DobryBuk"

        quotes: dict[str, list[dict]] = defaultdict(list)
        for row in rows[header_idx + 1 :]:
            cells = row.find_all(["td", "th"])
            if len(cells) < 3:
                continue
            first = cells[0]
            candidates = [clean(img.get("alt", "")) for img in first.find_all("img")]
            candidates.append(clean(first.get_text(" ", strip=True)))
            bookmaker = next((_canonical_book(x) for x in candidates if _canonical_book(x)), None)
            if not bookmaker:
                continue
            book_url = BOOK_HOME.get(bookmaker, "")
            for idx, cell in enumerate(cells[1:]):
                if idx >= len(labels):
                    break
                vals = odds_from_text(cell.get_text(" ", strip=True))
                if not vals:
                    continue
                odds = max(vals)
                # A conservative ceiling blocks UI counters accidentally parsed as odds.
                if odds > 80:
                    continue
                selection = normalize_label(labels[idx])
                if not selection:
                    continue
                quotes[selection].append({
                    "selection": selection,
                    "odds": odds,
                    "bookmaker": bookmaker,
                    "observed_at": now,
                    "source_url": source_url,
                    "bookmaker_url": book_url,
                    "source_name": "DobryBuk manual snapshot",
                    "link_exact": False,
                })

        if len(quotes) >= 2:
            out.append({
                "event": event,
                "sport": sport,
                "market": market,
                "quotes": dict(quotes),
                "observed_at": now,
                "source_url": source_url,
                "event_url": source_url,
                "source_name": "DobryBuk manual snapshot",
                "source_names": ["DobryBuk manual snapshot"],
            })
    return out


def parse_one(path: Path, *, sport: str | None, market: str, source_url: str) -> tuple[list[dict], list[str]]:
    errors: list[str] = []
    try:
        html = path.read_text("utf-8", errors="replace")
    except Exception as exc:
        return [], [f"{path.name}: nie udało się odczytać pliku: {exc}"]
    if not html.strip():
        return [], [f"{path.name}: pusty plik"]
    if _blocked(html):
        return [], [f"{path.name}: zapisano stronę blokady Cloudflare zamiast kursów"]

    inferred_sport = _infer_sport(path, sport)
    rows: list[dict] = []

    # General listing parsers from the project.
    try:
        rows.extend(extract_listing_market(html, inferred_sport, market, source_url))
    except Exception as exc:
        errors.append(f"{path.name}: parser listy szerokiej: {type(exc).__name__}: {exc}")
    try:
        rows.extend(extract_listing_tables(html, inferred_sport, source_url))
    except Exception as exc:
        errors.append(f"{path.name}: parser listy 1X2: {type(exc).__name__}: {exc}")
    try:
        rows.extend(extract_detail_tables_generic(html, path, inferred_sport, source_url))
    except Exception as exc:
        errors.append(f"{path.name}: parser tabel szczegółowych: {type(exc).__name__}: {exc}")

    for row in rows:
        row["source_name"] = "DobryBuk manual snapshot"
        row["source_names"] = ["DobryBuk manual snapshot"]
        row["source_url"] = row.get("source_url") or source_url
        row["event_url"] = row.get("event_url") or source_url
        for items in (row.get("quotes") or {}).values():
            for q in items:
                q["source_name"] = "DobryBuk manual snapshot"
                q["source_url"] = q.get("source_url") or source_url
                q["bookmaker_url"] = q.get("bookmaker_url") or BOOK_HOME.get(str(q.get("bookmaker", "")), "")
                q["link_exact"] = False
    return rows, errors


def _event_to_quotes(row: dict) -> dict[str, list[Quote]]:
    result: dict[str, list[Quote]] = {}
    for selection, items in (row.get("quotes") or {}).items():
        for item in items:
            try:
                odds = float(item.get("odds", 0) or 0)
                observed = float(item.get("observed_at", row.get("observed_at", time.time())) or time.time())
            except (TypeError, ValueError):
                continue
            bookmaker = clean(str(item.get("bookmaker", "")))
            if not bookmaker or odds <= 1.0 or odds > 80:
                continue
            result.setdefault(selection, []).append(Quote(
                selection=str(item.get("selection", selection)),
                odds=odds,
                bookmaker=bookmaker,
                observed_at=observed,
                source_url=str(item.get("source_url", row.get("source_url", DOBRYBUK_URL))),
                bookmaker_url=str(item.get("bookmaker_url", BOOK_HOME.get(bookmaker, ""))),
                source_name="DobryBuk manual snapshot",
                link_exact=False,
            ))
    return result


def find_surebets(markets: list[dict], bankroll: float, min_profit: float) -> list[dict]:
    found = []
    for row in markets:
        event = clean(str(row.get("event", "")))
        market = clean(str(row.get("market", "")))
        if not event or not market:
            continue
        try:
            arbs = detect(
                event,
                str(row.get("sport", "Inne") or "Inne"),
                market,
                _event_to_quotes(row),
                bankroll,
                DEFAULT_FACTORS,
                min_profit_pct=min_profit,
                max_age=7200,
            )
        except Exception:
            continue
        for arb in arbs:
            d = arb.to_dict()
            d["source"] = "DobryBuk — ręczny snapshot"
            d["confidence"] = "manual_snapshot"
            d["event_url"] = row.get("event_url") or DOBRYBUK_URL
            found.append(d)

    # Stable dedupe.
    best = {}
    for arb in found:
        key = (
            str(arb.get("event", "")).lower(),
            str(arb.get("market", "")).lower(),
            tuple(sorted((str(x.get("selection", "")).lower(), str(x.get("bookmaker", "")).lower()) for x in arb.get("legs", []))),
        )
        if key not in best or float(arb.get("profit_pct", 0)) > float(best[key].get("profit_pct", 0)):
            best[key] = arb
    return sorted(best.values(), key=lambda x: float(x.get("profit_pct", 0)), reverse=True)


def build_preview(markets: list[dict], limit: int = 900) -> list[dict]:
    out = []
    for idx, row in enumerate(markets[:limit]):
        best = []
        for selection, offers in (row.get("quotes") or {}).items():
            clean_offers = []
            for q in offers:
                try:
                    odds = float(q.get("odds", 0) or 0)
                except (TypeError, ValueError):
                    continue
                if odds <= 1 or odds > 80 or not q.get("bookmaker"):
                    continue
                clean_offers.append(q)
            clean_offers.sort(key=lambda q: float(q.get("odds", 0) or 0), reverse=True)
            if not clean_offers:
                continue
            top = dict(clean_offers[0])
            top["selection"] = selection
            top["alternatives"] = [dict(x) for x in clean_offers[1:6]]
            best.append(top)
        if len(best) >= 2:
            out.append({
                "id": f"db-{idx}",
                "event": row.get("event", ""),
                "sport": row.get("sport", "Inne"),
                "market": row.get("market", "Rynek"),
                "event_url": row.get("event_url") or DOBRYBUK_URL,
                "source_url": row.get("source_url") or DOBRYBUK_URL,
                "best": best,
                "sources": ["DobryBuk manual snapshot"],
                "observed_at": row.get("observed_at", time.time()),
            })
    return out


def build_catalog(markets: list[dict], limit: int = 1400) -> list[dict]:
    out = []
    for idx, row in enumerate(markets[:limit]):
        selections = []
        for selection, offers in (row.get("quotes") or {}).items():
            valid = []
            for q in offers:
                try:
                    odds = float(q.get("odds", 0) or 0)
                except (TypeError, ValueError):
                    continue
                if odds <= 1 or odds > 80:
                    continue
                book = str(q.get("bookmaker", ""))
                if not book:
                    continue
                valid.append({
                    "bookmaker": book,
                    "odds": odds,
                    "bookmaker_url": q.get("bookmaker_url") or BOOK_HOME.get(book, ""),
                    "source_url": q.get("source_url") or DOBRYBUK_URL,
                    "source_name": "DobryBuk manual snapshot",
                })
            valid.sort(key=lambda x: x["odds"], reverse=True)
            if valid:
                selections.append({
                    "selection": selection,
                    "best_odds": valid[0]["odds"],
                    "best_bookmaker": valid[0]["bookmaker"],
                    "offers": valid,
                })
        if selections:
            out.append({
                "id": f"db-cat-{idx}",
                "event": row.get("event", ""),
                "sport": row.get("sport", "Inne"),
                "market": row.get("market", "Rynek"),
                "event_url": row.get("event_url") or DOBRYBUK_URL,
                "sources": ["DobryBuk manual snapshot"],
                "selections": selections,
            })
    return out


def coverage(markets: list[dict]) -> dict:
    per_book = Counter()
    per_book_events: dict[str, set[str]] = defaultdict(set)
    for row in markets:
        event = str(row.get("event", ""))
        seen_here = set()
        for offers in (row.get("quotes") or {}).values():
            for q in offers:
                book = str(q.get("bookmaker", ""))
                if book:
                    per_book[book] += 1
                    seen_here.add(book)
        for book in seen_here:
            per_book_events[book].add(event)
    return {
        book: {
            "markets": sum(1 for row in markets if any(book == str(q.get("bookmaker", "")) for offers in (row.get("quotes") or {}).values() for q in offers)),
            "events": len(per_book_events[book]),
            "quotes": per_book[book],
            "source": "DobryBuk manual snapshot",
        }
        for book in sorted(per_book)
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Import ręcznie zapisanego HTML z DobryBuk do ARBI.")
    parser.add_argument("input", nargs="?", default="imports", help="Plik HTML albo katalog z HTML")
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT), help="Plik wynikowy latest.json")
    parser.add_argument("--sport", default=None, help="Sport, np. 'Piłka nożna'")
    parser.add_argument("--market", default="1X2", help="Rynek listingu, domyślnie 1X2")
    parser.add_argument("--source-url", default=DOBRYBUK_URL)
    parser.add_argument("--bankroll", type=float, default=50.0)
    parser.add_argument("--min-profit", type=float, default=0.0)
    args = parser.parse_args()

    input_path = Path(args.input)
    if input_path.is_dir():
        files = sorted([*input_path.glob("*.html"), *input_path.glob("*.htm")])
    else:
        files = [input_path]
    files = [p for p in files if p.exists() and p.is_file()]
    if not files:
        print("Brak plików HTML do importu.", file=sys.stderr)
        return 2

    all_rows: list[dict] = []
    errors: list[str] = []
    for path in files:
        rows, errs = parse_one(path, sport=args.sport, market=args.market, source_url=args.source_url)
        all_rows.extend(rows)
        errors.extend(errs)
        print(f"{path.name}: {len(rows)} rozpoznanych rynków")

    merged = merge_markets(all_rows)
    now = time.time()
    surebets = find_surebets(merged, max(1.0, args.bankroll), max(0.0, args.min_profit))
    try:
        radar = detect_near_arbs(
            merged,
            DEFAULT_FACTORS,
            max_gap_pct=1.5,
            fallback_gap_pct=35.0,
            min_results=120,
            max_age_seconds=7200,
            fresh_age_seconds=7200,
        )
    except Exception as exc:
        radar = []
        errors.append(f"Radar: {type(exc).__name__}: {exc}")

    try:
        quality = scan_quality(merged)
    except Exception:
        quality = {}

    events = {str(x.get("event", "")).strip().lower() for x in merged if x.get("event")}
    sports = sorted({str(x.get("sport", "Inne")) for x in merged if x.get("sport")})
    payload = {
        "generated_at": now,
        "last_scan": now,
        "last_attempt": now,
        "data_fresh": bool(merged),
        "data_status": "manual-dobrybuk-snapshot" if merged else "no-data",
        "latest": surebets[:200],
        "valuebets": [],
        "near_arbs": radar[:160],
        "scan_preview": build_preview(merged),
        "coupon_catalog": build_catalog(merged),
        "stats": {
            "events": len(events),
            "sports_scanned": len(sports),
            "sports": sports,
            "markets": len(merged),
            "markets_scanned": len(merged),
            "markets_scanned_current": len(merged),
            "active_markets_2h": len(merged),
            "active_events_2h": len(events),
            "dobrybuk_markets": len(merged),
            "direct_markets": 0,
            "surebets": len(surebets),
            "near_arbs": len(radar),
            "exhaustive_complete": True,
            "scanner": "dobrybuk-manual-v33",
            "scan_mode": "MANUAL SNAPSHOT",
            "quality": quality,
            "sources": {
                "DobryBuk": {
                    "markets": len(merged),
                    "events": len(events),
                    "mode": "ręcznie zapisany snapshot HTML",
                }
            },
        },
        "coverage": coverage(merged),
        "intelligence": {
            "quality": quality,
            "source_health": {
                "DobryBuk": {
                    "ok": bool(merged),
                    "message": "Dane z ręcznie zapisanego HTML" if merged else "Brak rozpoznanych danych",
                }
            },
            "near_arb_limit_pct": 1.5,
        },
        "errors": errors[-100:],
        "source": "DobryBuk — ręczny import HTML",
        "runtime": {
            "version": 33,
            "state": "ok" if merged else "no_data",
            "message": (
                f"Zaimportowano ręczny snapshot DobryBuk: {len(events)} zdarzeń / {len(merged)} rynków."
                if merged else
                "Nie rozpoznano kursów w zapisanych plikach DobryBuk."
            ),
            "attempt_finished_at": now,
        },
        "coupon_catalog_info": {"items": len(build_catalog(merged)), "mode": "DobryBuk manual"},
        "market_scan_note": (
            "Źródłem danych jest wyłącznie ręcznie zapisany snapshot DobryBuk. "
            "Importer nie pobiera strony automatycznie i nie omija zabezpieczeń. "
            "Przed postawieniem zakładu zawsze sprawdź kurs i zasady bezpośrednio u bukmachera."
        ),
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nOK: zapisano {out}")
    print(f"Zdarzenia: {len(events)} | rynki: {len(merged)} | surebety: {len(surebets)} | radar: {len(radar)}")
    if errors:
        print("Uwagi:")
        for err in errors[-12:]:
            print(" -", err)
    return 0 if merged else 3


if __name__ == "__main__":
    raise SystemExit(main())
