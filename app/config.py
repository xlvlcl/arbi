from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    source_url: str = os.getenv("SOURCE_URL", "https://dobrybuk.pl/kursy")
    bankroll: float = float(os.getenv("BANKROLL_PLN", "50"))
    min_profit_pct: float = float(os.getenv("MIN_PROFIT_PCT", "0.35"))
    max_events: int = int(os.getenv("MAX_EVENTS", "150"))
    concurrency: int = int(os.getenv("SCAN_CONCURRENCY", "12"))
    request_timeout: float = float(os.getenv("REQUEST_TIMEOUT", "18"))
    max_markets_per_event: int = int(os.getenv("MAX_MARKETS_PER_EVENT", "40"))
    telegram_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    dedupe_minutes: int = int(os.getenv("DEDUPE_MINUTES", "30"))
    loop_seconds: int = int(os.getenv("LOOP_SECONDS", "300"))


settings = Settings()
