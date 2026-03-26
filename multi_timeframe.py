"""
multi_timeframe.py

Çoklu Zaman Dilimi Onay Sistemi:
  1H + 4H + 1D grafikleri aynı yönde hizalanmadıkça
  "YÜKSEK GÜVEN" sinyali üretilmez.
"""

import pandas as pd
import numpy as np
from typing import Optional

try:
    from tvDatafeed import TvDatafeed, Interval
    _TV = TvDatafeed()
except Exception:
    _TV = None


_MTF_CACHE = {}      # {(symbol, exchange): {"h1":df, "h4":df, "d1":df, "ts": datetime}}
import datetime as _dt
_MTF_TTL_MINUTES = 30


def _get_tv(symbol: str, exchange: str, interval, n_bars: int) -> Optional[pd.DataFrame]:
    if _TV is None:
        return None
    try:
        data = _TV.get_hist(symbol=symbol, exchange=exchange, interval=interval, n_bars=n_bars)
        if data is not None and not data.empty:
            data = data.rename(columns={"open": "Open", "high": "High",
                                        "low": "Low", "close": "Close", "volume": "Volume"})
        return data
    except Exception:
        return None


def _ema(series, span):
    return series.ewm(span=span, adjust=False).mean()


def _analyze_tf(df: Optional[pd.DataFrame]) -> dict:
    """Tek bir zaman dilimine ait trend yönünü analiz eder."""
    if df is None or df.empty or len(df) < 50:
        return {"trend": "NÖTR", "score": 0.0}

    close  = df["Close"].astype(float)
    ema20  = _ema(close, 20).iloc[-1]
    ema50  = _ema(close, 50).iloc[-1]
    price  = float(close.iloc[-1])

    # RSI
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rs    = gain / (loss + 1e-9)
    rsi   = float((100 - 100 / (1 + rs)).iloc[-1])

    bull_signals = sum([
        price > ema20,
        ema20 > ema50,
        rsi > 50,
        rsi > 60,
    ])

    if bull_signals >= 3:
        trend, score = "YUKARI", 1.0
    elif bull_signals <= 1:
        trend, score = "AŞAĞI", -1.0
    else:
        trend, score = "NÖTR", 0.0

    return {"trend": trend, "score": score, "rsi": round(rsi, 1),
            "price": round(price, 2), "ema20": round(ema20, 2), "ema50": round(ema50, 2)}


def get_multi_timeframe_confirmation(symbol: str, exchange: str = "BIST") -> dict:
    """
    3 zaman dilimi (1H, 4H, 1D) analiz eder → bütünleşik onay skoru döner.

    Returns:
        {
          "confirmed":      bool,          # Tüm TF'ler aynı yönde mi?
          "direction":      str,           # "YUKARI" / "AŞAĞI" / "KARIŞIK"
          "score":          float,         # -1 ile +1 arası
          "tf_h1":          dict,
          "tf_h4":          dict,
          "tf_d1":          dict,
          "confidence_add": float,         # scoring.py'ye eklenecek bonus/ceza
        }
    """
    cache_key = (symbol, exchange)
    now       = _dt.datetime.now()
    if cache_key in _MTF_CACHE:
        age = (now - _MTF_CACHE[cache_key]["ts"]).seconds / 60
        if age < _MTF_TTL_MINUTES:
            return _MTF_CACHE[cache_key]["result"]

    if _TV is not None:
        df_h1  = _get_tv(symbol, exchange, Interval.in_1_hour,   200)
        df_h4  = _get_tv(symbol, exchange, Interval.in_4_hour,   200)
        df_d1  = _get_tv(symbol, exchange, Interval.in_daily,    300)
    else:
        df_h1 = df_h4 = df_d1 = None     # TvDatafeed yoksa fallback

    tf_h1 = _analyze_tf(df_h1)
    tf_h4 = _analyze_tf(df_h4)
    tf_d1 = _analyze_tf(df_d1)

    scores    = [tf_h1["score"], tf_h4["score"], tf_d1["score"]]
    avg_score = float(np.mean(scores))

    # Yön kararı
    if avg_score > 0.3:
        direction = "YUKARI"
    elif avg_score < -0.3:
        direction = "AŞAĞI"
    else:
        direction = "KARIŞIK"

    # Onay: 3 TF'den en az 2'si aynı yönde
    up_count   = sum(s > 0   for s in scores)
    down_count = sum(s < 0   for s in scores)
    confirmed  = up_count >= 2 or down_count >= 2

    # Güven bonusu/cezası scoring.py için
    if confirmed and direction == "YUKARI":
        confidence_add = +round(avg_score * 10, 1)      # Max +10 puan
    elif confirmed and direction == "AŞAĞI":
        confidence_add = +round(avg_score * 10, 1)      # Negatif zaten
    else:
        confidence_add = -5.0                            # Karışık → ceza

    result = {
        "confirmed":       confirmed,
        "direction":       direction,
        "score":           round(avg_score, 3),
        "tf_h1":           tf_h1,
        "tf_h4":           tf_h4,
        "tf_d1":           tf_d1,
        "confidence_add":  confidence_add,
    }

    _MTF_CACHE[cache_key] = {"result": result, "ts": now}
    return result


if __name__ == "__main__":
    r = get_multi_timeframe_confirmation("THYAO", "BIST")
    print(r)
