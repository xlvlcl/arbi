from __future__ import annotations

import json
import time
from pathlib import Path


class AlertState:
    def __init__(self, path: Path):
        self.path = path
        self.sent: dict[str, dict] = {}
        self.load()

    def load(self) -> None:
        try:
            self.sent = json.loads(self.path.read_text("utf-8")).get("sent", {})
        except Exception:
            self.sent = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"sent": self.sent}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def should_alert(self, key: str, profit_pct: float, minutes: int) -> bool:
        now = time.time()
        old = self.sent.get(key)
        if not old or now - float(old.get("at", 0)) > minutes * 60:
            self.sent[key] = {"at": now, "profit": profit_pct}
            self.save()
            return True
        return False
