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
        self.load()

    def load(self):
        try:
            payload = json.loads(self.path.read_text("utf-8"))
            self.sent = payload.get("sent", {})
        except Exception:
            self.sent = {}

    async def save(self):
        async with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps({"sent": self.sent}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    async def should_alert(
        self,
        key: str,
        profit: float,
        cooldown_minutes: int,
        reappear_minutes: int = 6,
        improvement_pct: float = 0.15,
    ) -> bool:
        """Wyślij alert, gdy:
        - surebet pojawia się pierwszy raz,
        - wraca po co najmniej kilku minutach nieobecności,
        - zysk poprawił się zauważalnie,
        - albo utrzymuje się bardzo długo i minął cooldown.

        Ten sam identyczny surebet nie spamuje co każde 2 minuty.
        """
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
        }
