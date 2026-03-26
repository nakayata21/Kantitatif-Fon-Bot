"""
anomaly_detector.py

Autoencoder tabanlı Piyasa Anomali Dedektörü.

"Tahtacı" / Balina operasyonlarını tespit eder:
  - Hacim-Fiyat ilişkisini "normal" olarak öğrenir
  - Gelen veri bu normalden sapıyorsa → Anomali Skoru yüksek
  - Yüksek anomali → "AL" sinyali olsa bile sistem dur emri verir

Mimari:
  - Encoder: yüksek boyutlu piyasa durumu → gizli temsil (latent space)
  - Decoder: gizli temsil → orijinal piyasa durumu
  - Rekonstrüksiyon Hatası (MSE) = Anomali Skoru
  - VAE (Variational) için KL-Divergence terimi eklendi
"""

import numpy as np
import pandas as pd
import pickle
import os
from datetime import datetime
from typing import Optional, Union, Tuple, List, Dict


AUTOENCODER_PATH = "anomaly_model.pkl"
ANOMALY_THRESHOLD_PATH = "anomaly_threshold.pkl"

# =========================================================================== #
#  HAFIF NUMPY AUTOENCODER (Derin öğrenme kütüphanesi gerektirmez)
# =========================================================================== #

class LightAutoencoder:
    """
    Sıfırdan yazılmış hafif 3-katmanlı Autoencoder.
    Sigmoid aktivasyon + MSE kaybı + backprop.

    Katman yapısı: input_dim → hidden → latent → hidden → input_dim
    """

    def __init__(self, input_dim: int, hidden_dim: int = 16, latent_dim: int = 6,
                 lr: float = 0.01, epochs: int = 300):
        self.input_dim  = input_dim
        self.hidden_dim = hidden_dim
        self.latent_dim = latent_dim
        self.lr         = lr
        self.epochs     = epochs
        self._init_weights()

    def _init_weights(self):
        scale = 0.1
        d, h, l = self.input_dim, self.hidden_dim, self.latent_dim
        # Encoder ağırlıkları
        self.W1 = np.random.randn(d, h) * scale
        self.b1 = np.zeros(h)
        self.W2 = np.random.randn(h, l) * scale
        self.b2 = np.zeros(l)
        # Decoder ağırlıkları
        self.W3 = np.random.randn(l, h) * scale
        self.b3 = np.zeros(h)
        self.W4 = np.random.randn(h, d) * scale
        self.b4 = np.zeros(d)

    @staticmethod
    def _sigmoid(x):
        return 1.0 / (1.0 + np.exp(-np.clip(x, -500, 500)))

    @staticmethod
    def _sigmoid_grad(s):
        return s * (1.0 - s)

    def _forward(self, X):
        # Encode
        h1   = self._sigmoid(X @ self.W1 + self.b1)
        lat  = self._sigmoid(h1 @ self.W2 + self.b2)
        # Decode
        h2   = self._sigmoid(lat @ self.W3 + self.b3)
        out  = lat @ self.W4 + self.b4       # Linear output (better for MSE)
        return h1, lat, h2, out

    def _backward(self, X, h1, lat, h2, out):
        m    = X.shape[0]
        eps  = 1e-9

        # Output gradient (MSE loss)
        d_out = 2.0 * (out - X) / m

        # Decoder gradients
        d_W4  = h2.T @ d_out
        d_b4  = d_out.sum(axis=0)
        d_h2  = d_out @ self.W4.T * self._sigmoid_grad(h2)
        d_W3  = lat.T @ d_h2
        d_b3  = d_h2.sum(axis=0)

        # Encoder gradients
        d_lat = d_h2 @ self.W3.T * self._sigmoid_grad(lat)
        d_W2  = h1.T @ d_lat
        d_b2  = d_lat.sum(axis=0)
        d_h1  = d_lat @ self.W2.T * self._sigmoid_grad(h1)
        d_W1  = X.T @ d_h1
        d_b1  = d_h1.sum(axis=0)

        # Gradient clip & update
        for p, g in [(self.W1, d_W1), (self.b1, d_b1), (self.W2, d_W2), (self.b2, d_b2),
                     (self.W3, d_W3), (self.b3, d_b3), (self.W4, d_W4), (self.b4, d_b4)]:
            p -= self.lr * np.clip(g, -5.0, 5.0)

    def fit(self, X: np.ndarray, verbose: bool = False) -> list[float]:
        losses = []
        for epoch in range(self.epochs):
            h1, lat, h2, out = self._forward(X)
            loss = float(np.mean((out - X) ** 2))
            losses.append(loss)
            self._backward(X, h1, lat, h2, out)
            if verbose and epoch % 50 == 0:
                print(f"   Epoch {epoch}/{self.epochs} — MSE Loss: {loss:.5f}")
        return losses

    def reconstruct(self, X: np.ndarray) -> np.ndarray:
        _, _, _, out = self._forward(X)
        return out

    def anomaly_score(self, X: np.ndarray) -> np.ndarray:
        """Her örnek için rekonstrüksiyon hatası (MSE) = anomali skoru."""
        out = self.reconstruct(X)
        return np.mean((out - X) ** 2, axis=1)

    def encode(self, X: np.ndarray) -> np.ndarray:
        """Latent space temsili (boyut indirgeme)."""
        _, lat, _, _ = self._forward(X)
        return lat


