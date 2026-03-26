"""
order_flow.py

Mikroyapı ve Emir Akışı Analizi:
  1. Anomalik Hacim Dedektörü   — Z-score tabanlı olağandışı hacim tespiti
  2. Smart Money İndikatörü     — Fiyat/Hacim uyuşmazlığı (Divergence)
  3. Spread Analizi             — Likidite ölçümü (High-Low proxy spread)
"""

import numpy as np
import pandas as pd


def detect_volume_anomaly(df: pd.DataFrame, window: int = 20) -> dict:
    """
    Güncel hacmin geçmiş 'window' günlük ortalamaya göre Z-skorunu hesaplar.
    Z > 2.0  → Olağandışı hacim artışı (Potansiyel Smart Money alımı veya satışı)
    Z < -1.0 → Hacim kuruması (Dikkat, likidite azalıyor)
    """
    if df is None or "Volume" not in df.columns or len(df) < window + 1:
        return {"z_score": 0.0, "signal": "NORMAL", "ratio": 1.0}

    vols = df["Volume"].dropna().astype(float)
    if len(vols) < window + 1:
        return {"z_score": 0.0, "signal": "NORMAL", "ratio": 1.0}

    rolling_mean = vols.rolling(window).mean()
    rolling_std  = vols.rolling(window).std()

    last_vol   = float(vols.iloc[-1])
    last_mean  = float(rolling_mean.iloc[-1])
    last_std   = float(rolling_std.iloc[-1])

    z_score = (last_vol - last_mean) / (last_std + 1e-9)
    ratio   = last_vol / (last_mean + 1e-9)

    if z_score > 2.5:
        signal = "YOK ARTIŞI"       # Olağandışı hacim spike
    elif z_score > 1.5:
        signal = "HACİM ARTIŞI"
    elif z_score < -1.0:
        signal = "HACİM KURUDU"     # Dilek/manipülasyon riski
    else:
        signal = "NORMAL"

    return {
        "z_score":  round(float(z_score), 2),
        "ratio":    round(float(ratio), 2),
        "signal":   signal,
    }


def smart_money_indicator(df: pd.DataFrame, window: int = 10) -> float:
    """
    Fiyat yükselirken hacim düşüyorsa → Zayıf Alış (Smart Money çıkıyor) → Negatif
    Fiyat yükselirken hacim artıyorsa → Güçlü Alış (Smart Money giriyor) → Pozitif

    Returns: -1.0 ile +1.0 arası skor
    """
    if df is None or len(df) < window + 1:
        return 0.0

    try:
        closes  = df["Close"].astype(float)
        volumes = df["Volume"].astype(float)

        price_direction  = closes.diff(window).iloc[-1]
        volume_direction = volumes.diff(window).iloc[-1]

        # Her ikisi aynı yönde → Güçlü, Zıt yön → Zayıf/Tehlikeli
        if price_direction > 0 and volume_direction > 0:
            score = min(volume_direction / (volumes.mean() + 1e-9), 1.0)
        elif price_direction > 0 and volume_direction < 0:
            score = -0.5   # Fiyat yükseliyor ama hacim eriyor → Uyarı
        elif price_direction < 0 and volume_direction > 0:
            score = -0.8   # Fiyat düşüyor, hacim yükseliyor → Panik satışı
        else:
            score = 0.1    # Her ikisi de düşüyor → Sessiz düzeltme

        return round(float(max(-1.0, min(1.0, score))), 3)
    except Exception:
        return 0.0


def calculate_spread(df: pd.DataFrame, window: int = 5) -> dict:
    """
    High-Low proxy spread'i ile likiditeyi ölçer.
    Yüksek spread → Düşük likidite → İşlem yapmak maliyetli.

    Returns: {"spread_pct": float, "liquidity": "HIGH"/"MEDIUM"/"LOW"}
    """
    if df is None or "High" not in df.columns or len(df) < 2:
        return {"spread_pct": 0.0, "liquidity": "UNKNOWN"}

    try:
        tail      = df.tail(window)
        hl_spread = (tail["High"] - tail["Low"]) / (tail["Close"] + 1e-9) * 100
        avg_spr   = float(hl_spread.mean())

        if avg_spr < 1.0:
            liquidity = "YÜKSEK"
        elif avg_spr < 3.0:
            liquidity = "ORTA"
        else:
            liquidity = "DÜŞÜK"       # Yüksek spread → Giriş-çıkış maliyetli

        return {"spread_pct": round(avg_spr, 2), "liquidity": liquidity}
    except Exception:
        return {"spread_pct": 0.0, "liquidity": "UNKNOWN"}


def get_order_flow_score(df: pd.DataFrame) -> dict:
    """
    Tüm mikroyapı metriklerini birleştirir → single composite score (-1 to +1).
    """
    vol_data     = detect_volume_anomaly(df)
    smart_m      = smart_money_indicator(df)
    spread_data  = calculate_spread(df)

    # Spread cezası (likidite düşükse ağırlık azalt)
    spread_penalty = {"YÜKSEK": 1.0, "ORTA": 0.8, "DÜŞÜK": 0.5, "UNKNOWN": 0.7}
    liq_factor     = spread_penalty.get(spread_data["liquidity"], 0.7)

    # Hacim Z-skoru bonus
    vol_bonus = 0.0
    if vol_data["signal"] == "YOK ARTIŞI":
        vol_bonus = 0.2 if smart_m > 0 else -0.3   # Büyük hacim — yönüne göre
    elif vol_data["signal"] == "HACİM KURUDU":
        vol_bonus = -0.1

    composite = (smart_m + vol_bonus) * liq_factor
    composite = round(float(max(-1.0, min(1.0, composite))), 3)

    return {
        "volume_z":    vol_data["z_score"],
        "volume_sig":  vol_data["signal"],
        "smart_money": smart_m,
        "spread_pct":  spread_data["spread_pct"],
        "liquidity":   spread_data["liquidity"],
        "composite":   composite,
    }


if __name__ == "__main__":
    import yfinance as yf
    df = yf.download("THYAO.IS", period="60d", interval="1d", progress=False)
    result = get_order_flow_score(df)
    print(result)
