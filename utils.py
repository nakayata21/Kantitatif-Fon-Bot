
import requests
import pandas as pd
from typing import List

def send_telegram_message(token: str, chat_id: str, message: str) -> bool:
    """Telegram'a mesaj gönderir. Başarılıysa True döner."""
    if not token or not chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        resp = requests.post(url, json=payload, timeout=10)
        return resp.status_code == 200
    except Exception:
        return False

def uniq(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out

def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))

def _safe_get(s: pd.Series, key: str, default: object = None):
    try:
        val = s[key]
        return val if pd.notna(val) else default
    except (KeyError, TypeError):
        return default
        