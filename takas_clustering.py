"""
BIST takas (AKD) özelliklerine göre gözetimsiz kümeleme.

- K-Means, Gaussian Mixture, DBSCAN desteklenir.
- "Akıllı para" kümesi: TakasAnalizoru puanına göre en yüksek ortalamalı küme seçilir.
- İleri getiri etiketleme: küme bazlı ortalama getiri (eğitim / rapor için).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

SMART_KEYWORDS = ("CITI", "DEUTSCHE", "YABANCI", "EMEKLILIK", "YATIRIM FON")


def takas_dict_to_features(d: Optional[Dict]) -> Optional[Dict[str, float]]:
    """takas_metrics JSON sözlüğünden sabit boyutlu sayısal özellik vektörü."""

    if not d or not isinstance(d, dict):
        return None

    def _f(*keys: str, default: float = 0.0) -> float:
        for k in keys:
            if k in d and d[k] is not None:
                try:
                    return float(d[k])
                except (TypeError, ValueError):
                    pass
        return default

    al5 = _f("ilk_5_alici_oran")
    sat5 = _f("ilk_5_satici_oran")
    da = _f("diger_alici_orani", "diger_alici_oran")
    ds = _f("diger_satici_orani", "diger_satici_oran")
    i3 = _f("ilk_3_alici_payi")
    fd = _f("fiyat_degisim")
    ft = _f("fiyat_trend")
    fp = _f("guncel_fiyat")
    km = _f("kurumsal_maliyet", "ilk_5_maliyet")
    price_vs_cost = (fp / max(km, 1e-6)) if fp > 0 and km > 0 else 1.0

    smart_n = 0.0
    smart_pay = 0.0
    for kurum in d.get("ana_alicilar") or []:
        if not isinstance(kurum, dict):
            continue
        ad = str(kurum.get("ad", "")).upper()
        if any(k in ad for k in SMART_KEYWORDS):
            smart_n += 1.0
            try:
                smart_pay += float(kurum.get("toplam_takas_payi", 0) or 0)
            except (TypeError, ValueError):
                pass

    return {
        "f_net_kurum": al5 - sat5,
        "f_diger_net": ds - da,
        "f_ilk3": i3,
        "f_fiyat_delta": fd,
        "f_fiyat_trend": ft,
        "f_price_vs_cost": float(np.clip(price_vs_cost, 0.5, 2.0)),
        "f_smart_buyers_n": smart_n,
        "f_smart_pay_sum": smart_pay,
    }


FEATURE_ORDER: Tuple[str, ...] = (
    "f_net_kurum",
    "f_diger_net",
    "f_ilk3",
    "f_fiyat_delta",
    "f_fiyat_trend",
    "f_price_vs_cost",
    "f_smart_buyers_n",
    "f_smart_pay_sum",
)


def build_matrix(
    rows: List[Tuple[str, Optional[Dict], Optional[float]]],
) -> Tuple[pd.DataFrame, List[str]]:
    """
    rows: (symbol, takas_dict or None, takas_analyzer_score or None)
    Dönüş: özellik DataFrame'i (eksik satırlar atılır) ve sembol listesi.
    """
    recs = []
    syms = []
    for sym, td, score in rows:
        feat = takas_dict_to_features(td)
        if feat is None:
            continue
        r = {"symbol": sym, "analyzer_score": float(score) if score is not None else np.nan}
        r.update(feat)
        recs.append(r)
        syms.append(sym)
    if not recs:
        return pd.DataFrame(), []
    return pd.DataFrame(recs), syms


@dataclass
class ClusteringResult:
    labels: np.ndarray
    method: str
    smart_cluster_id: Optional[int]
    n_clusters_effective: int
    noise_count: int
    model_dump: Optional[Dict[str, Any]] = None


def run_clustering(
    X: np.ndarray,
    method: str = "kmeans",
    n_clusters: int = 5,
    random_state: int = 42,
    dbscan_eps: float = 1.2,
    dbscan_min_samples: int = 5,
) -> ClusteringResult:
    from sklearn.cluster import DBSCAN, KMeans
    from sklearn.mixture import GaussianMixture
    from sklearn.preprocessing import StandardScaler

    if len(X) < 3:
        return ClusteringResult(
            labels=np.zeros(len(X), dtype=int),
            method=method,
            smart_cluster_id=0,
            n_clusters_effective=1,
            noise_count=0,
        )

    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    method = (method or "kmeans").lower()
    noise_count = 0

    if method == "dbscan":
        clf = DBSCAN(eps=dbscan_eps, min_samples=min(dbscan_min_samples, max(2, len(X) // 20)))
        labels = clf.fit_predict(Xs)
        noise_count = int((labels == -1).sum())
        uniq = sorted(set(labels.tolist()))
        if -1 in uniq:
            uniq.remove(-1)
        if not uniq:
            labels = np.zeros(len(X), dtype=int)
            n_eff = 1
        else:
            remap = {old: i for i, old in enumerate(sorted(uniq))}
            remapped = np.array([remap.get(int(l), -1) for l in labels], dtype=int)
            if -1 in labels:
                max_c = int(remapped.max()) if remapped.size else -1
                remapped = np.where(labels == -1, max_c + 1, remapped)
            labels = remapped
            n_eff = len(set(labels.tolist()))
    elif method == "gmm":
        k = max(2, min(n_clusters, len(X) - 1))
        gmm = GaussianMixture(n_components=k, random_state=random_state, covariance_type="full")
        labels = gmm.fit_predict(Xs)
        n_eff = k
    else:
        k = max(2, min(n_clusters, len(X) - 1))
        km = KMeans(n_clusters=k, random_state=random_state, n_init=10)
        labels = km.fit_predict(Xs)
        n_eff = k

    return ClusteringResult(
        labels=labels.astype(int),
        method=method,
        smart_cluster_id=None,
        n_clusters_effective=n_eff,
        noise_count=noise_count,
        model_dump={"scaler_mean": scaler.mean_.tolist(), "scaler_scale": scaler.scale_.tolist()},
    )


def pick_smart_money_cluster(labels: np.ndarray, analyzer_scores: np.ndarray, min_cluster_size: int = 3) -> Optional[int]:
    """TakasAnalizoru puanı ortalaması en yüksek küme = akıllı para adayı."""

    if len(labels) == 0:
        return None
    best_c = None
    best_mean = -np.inf
    for c in sorted(set(labels.tolist())):
        mask = labels == c
        if int(mask.sum()) < min_cluster_size:
            continue
        sc = analyzer_scores[mask]
        sc = sc[~np.isnan(sc)]
        if len(sc) == 0:
            m = 0.0
        else:
            m = float(np.mean(sc))
        if m > best_mean:
            best_mean = m
            best_c = int(c)
    return best_c


def load_bist_symbols_takas_rows() -> List[Tuple[str, Optional[Dict], Optional[float]]]:
    """fundamental_data.db içindeki BIST takas_metrics satırlarını okur."""
    import sqlite3

    from constants import DEFAULT_BIST_HISSELER
    from fundamental_db import DB_PATH, init_fund_db
    from takas_analyzer import TakasAnalizoru

    init_fund_db()
    conn = sqlite3.connect(DB_PATH)
    try:
        q = "SELECT symbol, takas_metrics FROM fundamental_metrics WHERE market = 'BIST' OR market IS NULL"
        try:
            df = pd.read_sql_query(q, conn)
        except Exception:
            df = pd.DataFrame()
    finally:
        conn.close()

    rows: List[Tuple[str, Optional[Dict], Optional[float]]] = []
    have = set(df["symbol"].str.upper().tolist()) if not df.empty and "symbol" in df.columns else set()
    for sym in DEFAULT_BIST_HISSELER:
        sym_u = sym.upper()
        tk = None
        if not df.empty and sym_u in have:
            sub = df[df["symbol"].str.upper() == sym_u]
            if not sub.empty:
                raw = sub.iloc[0].get("takas_metrics")
                if raw and isinstance(raw, str):
                    try:
                        tk = json.loads(raw)
                    except json.JSONDecodeError:
                        tk = None
        score = None
        if tk:
            try:
                score = float(TakasAnalizoru(tk).analiz_et().get("takas_puani", 0))
            except Exception:
                score = None
        rows.append((sym_u, tk, score))
    return rows


def run_daily_bist_clustering(
    method: str = "kmeans",
    n_clusters: int = 5,
    run_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Tüm BIST listesi için kümeleme + DB kaydı."""
    from takas_cluster_db import save_cluster_run

    run_date = run_date or date.today().isoformat()
    raw_rows = load_bist_symbols_takas_rows()
    df, _ = build_matrix(raw_rows)
    if df.empty or len(df) < 5:
        logger.warning("Takas kümeleme: yeterli veri yok (%d satır)", len(df))
        return {"ok": False, "error": "Yetersiz takas verisi", "n": len(df)}

    sym_list = df["symbol"].tolist()
    X = df[list(FEATURE_ORDER)].values.astype(float)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    analyzer_scores = df["analyzer_score"].values.astype(float)

    res = run_clustering(X, method=method, n_clusters=n_clusters)
    min_sz = max(2, min(5, len(df) // 40))
    smart_id = pick_smart_money_cluster(res.labels, analyzer_scores, min_cluster_size=min_sz)
    if smart_id is None and len(res.labels):
        clist = sorted(set(res.labels.tolist()))
        best_c, best_m = clist[0], -1e18
        for c in clist:
            mask = res.labels == c
            sc = analyzer_scores[mask]
            sc = sc[~np.isnan(sc)]
            proxy = float(np.mean(X[mask, 0] + X[mask, -1]))  # kurum net + smart pay
            m = float(np.mean(sc)) if len(sc) else proxy
            if m > best_m:
                best_m, best_c = m, c
        smart_id = int(best_c)

    is_smart = [int(res.labels[i] == smart_id) for i in range(len(sym_list))]
    save_cluster_run(
        run_date=run_date,
        method=res.method,
        symbols=sym_list,
        cluster_ids=res.labels.tolist(),
        smart_cluster_id=int(smart_id) if smart_id is not None else -1,
        is_smart_flags=is_smart,
        analyzer_scores=analyzer_scores.tolist(),
        features_by_symbol={sym_list[i]: {k: float(df.iloc[i][k]) for k in FEATURE_ORDER} for i in range(len(sym_list))},
        n_noise=res.noise_count,
    )
    return {
        "ok": True,
        "run_date": run_date,
        "method": res.method,
        "n": len(sym_list),
        "smart_cluster_id": smart_id,
        "noise": res.noise_count,
    }


def compute_cluster_forward_returns(
    run_date: str,
    price_loader,
    horizons: Tuple[int, ...] = (5, 20),
    method: str = "kmeans",
) -> None:
    """
    run_date'teki küme atamaları için ileri getiri (kapanıştan kapanışa).
    price_loader(symbol) -> pd.Series close indexed by date veya None
    """
    from takas_cluster_db import get_run_members, save_cluster_performance

    for h in horizons:
        members = get_run_members(run_date, method)
        if not members:
            continue
        by_c: Dict[int, List[float]] = {}
        for m in members:
            sym = m["symbol"]
            cid = int(m["cluster_id"])
            ser = price_loader(sym)
            if ser is None or len(ser) < h + 1:
                continue
            try:
                # ser son gün = bugün varsayımı; run_date'e göre kesit gerekir — basit: son h farkı
                c = float(ser.iloc[-1])
                p = float(ser.iloc[-1 - h])
                if p <= 0:
                    continue
                r = (c - p) / p * 100.0
                by_c.setdefault(cid, []).append(r)
            except Exception:
                continue
        for cid, rets in by_c.items():
            if not rets:
                continue
            save_cluster_performance(
                run_date=run_date,
                method=method,
                cluster_id=cid,
                horizon_days=h,
                mean_return_pct=float(np.mean(rets)),
                n_symbols=len(rets),
            )
