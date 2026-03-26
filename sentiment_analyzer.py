"""
sentiment_analyzer.py

1. KAP Bildirimi Analizi  — OpenRouter ile Türkçe NLP
2. Haber Tansiyonu        — Google News RSS üzerinden hisse başlık sayısı
"""

import requests
import json
import os
import hashlib
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional

# --------------------------------------------------------------------------- #
#  KAP DUYGU ANALİZİ                                                           #
# --------------------------------------------------------------------------- #

KAP_RSS    = "https://www.kap.org.tr/tr/bildirim-sorgu"
KAP_CACHE  = {}          # {symbol: {"score": float, "ts": datetime}}
_KAP_TTL   = 6 * 3600    # 6 saat (saniye)


def fetch_kap_disclosures(symbol: str, max_items: int = 5) -> List[str]:
    """
    KAP'tan sembole ait son bildirimlerin başlıklarını döner.
    Rate-limit aşmamak için 6 saatlik önbellek kullanır.
    """
    try:
        url = f"https://www.kap.org.tr/tr/api/memberDisclosureList?stockCode={symbol}"
        r = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return []
        data = r.json()
        titles = [d.get("title", "") for d in data[:max_items]]
        return [t for t in titles if t]
    except Exception:
        return []


def score_kap_with_ai(symbol: str, headlines: List[str]) -> float:
    """
    OpenRouter ile başlıkları analiz eder → [-1, +1] duygu skoru döner.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key or not headlines:
        return 0.0

    prompt = (
        f"{symbol} hissesine ait KAP bildirimleri:\n"
        + "\n".join(f"- {h}" for h in headlines)
        + "\n\nBu bildirimler hisse senedi fiyatı için genel olarak POZİTİF mi, NEGATİF mi yoksa NÖTR mü? "
        "Sadece şu JSON formatında yanıt ver: {\"score\": <-1.0 ile 1.0 arası float>, \"reason\": \"<1 cümle>\"}"
    )

    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "google/gemma-3-27b-it:free",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 100,
            },
            timeout=15,
        )
        content = r.json()["choices"][0]["message"]["content"]
        parsed  = json.loads(content[content.find("{"):content.rfind("}") + 1])
        return float(parsed.get("score", 0.0))
    except Exception:
        return 0.0


def get_kap_sentiment(symbol: str) -> dict:
    """
    Önbellekli KAP duygu skoru sorgular.
    Returns: {"score": float, "cached": bool}
    """
    now = datetime.now()
    if symbol in KAP_CACHE:
        cached = KAP_CACHE[symbol]
        if (now - cached["ts"]).seconds < _KAP_TTL:
            return {"score": cached["score"], "cached": True}

    headlines = fetch_kap_disclosures(symbol)
    score     = score_kap_with_ai(symbol, headlines) if headlines else 0.0
    KAP_CACHE[symbol] = {"score": score, "ts": now}
    return {"score": score, "cached": False, "headlines": headlines}


# --------------------------------------------------------------------------- #
#  HABER TANSİYONU (Google News RSS)                                            #
# --------------------------------------------------------------------------- #

NEWS_CACHE = {}    # {symbol: {"count": int, "ts": datetime}}
_NEWS_TTL  = 3600  # 1 saat


def get_news_volume(symbol: str, days: int = 3) -> int:
    """
    Son N gündeki haber başlık sayısını döner (0 = sessizlik, yüksek = ilgi artışı).
    """
    now = datetime.now()
    if symbol in NEWS_CACHE:
        if (now - NEWS_CACHE[symbol]["ts"]).seconds < _NEWS_TTL:
            return NEWS_CACHE[symbol]["count"]

    try:
        url   = f"https://news.google.com/rss/search?q={symbol}+borsa&hl=tr&gl=TR&ceid=TR:tr"
        r     = requests.get(url, timeout=8)
        count = r.text.count("<item>")
    except Exception:
        count = 0

    NEWS_CACHE[symbol] = {"count": count, "ts": now}
    return count


def get_full_sentiment(symbol: str) -> dict:
    """
    KAP + Haber tansiyonunu birleştirir → systeme entegre edilecek skor.
    Returns: {"kap_score": float, "news_volume": int, "composite": float}
    """
    kap   = get_kap_sentiment(symbol)
    news  = get_news_volume(symbol)

    # Haber tansiyonunu normalleştir: 0-50+ arası → 0-1 arası
    news_norm = min(news / 50.0, 1.0)

    # Composite: KAP skoru ağırlıklı, haber tansiyonu çarpan etkisi
    composite = kap["score"] * (1.0 + news_norm * 0.3)
    composite = max(-1.0, min(1.0, composite))

    return {
        "kap_score":   round(kap["score"], 3),
        "news_volume": news,
        "composite":   round(composite, 3),
    }


if __name__ == "__main__":
    result = get_full_sentiment("THYAO")
    print(result)
