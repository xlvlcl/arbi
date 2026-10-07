from __future__ import annotations

import httpx


def _short(value: str, limit: int = 120) -> str:
    value = " ".join(str(value or "").split())
    if len(value) <= limit:
        return value
    return value[: max(1, limit - 1)].rstrip() + "…"


def build_payload(app_id: str, arb, app_url: str) -> dict:
    legs = list(getattr(arb, "legs", []) or [])
    leg_text = " • ".join(
        f"{leg.bookmaker}: {leg.selection} @{leg.odds:.2f}" for leg in legs[:3]
    )
    event = _short(getattr(arb, "event", "Surebet"), 95)
    market = _short(getattr(arb, "market", "Rynek"), 55)
    sport = _short(getattr(arb, "sport", "Sport"), 35)
    content = _short(f"{sport} • {event} • {market} | {leg_text}", 220)

    payload = {
        "app_id": app_id,
        "target_channel": "push",
        "included_segments": ["Subscribed Users"],
        "headings": {
            "en": f"🚨 Surebet +{float(arb.profit_pct):.2f}%",
            "pl": f"🚨 Surebet +{float(arb.profit_pct):.2f}%",
        },
        "contents": {"en": content, "pl": content},
        "url": app_url,
        "data": {
            "type": "surebet",
            "event": str(getattr(arb, "event", "")),
            "sport": str(getattr(arb, "sport", "")),
            "market": str(getattr(arb, "market", "")),
            "profit_pct": round(float(arb.profit_pct), 4),
        },
        "ttl": 300,
        "priority": 10,
    }

    web_buttons = []
    seen = set()
    for leg in legs:
        exact_flag = getattr(leg, "link_exact", None)
        if exact_flag is False:
            continue
        url = getattr(leg, "bookmaker_url", "")
        if not url or url in seen:
            continue
        seen.add(url)
        web_buttons.append(
            {
                "id": f"book-{len(web_buttons)+1}",
                "text": f"Otwórz {leg.bookmaker}",
                "url": url,
            }
        )
        if len(web_buttons) >= 2:
            break
    if web_buttons:
        payload["web_buttons"] = web_buttons

    return payload


async def send_push(app_id: str, api_key: str, arb, app_url: str) -> dict:
    payload = build_payload(app_id, arb, app_url)
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            "https://api.onesignal.com/notifications",
            headers={
                "Authorization": f"Key {api_key}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json=payload,
        )
    if response.status_code >= 400:
        raise RuntimeError(f"OneSignal HTTP {response.status_code}: {response.text[:500]}")
    try:
        return response.json()
    except Exception:
        return {"status_code": response.status_code, "text": response.text[:500]}


def build_value_payload(app_id: str, value: dict, app_url: str) -> dict:
    event = _short(value.get("event", "Value bet"), 95)
    market = _short(value.get("market", "Rynek"), 50)
    selection = _short(value.get("selection", ""), 45)
    bookmaker = _short(value.get("bookmaker", ""), 35)
    odds = float(value.get("odds", 0) or 0)
    edge = float(value.get("edge_pct", 0) or 0)
    risk = float(value.get("outcome_risk_pct", 0) or 0)

    content = _short(
        f"POSTAW: {selection} • {bookmaker} @{odds:.2f} | "
        f"{event} • {market} • edge +{edge:.1f}% • ryzyko wyniku {risk:.0f}%",
        220,
    )

    payload = {
        "app_id": app_id,
        "target_channel": "push",
        "included_segments": ["Subscribed Users"],
        "headings": {
            "en": f"💎 Value +{edge:.1f}% • {bookmaker}",
            "pl": f"💎 Value +{edge:.1f}% • {bookmaker}",
        },
        "contents": {"en": content, "pl": content},
        "url": app_url.rstrip("/") + "/#value",
        "data": {
            "type": "valuebet",
            "event": str(value.get("event", "")),
            "sport": str(value.get("sport", "")),
            "market": str(value.get("market", "")),
            "selection": str(value.get("selection", "")),
            "bookmaker": str(value.get("bookmaker", "")),
            "odds": odds,
            "edge_pct": edge,
            "outcome_risk_pct": risk,
        },
        "ttl": 300,
        "priority": 10,
    }

    exact_url = str(value.get("exact_bookmaker_url", "") or "")
    if exact_url:
        payload["web_buttons"] = [
            {"id": "open-book-event", "text": f"Otwórz {bookmaker}", "url": exact_url}
        ]
    return payload


async def send_value_push(app_id: str, api_key: str, value: dict, app_url: str) -> dict:
    payload = build_value_payload(app_id, value, app_url)
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            "https://api.onesignal.com/notifications",
            headers={
                "Authorization": f"Key {api_key}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json=payload,
        )
    if response.status_code >= 400:
        raise RuntimeError(
            f"OneSignal value HTTP {response.status_code}: {response.text[:500]}"
        )
    try:
        return response.json()
    except Exception:
        return {"status_code": response.status_code, "text": response.text[:500]}
