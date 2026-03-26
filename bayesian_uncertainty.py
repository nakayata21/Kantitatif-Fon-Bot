"""
bayesian_uncertainty.py

Bayesian Belirsizlik Ölçümü — "Bilmediğini Bilen Model"

Klasik modeller tek bir nokta tahmini verir (%72 gibi).
Bu modül ise tahminin ne kadar güvenilir olduğunu da söyler:
  - Epistemic Uncertainty (Veri Eksikliği Belirsizliği): Model bu durumu daha önce hiç görmedi mi?
  - Aleatoric Uncertainty (Doğal Gürültü): Piyasanın doğasındaki tahmin edilemezlik

Teknik: MC Dropout (Monte Carlo Dropout)
  - Eğitimli modelin üzerine dropout katmanı simüle edilir
  - Aynı girdi için 50 farklı tahmin yapılır (her seferinde farklı nöronlar kapatılır)
  - Bu 50 tahminin ortalaması = "Bayesian Mean", std'si = "Uncertainty"

Dinamik Kelly:
  - Yüksek uncertainty → Kelly otomatik küçülür → Az risk
  - Düşük uncertainty + Yüksek confidence → Kelly tam boyut
"""

import numpy as np
import pickle
import os
import json
from datetime import datetime
from typing import List, Dict, Tuple, Optional, Union

BAYESIAN_CONFIG_PATH = "bayesian_config.json"


# =========================================================================== #
#  MC DROPOUT: Mevcut XGBoost Modelini Bayesian Moduna Çevir
# =========================================================================== #

class MCDropoutPredictor:
    """
    Mevcut ai_model.pkl (XGBoost/RandomForest) üzerine
    Monte Carlo Dropout simülasyonu uygular.

    Fikir:
      - Her tahmin turunda özelliklerin rastgele %20'sini maskeliyoruz
      - Bu, "model bu özelliği görmese ne düşünürdü?" sorusunu simüle eder
      - N_SAMPLES tur sonunda istatistik çıkarıyoruz
    """

    def __init__(self, n_samples: int = 50, dropout_rate: float = 0.20):
        self.n_samples    = n_samples
        self.dropout_rate = dropout_rate
        self.model_data   = None
        self._load_model()

    def _load_model(self):
        if os.path.exists("ai_model.pkl"):
            try:
                with open("ai_model.pkl", "rb") as f:
                    self.model_data = pickle.load(f)
            except Exception:
                pass

    def _get_expert(self, regime: str = "bull"):
        """Rejime göre en uygun expert modeli seç."""
        if self.model_data is None:
            return None
        experts = self.model_data.get("experts", {})
        return experts.get(regime) or (list(experts.values())[0] if experts else None)

    def predict_with_uncertainty(self, X: np.ndarray,
                                  feature_names: List[str],
                                  regime: str = "bull") -> dict:
        """
        MC Dropout ile belirsizlik tahminli predict.

        Returns:
          {
            "mean_prob":       float,   # Ortalama tahmin olasılığı
            "std_prob":        float,   # Belirsizlik (std)
            "epistemic_unc":   float,   # Veri eksikliği belirsizliği
            "confidence_band": tuple,   # (%5, %95) güven aralığı
            "is_confident":    bool,    # Güvenilir tahmin mi?
          }
        """
        model = self._get_expert(regime)
        if model is None:
            return {
                "mean_prob": 0.5, "std_prob": 0.5,
                "epistemic_unc": 1.0, "confidence_band": (0.0, 1.0),
                "is_confident": False, "n_samples": 0
            }

        preds = []
        n_feats = X.shape[1] if len(X.shape) > 1 else len(X)
        X_2d = X.reshape(1, -1) if len(X.shape) == 1 else X

        for _ in range(self.n_samples):
            # Feature dropout: rastgele özellikleri maskele
            X_dropped = X_2d.copy().astype(float)
            mask = np.random.random(n_feats) < self.dropout_rate
            X_dropped[:, mask] = 0.0

            try:
                if hasattr(model, 'predict_proba'):
                    prob = float(model.predict_proba(X_dropped)[0][1])
                else:
                    prob = float(model.predict(X_dropped)[0])
                preds.append(prob)
            except Exception:
                preds.append(0.5)

        preds = np.array(preds)
        mean  = float(np.mean(preds))
        std   = float(np.std(preds))

        # Epistemic uncertainty: Yüksek std → Model bu durumu tanımıyor
        epistemic = std * 2.0  # 0-1 arası normalize

        # Güven aralığı
        band = (float(np.percentile(preds, 5)),
                float(np.percentile(preds, 95)))

        # Güvenilir mi? (Std < 0.15 → Yüksek güven)
        is_confident = std < 0.15 and abs(mean - 0.5) > 0.1

        return {
            "mean_prob":       round(mean, 3),
            "std_prob":        round(std, 3),
            "epistemic_unc":   round(min(1.0, epistemic), 3),
            "confidence_band": (round(band[0], 3), round(band[1], 3)),
            "is_confident":    is_confident,
            "n_samples":       self.n_samples,
        }


