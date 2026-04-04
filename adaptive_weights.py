"""
adaptive_weights.py

Eğitilmiş AI modelin (ai_model.pkl) öğrendiği özellik önem skorlarını okur
ve scoring.py'de kullanılacak dinamik ağırlıkları türetir.

Bu modül sayesinde model ne öğrendiyse, tarama algoritması da
aynı şekilde öncelik sıralaması yapabilir.
"""

import pickle
import os
import numpy as np
from typing import Dict
try:
    from trainer_service import ShapExplainer
except:
    pass

if 'ShapExplainer' not in globals():
    class ShapExplainer: 
        """Mock class when import fails to prevent Pickle errors."""
        pass

MODEL_PATH = "ai_model.pkl"

# ── Varsayılan (Statik) Ağırlıklar ─────────────────────────────────────────
# Model dosyası bulunamazsa veya okunamazsa bu değerler kullanılır.
DEFAULT_WEIGHTS = {
    "w_trend":    0.30,
    "w_dip":      0.10,
    "w_breakout": 0.20,
    "w_momentum": 0.15,
    "w_sm":       0.10,   # smart money
    "w_wein":     0.15,   # weinstein
    "rsi_weight": 1.0,
    "adx_weight": 1.0,
    "vol_weight": 1.0,
    "mfi_weight": 1.0,
}

# ── Feature → Scoring bileşeni Eşleştirme ──────────────────────────────────
# Model hangi feature'ı önemsiyorsa, o bileşenin ağırlığını artıracağız.
FEATURE_TO_COMPONENT = {
    # Trend bileşeni
    "roc20":          "w_trend",
    "mansfield_rs":   "w_trend",
    "ema20_dist":     "w_trend",
    "score":          "w_trend",
    # Dip bileşeni
    "rsi":            "w_dip",
    "mfi":            "w_dip",
    # Kırılım bileşeni
    "vol_spike":      "w_breakout",
    "kalite":         "w_breakout",
    # Smart Money bileşeni
    "above_vwap":     "w_sm",
    # Weinstein bileşeni (index bağlamı)
    "index_rsi":      "w_wein",
    "index_return_5d":"w_wein",
    # Temel analiz → uzun vade ağırlığı
    "pe_ratio":       "w_trend",
    "pb_ratio":       "w_trend",
    "piotroski_score":"w_trend",
    "isy_score":      "w_trend",
    # ADX → Momentum
    "adx":            "w_momentum",
    "feat_rsi_mom":   "w_momentum",
    "feat_vol_atr":   "w_breakout",
    "feat_trend_strength": "w_trend",
}

_cached_weights: Dict = None   # İçi dolu olduğunda tekrar hesaplanmaz

def _normalize(weights: Dict[str, float]) -> Dict[str, float]:
    """Ana 6 bileşen ağırlığının toplamı 1'e eşit olacak şekilde normalleştirir."""
    keys = ["w_trend", "w_dip", "w_breakout", "w_momentum", "w_sm", "w_wein"]
    total = sum(weights.get(k, 0.0) for k in keys)
    if total <= 0:
        return weights
    for k in keys:
        weights[k] = weights.get(k, 0.0) / total
    return weights

def load_adaptive_weights(force_reload: bool = False) -> Dict[str, float]:
    """
    Eğitilmiş modelin özellik önem değerlerinden dinamik scoring ağırlıkları türetir.

    Parametreler
    ------------
    force_reload : bool
        True ise önbellek devre dışı bırakılır ve model dosyası yeniden okunur.

    Dönüş
    ------
    Dict[str, float]
        scoring.py'de kullanılacak ağırlıklar sözlüğü.
    """
    global _cached_weights
    if _cached_weights is not None and not force_reload:
        return _cached_weights

    if not os.path.exists(MODEL_PATH):
        print("⚠️ [AdaptiveWeights] Model bulunamadı → Varsayılan ağırlıklar kullanılıyor.")
        _cached_weights = DEFAULT_WEIGHTS.copy()
        return _cached_weights

    try:
        with open(MODEL_PATH, "rb") as f:
            exported = pickle.load(f)

        # Model hem eski (pipeline doğrudan) hem yeni (sözlük) format desteği
        if isinstance(exported, dict):
            # Yeni formatta ana model "student" veya "experts" içinde olabilir
            pipeline  = exported.get("pipeline")
            if not pipeline:
                pipeline = exported.get("student")
                if not pipeline and "experts" in exported and exported["experts"]:
                    # Herhangi bir uzman modeli al
                    pipeline = list(exported["experts"].values())[0]
            features  = exported.get("features", [])
            meta      = exported.get("metadata", {})
        else:
            pipeline  = exported
            features  = []
            meta      = {}

        if hasattr(pipeline, 'named_steps'):
            importances = pipeline.named_steps["model"].feature_importances_
        else:
            importances = pipeline.feature_importances_
            
        importance_map = dict(zip(features, importances))

        accuracy = meta.get("best_accuracy", meta.get("cv_accuracy", 0))
        print(f"ℹ️ [AdaptiveWeights] Model yüklendi. Doğruluk: %{accuracy*100:.1f} | {meta.get('trained_at','?')[:10]}")

        # ── Bileşen Katkı Toplamlarını Hesapla ─────────────────────────────
        component_scores: Dict[str, float] = {
            k: DEFAULT_WEIGHTS[k]
            for k in ["w_trend","w_dip","w_breakout","w_momentum","w_sm","w_wein"]
        }

        for feature, comp_key in FEATURE_TO_COMPONENT.items():
            if feature in importance_map and comp_key in component_scores:
                component_scores[comp_key] += importance_map[feature]

        # ── Ağırlık Sınırlamalarını Uygula ──────────────────────────────────
        # Hiçbir bileşen %5'in altına veya %55'in üstüne çıkmasın
        for k in component_scores:
            component_scores[k] = np.clip(component_scores[k], 0.05, 0.55)

        # ── Normalize Et ────────────────────────────────────────────────────
        weights = _normalize(component_scores)

        # ── Bireysel İndikatör Çarpanları ────────────────────────────────────
        weights["rsi_weight"] = 1.0 + importance_map.get("rsi",    0.0) * 3
        weights["adx_weight"] = 1.0 + importance_map.get("adx",    0.0) * 3
        weights["vol_weight"] = 1.0 + importance_map.get("vol_spike",0.0) * 3
        weights["mfi_weight"] = 1.0 + importance_map.get("mfi",    0.0) * 3

        print(f"✅ [AdaptiveWeights] Dinamik ağırlıklar güncellendi:")
        for k, v in weights.items():
            print(f"   {k:20s} → {v:.3f}")

        _cached_weights = weights
        return weights

    except Exception as e:
        print(f"❌ [AdaptiveWeights] Model okunamadı: {e} → Varsayılan ağırlıklar.")
        _cached_weights = DEFAULT_WEIGHTS.copy()
        return _cached_weights


def invalidate_cache():
    """Model yeniden eğitildikten sonra önbelleği temizler."""
    global _cached_weights
    _cached_weights = None
    print("🔄 [AdaptiveWeights] Ağırlık önbelleği sıfırlandı.")
