from __future__ import annotations

import json
import time
from pathlib import Path

from app.merge import event_key, market_key_for_item, selection_key


def _event_identity(row: dict) -> str:
    url = str(row.get("event_url", "") or "").strip()
    if url:
        return url.split("#", 1)[0].split("?", 1)[0].rstrip("/").lower()
    return event_key(str(row.get("event", "")))


def _market_identity(row: dict) -> str:
    return market_key_for_item(row)


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return float(default)


def _quote_time(q: dict, row: dict, now: float) -> float:
    value = _safe_float(q.get("observed_at", row.get("observed_at", 0)), 0.0)
    return value or now


def _source_names(value) -> set[str]:
    if isinstance(value, (list, tuple, set)):
        return {str(x) for x in value if x not in (None, "")}
    if value in (None, ""):
        return set()
    return {str(value)}


class MarketCache:
    """Rolling UI/fresh-data cache across GitHub Action runs.

    Important:
    - newest quote wins, NEVER the highest old quote;
    - old rows may remain for browsing;
    - arbitration/value code can request only very fresh rows.
    """

    def __init__(self, path: Path):
        self.path = path
        self.rows: dict[str, dict] = {}
        self.load()

    def load(self):
        try:
            payload = json.loads(self.path.read_text("utf-8"))
            items = payload.get("rows", []) if isinstance(payload, dict) else []
            self.rows = {}
            for row in items:
                ekey = _event_identity(row)
                mkey = _market_identity(row)
                if ekey and mkey:
                    self.rows[f"{ekey}|{mkey}"] = row
        except Exception:
            self.rows = {}

    def update(self, incoming: list[dict]) -> None:
        now = time.time()

        for row in incoming:
            ekey = _event_identity(row)
            mkey = _market_identity(row)
            if not ekey or not mkey:
                continue

            key = f"{ekey}|{mkey}"
            old = self.rows.get(key, {})
            base = dict(old)

            # Prefer clean/new metadata, but keep older good event URL if needed.
            for field in ("event", "sport", "market", "event_url", "source_url"):
                value = row.get(field)
                if value not in (None, "", "Inne"):
                    base[field] = value

            base["observed_at"] = max(
                _safe_float(old.get("observed_at", 0), 0.0),
                _safe_float(row.get("observed_at", 0), 0.0),
                now,
            )
            base["source_names"] = sorted(
                _source_names(old.get("source_names"))
                | _source_names(row.get("source_names"))
            )

            # selection -> bookmaker -> latest quote
            merged: dict[str, dict[str, dict]] = {}
            labels: dict[str, str] = {}

            for source_row in (old, row):
                for label, quotes in (source_row.get("quotes") or {}).items():
                    skey = selection_key(str(label))
                    labels.setdefault(skey, str(label))
                    merged.setdefault(skey, {})
                    for quote in quotes or []:
                        book = str(quote.get("bookmaker", "")).strip()
                        if not book:
                            continue

                        q = dict(quote)
                        q["observed_at"] = _quote_time(q, source_row, now)
                        previous = merged[skey].get(book)

                        if (
                            previous is None
                            or _safe_float(q.get("observed_at", 0), 0.0)
                            >= _safe_float(previous.get("observed_at", 0), 0.0)
                        ):
                            # Preserve a verified direct deep link even if a newer
                            # comparison quote has no exact bookmaker URL.
                            if previous and not q.get("bookmaker_url"):
                                if "direct" in str(previous.get("source_name", "")).lower():
                                    q["bookmaker_url"] = previous.get("bookmaker_url", "")
                            merged[skey][book] = q

            base["quotes"] = {
                labels.get(skey, skey): sorted(
                    per_book.values(),
                    key=lambda q: _safe_float(q.get("odds", 0), 0.0),
                    reverse=True,
                )
                for skey, per_book in merged.items()
                if per_book
            }
            self.rows[key] = base

    def snapshot(self, max_age_seconds: int) -> list[dict]:
        now = time.time()
        out: list[dict] = []

        for row in self.rows.values():
            filtered = {}
            newest = 0.0

            for label, quotes in (row.get("quotes") or {}).items():
                kept = []
                for quote in quotes or []:
                    observed = _safe_float(
                        quote.get("observed_at", row.get("observed_at", 0)),
                        0.0,
                    )
                    if not observed or now - observed > max_age_seconds:
                        continue
                    kept.append(dict(quote))
                    newest = max(newest, observed)
                if kept:
                    filtered[label] = kept

            if not filtered:
                continue

            item = dict(row)
            item["quotes"] = filtered
            item["observed_at"] = newest or _safe_float(row.get("observed_at", 0), 0.0)
            out.append(item)

        return out

    def prune(self, keep_seconds: int = 21600):
        now = time.time()
        kept = {}
        for key, row in self.rows.items():
            newest = 0.0
            for quotes in (row.get("quotes") or {}).values():
                for quote in quotes or []:
                    newest = max(
                        newest,
                        _safe_float(
                            quote.get("observed_at", row.get("observed_at", 0)),
                            0.0,
                        ),
                    )
            if newest and now - newest <= keep_seconds:
                kept[key] = row
        self.rows = kept

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {"updated_at": time.time(), "rows": list(self.rows.values())},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