# =========================================================================== #
#  DİNAMİK KELLY: Belirsizliğe Göre Pozisyon Ayarla
# =========================================================================== #

class DynamicKellyWithUncertainty:
    """
    Standart Kelly Criterion'ı epistemic uncertainty ile günceller.

    Formül:
        adjusted_kelly = kelly_fraction × (1 − epistemic_uncertainty)

    Mantık:
        - Model çok emin → Uncertainty düşük → Kelly tam çalışır
        - Model emin değil → Uncertainty yüksek → Kelly'de agresif kesinti
        - %100 belirsizlik → Pozisyon = 0 (İşlem yapma)
    """

    def __init__(self):
        self.config = self._load_config()

    def _load_config(self) -> dict:
        if os.path.exists(BAYESIAN_CONFIG_PATH):
            try:
                with open(BAYESIAN_CONFIG_PATH, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "uncertainty_penalty": 1.5,    # Belirsizlik ceza çarpanı
            "min_confidence":      0.10,   # Bu altında → İşlem yok
            "max_kelly":           0.25,   # Maksimum kasa %'si
        }

    def adjust_kelly(self, base_kelly: float,
                     epistemic_unc: float,
                     mean_prob: float,
                     is_confident: bool) -> dict:
        """
        Kelly fraksiyonunu Bayesian belirsizliğe göre dinamik olarak ayarlar.

        Args:
            base_kelly:     Ham Kelly fraksiyonu (policy_optimizer'dan)
            epistemic_unc:  0-1 arası belirsizlik skoru
            mean_prob:      Bayesian ortalama tahmin olasılığı
            is_confident:   Model güvenilir tahmin mi veriyor?

        Returns: {
            "adjusted_kelly": float,
            "kelly_pct":      float,
            "reduction":      float,   # Kelly'de ne kadar kesinti yapıldı (%)?
            "label":          str,
            "reason":         str,
        }
        """
        penalty = self.config["uncertainty_penalty"]

        # Düzeltme faktörü: Belirsizlik artıkça Kelly küçülür
        uncertainty_factor = max(0.0, 1.0 - (epistemic_unc * penalty))

        # Güven kontrolü: İşlem için minimum güven
        if mean_prob < self.config["min_confidence"] or (epistemic_unc > 0.7 and not is_confident):
            return {
                "adjusted_kelly": 0.0,
                "kelly_pct":      0.0,
                "reduction":      100.0,
                "label":          "🚫 GEÇIN (Yüksek Belirsizlik)",
                "reason":         f"Epistemic Unc={epistemic_unc:.2f} — Model bu durumu tanımıyor.",
            }

        adjusted = base_kelly * uncertainty_factor
        adjusted = round(max(0.0, min(self.config["max_kelly"], adjusted)), 3)
        kelly_pct = adjusted * 100
        reduction = round((1.0 - uncertainty_factor) * 100, 1) if base_kelly > 0 else 0.0

        # Etiket
        if kelly_pct < 2:
            label = "🔴 ÇOK KÜÇÜK GİRİŞ"
        elif kelly_pct < 8:
            label = f"🟡 TEMKİNLİ GİRİŞ (%{kelly_pct:.0f})"
        elif kelly_pct < 18:
            label = f"🟢 NORMAL GİRİŞ (%{kelly_pct:.0f})"
        else:
            label = f"💎 GÜÇLÜ GİRİŞ (%{kelly_pct:.0f})"

        reason = (
            f"Bayesian Prob={mean_prob:.2f}±{epistemic_unc:.2f} | "
            f"Uncertainty={epistemic_unc:.2f} | Kelly Kesintisi=%{reduction}"
        )

        return {
            "adjusted_kelly": adjusted,
            "kelly_pct":      round(kelly_pct, 1),
            "reduction":      reduction,
            "label":          label,
            "reason":         reason,
            "is_confident":   is_confident,
        }


