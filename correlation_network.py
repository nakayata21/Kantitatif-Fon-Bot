"""
correlation_network.py

Hisseler arası gizli ilişki ağını keşfeder:
  1. Sektörel Korelasyon Matrisi  — 60 günlük getiri korelasyonu
  2. Dominant/Lokomotif Tespiti   — Endeks varyanstaki paya göre
  3. Lead-Lag Dedektörü           — "A hissesi B'yi N gün önceden taklit ediyor"
"""

import pandas as pd
import numpy as np
import yfinance as yf
import pickle
import os
from datetime import datetime

CORRELATION_CACHE_PATH = "correlation_network.pkl"
_CACHE_TTL_HOURS = 12


def _load_cache():
    if os.path.exists(CORRELATION_CACHE_PATH):
        try:
            with open(CORRELATION_CACHE_PATH, "rb") as f:
                data = pickle.load(f)
            age_hours = (datetime.now() - data["ts"]).total_seconds() / 3600
            if age_hours < _CACHE_TTL_HOURS:
                return data
        except Exception:
            pass
    return None


def _save_cache(data):
    data["ts"] = datetime.now()
    with open(CORRELATION_CACHE_PATH, "wb") as f:
        pickle.dump(data, f)


def build_correlation_matrix(symbols: list[str], lookback_days: int = 60) -> pd.DataFrame:
    """
    Verilen semboller için günlük getiri korelasyon matrisini hesaplar.
    """
    cache = _load_cache()
    if cache and "corr_matrix" in cache:
        return cache["corr_matrix"]

    tickers = [f"{s}.IS" for s in symbols]
    try:
        raw = yf.download(tickers, period=f"{lookback_days}d", interval="1d",
                          progress=False, auto_adjust=True)["Close"]
    except Exception:
        return pd.DataFrame()

    if raw.empty:
        return pd.DataFrame()

    # Sütun isimlerini sembol ismine döndür
    raw.columns = [c.replace(".IS", "") for c in raw.columns]
    returns     = raw.pct_change().dropna()
    corr        = returns.corr()

    _save_cache({"corr_matrix": corr, "returns": returns})
    return corr


def get_dominant_stocks(symbols: list[str], top_n: int = 5) -> list[dict]:
    """
    Portföy/endeks varyansına en fazla katkı sağlayan (lokomotif) hisseleri döner.
    """
    corr = build_correlation_matrix(symbols)
    if corr.empty:
        return []

    # Her hissenin ortalama mutlak korelasyonu → Piyasa etkisi
    influence = corr.abs().mean().sort_values(ascending=False)
    result    = [
        {"symbol": s, "influence": round(float(influence[s]), 3)}
        for s in influence.head(top_n).index
    ]
    return result


def detect_lead_lag(leader: str, follower: str, max_lag: int = 5) -> dict:
    """
    'leader' hissesinin 'follower' üzerindeki öncü etkisini ölçer.
    Pozitif lag → leader N gün önce hareket ediyor.
    """
    cache = _load_cache()
    rets  = cache.get("returns") if cache else None

    if rets is None or leader not in rets.columns or follower not in rets.columns:
        return {"lag": 0, "corr": 0.0}

    best_lag  = 0
    best_corr = 0.0

    for lag in range(1, max_lag + 1):
        shifted = rets[leader].shift(lag)
        c       = shifted.corr(rets[follower])
        if abs(c) > abs(best_corr):
            best_corr = c
            best_lag  = lag

    return {
        "leader":   leader,
        "follower": follower,
        "lag_days": best_lag,
        "corr":     round(float(best_corr), 3),
        "direction": "AYNI YÖN" if best_corr > 0 else "ZIT YÖN",
    }


def get_leading_signal(symbol: str, dominant_stocks: list[str]) -> float:
    """
    Lokomotif hisselerin mevcut durumunu göz önüne alarak sembol için
    -1 (negatif öncü sinyali) ile +1 (pozitif öncü sinyali) döner.
    """
    signals = []
    for dom in dominant_stocks:
        if dom == symbol:
            continue
        lag_info = detect_lead_lag(dom, symbol)
        if abs(lag_info["corr"]) > 0.3:  # Anlamlı ilişki varsa
            # Yönü de hesaba kat
            direction = 1.0 if lag_info["direction"] == "AYNI YÖN" else -1.0
            signals.append(lag_info["corr"] * direction)

    return round(float(np.mean(signals)) if signals else 0.0, 3)


if __name__ == "__main__":
    from constants import DEFAULT_BIST_30
    dominants = get_dominant_stocks(DEFAULT_BIST_30, top_n=5)
    print("Lokomotif Hisseler:", dominants)
    lag = detect_lead_lag("THYAO", "PGSUS")
    print("Lead-Lag:", lag)
