from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
SETTINGS = DATA / "settings.json"

DEFAULT = {
    "bankroll": 50.0,
    "min_profit_pct": 0.35,
    "scan_interval_seconds": 300,
    "max_quote_age_seconds": 300,
    "dedupe_minutes": 30,
    "recheck_delay_seconds": 1,
    "sports": [
        "Piłka nożna",
        "Tenis",
        "Koszykówka",
        "Siatkówka",
        "Hokej",
        "Piłka ręczna",
        "MMA",
        "Boks",
        "Dart",
        "Żużel",
        "Baseball",
        "Futbol amerykański",
        "Tenis stołowy",
        "Snooker",
        "Rugby",
        "Futsal",
        "Badminton",
        "Golf",
        "Kolarstwo",
        "Formuła 1",
        "Motorsport",
        "Esport",
        "Biathlon",
        "Narciarstwo",
        "Skoki narciarskie",
        "Hokej na trawie",
        "Piłka wodna",
        "Krykiet",
    ],

    "source_url": "https://dobrybuk.pl/kursy",
    "telegram_token": "",
    "telegram_chat_id": "",
    "bookmaker_payout_factors": {},
    "market_scan_max_events": 250,
    "market_scan_budget_seconds": 330,
    "market_scan_concurrency": 4,
    "max_markets_per_event": 40,
    "confirm_concurrency": 2,
    "direct_sources_enabled": True,
    "direct_sources_timeout": 12,
    "direct_sources_concurrency": 5,
    "coupon_catalog_limit": 1600,
    "host": "0.0.0.0",
    "port": 8080,
    "headless": True,
}

ENV_MAP = {
    "telegram_token": "TELEGRAM_BOT_TOKEN",
    "telegram_chat_id": "TELEGRAM_CHAT_ID",
}


class Settings:
    def __init__(self):
        self.data = dict(DEFAULT)
        self.load_file()
        for key, env in ENV_MAP.items():
            if os.getenv(env):
                self.data[key] = os.getenv(env)

        numeric_env = {
            "bankroll": ("BANKROLL_PLN", float),
            "min_profit_pct": ("MIN_PROFIT_PCT", float),
            "scan_interval_seconds": ("SCAN_INTERVAL_SECONDS", int),
            "max_quote_age_seconds": ("MAX_QUOTE_AGE_SECONDS", int),
            "market_scan_max_events": ("MARKET_SCAN_MAX_EVENTS", int),
            "market_scan_budget_seconds": ("MARKET_SCAN_BUDGET_SECONDS", int),
            "market_scan_concurrency": ("MARKET_SCAN_CONCURRENCY", int),
            "max_markets_per_event": ("MAX_MARKETS_PER_EVENT", int),
            "confirm_concurrency": ("CONFIRM_CONCURRENCY", int),
            "direct_sources_timeout": ("DIRECT_SOURCES_TIMEOUT", int),
            "direct_sources_concurrency": ("DIRECT_SOURCES_CONCURRENCY", int),
            "coupon_catalog_limit": ("COUPON_CATALOG_LIMIT", int),
        }
        for key, (env, caster) in numeric_env.items():
            if os.getenv(env):
                self.data[key] = caster(os.getenv(env))

        self.data["scan_interval_seconds"] = max(60, int(self.data["scan_interval_seconds"]))
        self.data["max_quote_age_seconds"] = max(60, int(self.data["max_quote_age_seconds"]))
        self.data["market_scan_max_events"] = max(1, int(self.data["market_scan_max_events"]))
        self.data["market_scan_budget_seconds"] = max(30, int(self.data["market_scan_budget_seconds"]))
        self.data["market_scan_concurrency"] = min(8, max(1, int(self.data["market_scan_concurrency"])))
        self.data["max_markets_per_event"] = min(80, max(1, int(self.data["max_markets_per_event"])))
        self.data["confirm_concurrency"] = min(4, max(1, int(self.data["confirm_concurrency"])))
        self.data["direct_sources_timeout"] = min(30, max(5, int(self.data["direct_sources_timeout"])))
        self.data["direct_sources_concurrency"] = min(8, max(1, int(self.data["direct_sources_concurrency"])))
        self.data["coupon_catalog_limit"] = min(2500, max(100, int(self.data["coupon_catalog_limit"])))

    def load_file(self):
        if SETTINGS.exists():
            try:
                self.data.update(json.loads(SETTINGS.read_text("utf-8")))
            except Exception:
                pass

    def save(self, updates):
        for key, value in updates.items():
            if key in DEFAULT:
                self.data[key] = value
        SETTINGS.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def __getattr__(self, name):
        if name in self.data:
            return self.data[name]
        raise AttributeError(name)

    def public(self):
        data = dict(self.data)
        token = str(data.get("telegram_token", ""))
        data["telegram_token_configured"] = bool(token)
        data["telegram_token"] = ("***" + token[-4:]) if len(token) > 4 else ("***" if token else "")
        data["telegram_chat_configured"] = bool(data.get("telegram_chat_id"))
        return data


settings = Settings()