# =========================================================================== #
#  SINYAL GÜVENİLİRLİK RAPORU
# =========================================================================== #

class BayesianSignalValidator:
    """
    Her sinyal için güvenilirlik raporu üretir.
    scoring.py'ye entegre edilecek ana arayüz.
    """

    def __init__(self):
        self.mcmc       = MCDropoutPredictor(n_samples=50, dropout_rate=0.20)
        self.dyn_kelly  = DynamicKellyWithUncertainty()

    def validate(self, feature_row: "pd.Series",
                 feature_names: List[str],
                 base_kelly: float,
                 regime: str = "bull") -> dict:
        """
        Ana doğrulama fonksiyonu.

        Returns: {
            "bayesian_prob":    float,
            "uncertainty":      float,
            "confidence_band":  tuple,
            "adjusted_kelly":   float,
            "kelly_pct":        float,
            "kelly_label":      str,
            "signal_grade":     str,   # "A+"/"A"/"B"/"C"/"D"
            "summary":          str,
        }
        """
        import pandas as pd
        # Feature vektörü oluştur
        feats = []
        for fn in feature_names:
            try:
                v = feature_row.get(fn, 0.0) if hasattr(feature_row, 'get') else getattr(feature_row, fn, 0.0)
                feats.append(float(v) if v is not None else 0.0)
            except Exception:
                feats.append(0.0)

        X = np.array(feats).reshape(1, -1)

        # MC Dropout tahmini
        unc_result = self.mcmc.predict_with_uncertainty(X, feature_names, regime)

        # Dinamik Kelly
        kelly_result = self.dyn_kelly.adjust_kelly(
            base_kelly     = base_kelly,
            epistemic_unc  = unc_result["epistemic_unc"],
            mean_prob      = unc_result["mean_prob"],
            is_confident   = unc_result["is_confident"],
        )

        # Sinyal Notu (A+ → D)
        mean_p = unc_result["mean_prob"]
        unc    = unc_result["epistemic_unc"]
        if mean_p > 0.7 and unc < 0.10:
            grade = "A+ (Kristal Netlik)"
        elif mean_p > 0.65 and unc < 0.20:
            grade = "A  (Güçlü)"
        elif mean_p > 0.55 and unc < 0.30:
            grade = "B  (Makul)"
        elif mean_p > 0.50 and unc < 0.45:
            grade = "C  (Zayıf)"
        else:
            grade = "D  (Güvensiz)"

        summary = (
            f"Bayesian={mean_p:.0%}±{unc:.0%} | "
            f"Güven Aralığı={unc_result['confidence_band']} | "
            f"Sinyal={grade} | {kelly_result['label']}"
        )

        return {
            "bayesian_prob":   unc_result["mean_prob"],
            "uncertainty":     unc_result["epistemic_unc"],
            "confidence_band": unc_result["confidence_band"],
            "is_confident":    unc_result["is_confident"],
            "adjusted_kelly":  kelly_result["adjusted_kelly"],
            "kelly_pct":       kelly_result["kelly_pct"],
            "kelly_reduction": kelly_result["reduction"],
            "kelly_label":     kelly_result["label"],
            "signal_grade":    grade,
            "summary":         summary,
        }


# Singleton
_validator = None

def get_bayesian_validator() -> BayesianSignalValidator:
    global _validator
    if _validator is None:
        _validator = BayesianSignalValidator()
    return _validator


if __name__ == "__main__":
    # Test (model olmasa bile çalışır)
    validator = get_bayesian_validator()
    import pandas as pd
    test_row = pd.Series({
        "rsi": 62.0, "macd_hist": 0.5, "adx": 30.0,
        "atr_pct": 2.5, "bb_width": 4.0, "roc20": 8.0,
    })
    result = validator.validate(
        feature_row   = test_row,
        feature_names = ["rsi", "macd_hist", "adx", "atr_pct", "bb_width", "roc20"],
        base_kelly    = 0.15,
        regime        = "bull",
    )
    print("\n🧠 Bayesian Doğrulama Sonucu:")
    for k, v in result.items():
        print(f"  {k}: {v}")
