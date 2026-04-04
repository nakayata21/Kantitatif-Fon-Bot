"""
Tek kaynak: OHLCV çekimi + add_indicators + vb/vc hazırlığı.
Streamlit taraması, FastAPI /api/scan ve Telegram bot aynı çekirdeği kullanır
(böylece Mansfield RS ve göstergeler tutarlı kalır).
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

import pandas as pd

logger = logging.getLogger(__name__)

_OHLCV_COLS = ("open", "high", "low", "close", "volume")


def attach_divergence_to_last(
    last: pd.Series,
    base_raw: pd.DataFrame,
    *,
    engine: Any = None,
) -> Dict[str, Any]:
    """
    Boğa uyumsuzluk motorunu çalıştırır; last üzerine has_bullish_div, pos_div, div_msg yazar.
    Streamlit sinyal takibi için tam analyze çıktısını döner.
    """
    from divergence import DivergenceEngine

    empty: Dict[str, Any] = {
        "summary": {"bias": "neutral", "ai_hint": "Güçlü uyumsuzluk yok.", "top_signals": []},
        "signals": [],
    }
    try:
        if base_raw is None or getattr(base_raw, "empty", True):
            last["has_bullish_div"] = False
            last["pos_div"] = False
            last["div_msg"] = ""
            return empty
        if not all(c in base_raw.columns for c in _OHLCV_COLS):
            last["has_bullish_div"] = False
            last["pos_div"] = False
            last["div_msg"] = ""
            return empty
        candles = base_raw[list(_OHLCV_COLS)].dropna().to_dict("records")
        eng = engine if engine is not None else DivergenceEngine()
        div_res = eng.analyze(candles)
        bull = div_res.get("summary", {}).get("bias") == "bullish"
        last["has_bullish_div"] = bool(bull)
        last["pos_div"] = bool(bull)
        last["div_msg"] = str(div_res.get("summary", {}).get("ai_hint", "") or "")
        return div_res
    except Exception:
        logger.debug("attach_divergence_to_last atlandı", exc_info=True)
        last["has_bullish_div"] = False
        last["pos_div"] = False
        last["div_msg"] = ""
        return empty


def prepare_symbol_dataframes(
    tv,
    sym: str,
    tv_exchange: str,
    tf: dict,
    global_index_df: Optional[pd.DataFrame] = None,
    delay_ms: int = 0,
    worker_id: int = 0,
) -> Dict[str, Any]:
    """
    Bir sembol için ana + teyit zaman diliminde veri çeker ve gösterge ekler.

    Returns:
        {"ok": True, "base_raw", "base", "conf", "vb", "vc", "last", "prev", "conf_last"}
        veya {"ok": False, "error": "THYAO: ..."}
    """
    from data_fetcher import fetch_hist, interval_obj
    from indicators import add_indicators

    try:
        if delay_ms > 0:
            time.sleep((delay_ms / 1000.0) + (worker_id * 0.1))

        base_raw = fetch_hist(tv, sym, tv_exchange, interval_obj(tf["base"]), tf["bars"])
        conf_raw = fetch_hist(tv, sym, tv_exchange, interval_obj(tf["confirm"]), tf["confirm_bars"])

        if base_raw is None or getattr(base_raw, "empty", True):
            return {"ok": False, "error": f"{sym}: Ana zaman dilimi veri yok"}
        if conf_raw is None or getattr(conf_raw, "empty", True):
            return {"ok": False, "error": f"{sym}: Teyit zaman dilimi veri yok"}

        base = add_indicators(base_raw, index_df=global_index_df, symbol=sym)
        conf = add_indicators(conf_raw, symbol=sym) # Teyit zaman dilimi için de duygu analizi eklensin (cache'ten gelir)

        vb = base.dropna(subset=["close", "rsi", "adx"])
        vc = conf.dropna(subset=["close", "macd_hist"])
        if vb.empty or vc.empty:
            return {"ok": False, "error": f"{sym}: Gösterge sonrası yeterli bar yok"}

        last = vb.iloc[-1].copy()
        prev = vb.iloc[-2] if len(vb) > 1 else vb.iloc[-1].copy()
        conf_last = vc.iloc[-1]

        return {
            "ok": True,
            "base_raw": base_raw,
            "base": base,
            "conf": conf,
            "vb": vb,
            "vc": vc,
            "last": last,
            "prev": prev,
            "conf_last": conf_last,
        }
    except Exception as e:
        logger.exception("prepare_symbol_dataframes: %s", sym)
        return {"ok": False, "error": f"{sym}: {e}"}
