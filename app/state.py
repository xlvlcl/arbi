from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path


class State:
    def __init__(self, path: Path):
        self.path = path
        self.lock = asyncio.Lock()
        self.latest = []
        self.errors = []
        self.last_scan = 0
        self.stats = {}
        self.sent: dict[str, dict] = {}
        self.scan_seq = 0
        self.watchlist: dict[str, dict] = {}
        self.value_memory: dict[str, dict] = {}
        self.source_health: dict[str, dict] = {}
        self.load()

    def load(self):
        try:
            payload = json.loads(self.path.read_text("utf-8"))
            self.sent = payload.get("sent", {}) or {}
            self.scan_seq = int(payload.get("scan_seq", 0) or 0)
            self.watchlist = payload.get("watchlist", {}) or {}
            self.value_memory = payload.get("value_memory", {}) or {}
            self.source_health = payload.get("source_health", {}) or {}
        except Exception:
            self.sent = {}
            self.scan_seq = 0
            self.watchlist = {}
            self.value_memory = {}
            self.source_health = {}

    def _payload(self):
        return {
            "sent": self.sent,
            "scan_seq": self.scan_seq,
            "watchlist": self.watchlist,
            "value_memory": self.value_memory,
            "source_health": self.source_health,
        }

    async def save(self):
        async with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self._payload(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def next_scan_plan(self, deep_every: int = 4) -> dict:
        deep_every = max(2, int(deep_every))
        self.scan_seq += 1

        # First scan after a clean state is deep; afterwards deep every N cycles.
        deep = self.scan_seq == 1 or self.scan_seq % deep_every == 0
        next_deep_in = 0 if deep else deep_every - (self.scan_seq % deep_every)
        return {
            "sequence": self.scan_seq,
            "mode": "deep" if deep else "fast",
            "deep_every": deep_every,
            "next_deep_in": next_deep_in,
        }

    def priority_targets(self, limit: int = 45) -> list[dict]:
        now = time.time()
        rows = []
        for key, item in self.watchlist.items():
            if now - float(item.get("last_seen", 0) or 0) > 12 * 3600:
                continue
            if not item.get("event_url") or not item.get("market"):
                continue
            rows.append(
                {
                    "key": key,
                    "score": float(item.get("score", 0) or 0),
                    "gap_pct": float(item.get("gap_pct", 99) or 99),
                    "event": item.get("event", ""),
                    "sport": item.get("sport", ""),
                    "market": item.get("market", ""),
                    "event_url": item.get("event_url", ""),
                }
            )
        rows.sort(key=lambda x: (-x["score"], x["gap_pct"]))
        return rows[: max(1, int(limit))]

    def update_watchlist(self, near_arbs: list[dict], values: list[dict]) -> list[dict]:
        now = time.time()
        seen = set()

        decorated = []
        for near in near_arbs:
            key = str(near.get("key", ""))
            if not key:
                continue
            seen.add(key)
            old = self.watchlist.get(key, {})
            consecutive = int(old.get("consecutive", 0) or 0) + 1
            best_gap = min(
                float(old.get("best_gap_pct", 999) or 999),
                float(near.get("gap_pct", 999) or 999),
            )
            item = {
                "event": near.get("event", ""),
                "sport": near.get("sport", ""),
                "market": near.get("market", ""),
                "event_url": near.get("event_url", ""),
                "gap_pct": float(near.get("gap_pct", 999) or 999),
                "best_gap_pct": best_gap,
                "score": float(near.get("score", 0) or 0) + min(20, consecutive * 2),
                "first_seen": float(old.get("first_seen", now) or now),
                "last_seen": now,
                "consecutive": consecutive,
            }
            self.watchlist[key] = item
            copy = dict(near)
            copy["seen_scans"] = consecutive
            copy["best_gap_pct"] = round(best_gap, 4)
            decorated.append(copy)

        # Value events also deserve fast rechecks, even when they are not near-arbs.
        for value in values:
            raw_key = "value:" + str(value.get("key", ""))
            if not value.get("event_url") or not value.get("market"):
                continue
            old = self.watchlist.get(raw_key, {})
            edge = float(value.get("edge_pct", 0) or 0)
            self.watchlist[raw_key] = {
                "event": value.get("event", ""),
                "sport": value.get("sport", ""),
                "market": value.get("market", ""),
                "event_url": value.get("event_url", ""),
                "gap_pct": 99.0,
                "best_gap_pct": 99.0,
                "score": 50.0 + min(50.0, edge * 3.0),
                "first_seen": float(old.get("first_seen", now) or now),
                "last_seen": now,
                "consecutive": int(old.get("consecutive", 0) or 0) + 1,
            }
            seen.add(raw_key)

        # Decay stale watch entries instead of dropping them immediately.
        pruned = {}
        for key, item in self.watchlist.items():
            age = now - float(item.get("last_seen", 0) or 0)
            if age > 24 * 3600:
                continue
            if key not in seen:
                item = dict(item)
                item["score"] = max(0.0, float(item.get("score", 0) or 0) * 0.80)
                item["consecutive"] = 0
            pruned[key] = item
        self.watchlist = pruned

        return decorated

    def decorate_values(
        self,
        values: list[dict],
        *,
        required_scans: int = 2,
        elite_edge_pct: float = 9.0,
    ) -> list[dict]:
        now = time.time()
        required_scans = max(1, int(required_scans))
        current_keys = set()
        out = []

        for value in values:
            key = str(value.get("key", ""))
            if not key:
                continue
            current_keys.add(key)
            old = self.value_memory.get(key, {})

            last_seq = int(old.get("last_scan_seq", 0) or 0)
            if last_seq == self.scan_seq - 1:
                consecutive = int(old.get("consecutive", 0) or 0) + 1
            elif last_seq == self.scan_seq:
                consecutive = int(old.get("consecutive", 1) or 1)
            else:
                consecutive = 1

            edge = float(value.get("edge_pct", 0) or 0)
            refs = int(value.get("reference_books", 0) or 0)
            dispersion = float(value.get("dispersion_pct", 999) or 999)
            elite = edge >= float(elite_edge_pct) and refs >= 7 and dispersion <= 4.0
            push_ready = consecutive >= required_scans or elite

            memory = {
                "event": value.get("event", ""),
                "market": value.get("market", ""),
                "selection": value.get("selection", ""),
                "bookmaker": value.get("bookmaker", ""),
                "first_seen": float(old.get("first_seen", now) or now),
                "last_seen": now,
                "last_scan_seq": self.scan_seq,
                "consecutive": consecutive,
                "best_edge_pct": max(float(old.get("best_edge_pct", 0) or 0), edge),
            }
            self.value_memory[key] = memory

            item = dict(value)
            item["stability_scans"] = consecutive
            item["elite_signal"] = elite
            item["push_ready"] = push_ready
            item["best_edge_pct"] = round(memory["best_edge_pct"], 3)
            out.append(item)

        self.value_memory = {
            key: item
            for key, item in self.value_memory.items()
            if now - float(item.get("last_seen", 0) or 0) <= 48 * 3600
        }
        return out

    def update_source_health(self, direct_stats: dict, dobrybuk_ok: bool) -> dict:
        now = time.time()
        current = {"DobryBuk": {"ok": bool(dobrybuk_ok), "markets": 1 if dobrybuk_ok else 0}}
        if isinstance(direct_stats, dict):
            for name, stats in (direct_stats.get("sources") or {}).items():
                current[str(name)] = {
                    "ok": bool(stats.get("ok")),
                    "markets": int(stats.get("markets", 0) or 0),
                }

        for source, status in current.items():
            old = self.source_health.get(source, {})
            ok = bool(status.get("ok"))
            markets = int(status.get("markets", 0) or 0)
            self.source_health[source] = {
                "ok": ok,
                "markets": markets,
                "last_checked": now,
                "consecutive_success": (
                    int(old.get("consecutive_success", 0) or 0) + 1 if ok else 0
                ),
                "consecutive_failures": (
                    0 if ok else int(old.get("consecutive_failures", 0) or 0) + 1
                ),
                "last_success": (
                    now if ok else float(old.get("last_success", 0) or 0)
                ),
            }

        return self.source_health

    async def should_alert(
        self,
        key: str,
        profit: float,
        cooldown_minutes: int,
        reappear_minutes: int = 6,
        improvement_pct: float = 0.15,
    ) -> bool:
        now = time.time()
        old = self.sent.get(key)

        if not old:
            self.sent[key] = {
                "alerted_at": now,
                "last_seen": now,
                "alert_profit": float(profit),
                "last_profit": float(profit),
            }
            await self.save()
            return True

        last_seen = float(old.get("last_seen", old.get("at", 0)) or 0)
        alerted_at = float(old.get("alerted_at", old.get("at", 0)) or 0)
        alert_profit = float(old.get("alert_profit", old.get("profit", 0)) or 0)

        reappeared = now - last_seen >= max(1, reappear_minutes) * 60
        improved = float(profit) >= alert_profit + max(0.01, float(improvement_pct))
        cooldown = now - alerted_at >= max(1, cooldown_minutes) * 60
        should = reappeared or improved or cooldown

        old["last_seen"] = now
        old["last_profit"] = float(profit)
        if should:
            old["alerted_at"] = now
            old["alert_profit"] = float(profit)
        self.sent[key] = old
        await self.save()
        return should

    def snapshot(self):
        cutoff = time.time() - 72 * 3600
        self.sent = {
            k: v
            for k, v in self.sent.items()
            if float(v.get("last_seen", v.get("at", 0)) or 0) > cutoff
        }
        return {
            "latest": [a.to_dict() for a in self.latest],
            "last_scan": self.last_scan,
            "errors": self.errors[-10:],
            "stats": self.stats,
            "scan_seq": self.scan_seq,
        }