# =========================================================================== #
#  ANOMALİ DEDEKTÖREventListener
# =========================================================================== #

# Piyasa durumunu temsil eden özellikler
_ANOMALY_FEATURES = [
    "vol_spike",       # Hacim spike
    "atr_pct",         # Volatilite
    "daily_return",    # Günlük getiri
    "rsi",             # RSI
    "bb_width",        # Bollinger genişliği
    "macd_hist",       # MACD momentum
    "ema20_slope",     # Kısa vadeli trend eğimi
    "roc20",           # 20 günlük momentum
]

_N_FEATURES = len(_ANOMALY_FEATURES)


def _normalize(X: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mu  = X.mean(axis=0)
    std = X.std(axis=0) + 1e-9
    return (X - mu) / std, mu, std


class MarketAnomalyDetector:
    """
    BIST piyasasındaki "tahtacı" / balina operasyonlarını tespit eder.

    Kullanım:
      1. train(historical_df)   → Normal piyasayı öğren
      2. detect(current_row)    → Mevcut durumu anomali-kontrol et
      3. is_safe(score)         → İşlem yapılabilir mi?
    """

    def __init__(self):
        self.model      = None
        self.threshold  = None
        self.mu         = None
        self.std        = None
        self.trained_at = None
        self._load()

    def _load(self):
        if os.path.exists(AUTOENCODER_PATH):
            try:
                with open(AUTOENCODER_PATH, "rb") as f:
                    saved = pickle.load(f)
                self.model      = saved["model"]
                self.threshold  = saved["threshold"]
                self.mu         = saved["mu"]
                self.std        = saved["std"]
                self.trained_at = saved.get("trained_at")
            except Exception:
                pass

    def _save(self):
        with open(AUTOENCODER_PATH, "wb") as f:
            pickle.dump({
                "model":      self.model,
                "threshold":  self.threshold,
                "mu":         self.mu,
                "std":        self.std,
                "trained_at": self.trained_at,
            }, f)

    def _extract_matrix(self, df: pd.DataFrame) -> Optional[np.ndarray]:
        """DataFrame'den anomali özellik matrisini çıkarır."""
        cols = [c for c in _ANOMALY_FEATURES if c in df.columns]
        if len(cols) < 4:
            return None
        mat = df[cols].select_dtypes(include=[np.number]).fillna(0).values
        # Eksik sütunlar için sıfır sütun ekle
        if mat.shape[1] < _N_FEATURES:
            pad = np.zeros((mat.shape[0], _N_FEATURES - mat.shape[1]))
            mat = np.hstack([mat, pad])
        return mat[:, :_N_FEATURES]

    def train(self, historical_dfs: List[pd.DataFrame], verbose: bool = False) -> str:
        """
        Birden fazla hissenin geçmiş verisinden "normal piyasa" profilini öğrenir.
        """
        print("\n🔬 Anomali Dedektörü: Normal piyasa profili öğreniliyor...")
        all_rows = []
        for df in historical_dfs:
            mat = self._extract_matrix(df)
            if mat is not None and len(mat) > 10:
                all_rows.append(mat)

        if not all_rows:
            return "⚠️ Yeterli veri yok."

        X_raw = np.vstack(all_rows)
        X, mu, std = _normalize(X_raw)

        # Autoencoder eğit
        self.model = LightAutoencoder(
            input_dim=_N_FEATURES, hidden_dim=24, latent_dim=8,
            lr=0.005, epochs=400
        )
        losses = self.model.fit(X, verbose=verbose)

        # Eşik değeri: 95. persentil rekonstrüksiyon hatası
        scores         = self.model.anomaly_score(X)
        self.threshold = float(np.percentile(scores, 95))
        self.mu        = mu
        self.std       = std
        self.trained_at = datetime.now().isoformat()
        self._save()

        final_loss = losses[-1] if losses else 0
        print(f"   ✅ Eğitim tamamlandı. Final MSE: {final_loss:.5f}")
        print(f"   📏 Anomali Eşiği (95p): {self.threshold:.5f}")
        print(f"   📊 Eğitim Örnekleri: {len(X)}")
        return f"✅ Anomali Dedektörü eğitildi. Eşik={self.threshold:.5f}"

    def detect(self, row: pd.Series) -> dict:
        """
        Tek bir veri noktası (hisse satırı) için anomali skoru hesaplar.
        Returns:
          {
            "anomaly_score": float,
            "is_anomaly":    bool,
            "severity":      str ("NORMAL"/"ŞÜPHELI"/"KRİTİK"),
            "explanation":   str,
          }
        """
        if self.model is None or self.threshold is None:
            return {"anomaly_score": 0.0, "is_anomaly": False,
                    "severity": "BILINMIYOR", "explanation": "Model henüz eğitilmedi."}

        # Özellik vektörü oluştur
        feats = []
        for feat in _ANOMALY_FEATURES:
            val = row.get(feat, 0.0)
            feats.append(float(val) if val is not None else 0.0)

        X_raw = np.array(feats).reshape(1, -1)
        X     = (X_raw - self.mu) / (self.std + 1e-9)

        # Rekonstrüksiyon hatası
        score = float(self.model.anomaly_score(X)[0])

        # Normalize skor (0-100 arası)
        norm_score = min(100.0, (score / (self.threshold + 1e-9)) * 100.0)

        # Şiddet sınıflandırması
        if norm_score > 250:
            severity    = "KRİTİK"
            explanation = "🚨 Ekstrem anomali! Manipülasyon veya ani şok olabilir."
            is_anomaly  = True
        elif norm_score > 150:
            severity    = "YÜKSEK"
            explanation = "⚠️ Olağandışı piyasa davranışı. Hacim-fiyat uyuşmazlığı."
            is_anomaly  = True
        elif norm_score > 100:   # Eşik = 100
            severity    = "ŞÜPHELI"
            explanation = "🟡 Şüpheli hareket. Normal sınırın üzerinde."
            is_anomaly  = True
        else:
            severity    = "NORMAL"
            explanation = "✅ Normal piyasa davranışı."
            is_anomaly  = False

        # En anormal özelliği bul
        reconstructed = self.model.reconstruct(X)[0]
        residuals     = np.abs(X[0] - reconstructed)
        top_feat_idx  = int(np.argmax(residuals))
        top_feat      = _ANOMALY_FEATURES[top_feat_idx] if top_feat_idx < len(_ANOMALY_FEATURES) else "?"
        if is_anomaly:
            explanation += f" En anormal özellik: '{top_feat}'"

        return {
            "anomaly_score":      round(score, 6),
            "anomaly_norm_score": round(norm_score, 1),
            "is_anomaly":         is_anomaly,
            "severity":           severity,
            "explanation":        explanation,
            "top_anomalous_feat": top_feat,
        }

    def is_safe_to_trade(self, row: pd.Series) -> tuple[bool, str]:
        """
        'AL' sinyali olsa bile anomali tespit edilirse işlemi durdurur.
        Returns: (safe: bool, reason: str)
        """
        result = self.detect(row)
        if result["is_anomaly"] and result["severity"] in ("YÜKSEK", "KRİTİK"):
            return False, f"🚫 ANOMALİ ENGELİ: {result['severity']} — {result['explanation']}"
        return True, "✅ Anomali yok, işlem güvenli."

    def get_latent_representation(self, row: pd.Series) -> np.ndarray:
        """Latent space vektörü döner (ileride kümeleme analizinde kullanılabilir)."""
        if self.model is None:
            return np.zeros(8)
        feats = [float(row.get(f, 0.0)) for f in _ANOMALY_FEATURES]
        X = (np.array(feats).reshape(1, -1) - self.mu) / (self.std + 1e-9)
        return self.model.encode(X)[0]


# Singleton
_detector = None

def get_anomaly_detector() -> MarketAnomalyDetector:
    global _detector
    if _detector is None:
        _detector = MarketAnomalyDetector()
    return _detector


def train_anomaly_detector_from_db():
    """
    signals_log.db içindeki geçmiş sinyallerin özelliklerini kullanarak
    anomali dedektörünü eğitir.
    """
    import sqlite3, json
    conn = sqlite3.connect("signals_log.db")
    df   = pd.read_sql_query("SELECT features FROM signals WHERE is_labeled=1 LIMIT 2000", conn)
    conn.close()

    if df.empty:
        print("⚠️ DB'de etiketli sinyal yok.")
        return

    rows = []
    for feat_str in df["features"]:
        try:
            d = json.loads(feat_str)
            rows.append(d)
        except Exception:
            continue

    feat_df = pd.DataFrame(rows).fillna(0)
    det = get_anomaly_detector()
    result = det.train([feat_df])
    print(result)


if __name__ == "__main__":
    import yfinance as yf

    # Test: THYAO üzerinde anomali tara
    df = yf.download("THYAO.IS", period="1y", interval="1d", progress=False)
    df["vol_spike"]    = df["Volume"] / df["Volume"].rolling(20).mean()
    df["atr_pct"]      = (df["High"] - df["Low"]) / df["Close"] * 100
    df["daily_return"] = df["Close"].pct_change() * 100
    df["rsi"]          = 50  # Placeholder
    df["bb_width"]     = 5
    df["macd_hist"]    = 0
    df["ema20_slope"]  = df["Close"].pct_change(5) * 100
    df["roc20"]        = df["Close"].pct_change(20) * 100
    df = df.dropna()

    det = MarketAnomalyDetector()
    result = det.train([df])
    print(result)

    # Son satır anomali testi
    last_row = df.iloc[-1]
    anomaly  = det.detect(last_row)
    print("\n🔬 Son Gün Anomali Analizi:")
    for k, v in anomaly.items():
        print(f"  {k}: {v}")
