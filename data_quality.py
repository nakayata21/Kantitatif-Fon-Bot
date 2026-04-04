"""
Tarama sonrası veri kapsamı ve eksiklik özeti — ürün / müşteri tarafında şeffaflık için.
Teknik + temel veri ayrımı; skorların hangi girdiye dayandığı netleşir.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd


def summarize_scan_coverage(
    df: Optional[pd.DataFrame],
    requested: int,
    err_list: Optional[List[str]],
) -> Dict[str, Any]:
    """
    requested: tarama isteğindeki sembol sayısı.
    df: başarılı satırlar (sembol başına bir satır).
    err_list: prepare_symbol_dataframes / istisna mesajları.
    """
    errs = list(err_list or [])
    n_err = len(errs)
    n_rows = 0 if df is None or df.empty else len(df)

    if requested <= 0:
        requested = max(n_rows + n_err, 1)

    ok_pct = (n_rows / requested) * 100.0

    fund_ok = 0
    fund_missing = 0
    if df is not None and not df.empty:
        if "isy_score" in df.columns:
            s = pd.to_numeric(df["isy_score"], errors="coerce").fillna(0)
            fund_ok = int((s > 0).sum())
            fund_missing = int(len(df) - fund_ok)

    tips: List[str] = []
    if n_err > 0:
        tips.append(
            f"{n_err} sembol için OHLCV veya teyit zaman dilimi alınamadı. "
            "Sembol kodunu, borsayı ve TradingView erişimini kontrol edin."
        )
    if fund_missing > 0 and "isy_score" in (df.columns if df is not None else []):
        tips.append(
            f"{fund_missing} satırda güncel temel analiz (İş Yatırım / önbellek) yok veya sıfır; "
            "kalite ve elit skorları ağırlıklı olarak teknik göstergelere dayanır."
        )
    if ok_pct < 75.0 and requested >= 15:
        tips.append(
            "Başarı oranı düşük: sembol gecikmesini artırın, paralel bağlantıyı azaltın veya listeyi bölün."
        )
    return {
        "requested": requested,
        "rows_ok": n_rows,
        "errors": n_err,
        "ok_pct": round(min(100.0, ok_pct), 1),
        "fund_ok": fund_ok,
        "fund_missing": fund_missing,
        "tips": tips,
        "error_samples": errs[:25],
    }


def error_symbols(err_list: List[str]) -> List[str]:
    """'THYAO: ...' biçiminden sembol adlarını çıkarır."""
    out = []
    for line in err_list or []:
        if not line or ":" not in line:
            continue
        sym = line.split(":", 1)[0].strip().upper()
        if sym and sym not in out:
            out.append(sym)
    return out[:50]
