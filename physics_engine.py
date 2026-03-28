"""
physics_engine.py

Fizik Tabanlı Makine Öğrenimi — Piyasayı bir enerji sistemi gibi modeller.

1. Kalman Filtresi             — Gürültü temizleyici (Fake hareket eleme)
2. Fourier Gürültü Filtresi   — Yalnızca anlamlı frekansları tutar
3. Fiyat Elastisitesi         — "Geri çekilme kuvveti" (Mean Reversion fiziği)
4. Momentum Korumu Yasası     — Newton'un 1. yasasını fiyat hareketine uygula
5. PINN Özellik Üretici       — Tüm fizik metriklerini ML özelliğine dönüştür
"""

import numpy as np
import pandas as pd
from typing import Tuple, List, Dict, Optional, Union


# =========================================================================== #
#  1. KALMAN FİLTRESİ — Piyasa Gürültüsünü Temizle
# =========================================================================== #

class KalmanPriceFilter:
    """
    Tek-boyutlu Kalman Filtresi.
    Piyasadaki anlık "sahte" fiyat hareketlerini süzerek
    gerçek fiyat trendini (smooth price) ortaya çıkarır.

    Finansal yorumu:
      - Gözlem gürültüsü (R): Fiyatın kısa vadeli rastlantısallığı
      - Süreç gürültüsü (Q): Gerçek piyasa dinamiğinin değişim hızı
    """

    def __init__(self, process_var: float = 1e-5, observation_var: float = 1e-2):
        self.Q = process_var      # Süreç gürültüsü (düşük → daha pürüzsüz)
        self.R = observation_var  # Gözlem gürültüsü (yüksek → ham veriye az güven)
        self.P = 1.0              # Başlangıç tahmini hatası
        self.x = None             # Gizli durum (tahmin edilen gerçek fiyat)

    def filter(self, prices: np.ndarray) -> np.ndarray:
        """
        Fiyat serisine Kalman filtresi uygular.
        Returns: Gürültüsü temizlenmiş fiyat serisi
        """
        n      = len(prices)
        x_est  = np.zeros(n)
        p_est  = np.zeros(n)

        # İlk tahmin: ilk fiyat değeri
        x_est[0] = prices[0]
        p_est[0] = self.P

        for t in range(1, n):
            # --- TAHMİN (Predict) ---
            x_pred = x_est[t - 1]          # Sabit hız modeli (random walk)
            p_pred = p_est[t - 1] + self.Q

            # --- GÜNCELLEME (Update) ---
            K          = p_pred / (p_pred + self.R)   # Kalman Kazancı
            x_est[t]   = x_pred + K * (prices[t] - x_pred)
            p_est[t]   = (1 - K) * p_pred

        self.x = x_est
        return x_est

    def get_noise(self, prices: np.ndarray) -> np.ndarray:
        """Ham fiyat − Kalman tahmini = Gürültü (Noise)"""
        filtered = self.filter(prices)
        return prices - filtered

    def noise_ratio(self, prices: np.ndarray) -> float:
        """
        Gürültü oranı: 0 = tamamen temiz, 1 = tamamen gürültü.
        Yüksek oran → Fake hareketler baskın, işlem riskli.
        """
        noise = self.get_noise(prices)
        total_var    = np.var(prices)
        noise_var    = np.var(noise)
        return round(float(np.sqrt(noise_var / (total_var + 1e-9))), 4)


# =========================================================================== #
#  2. FOURİER GÜRÜLTÜ FİLTRESİ — Sadece Anlamlı Frekansları Tut
# =========================================================================== #

class FourierNoiseFilter:
    """
    Hızlı Fourier Dönüşümü (FFT) ile gürültü filtresi.

    Fikir:
      - Fiyat serisini frekans bileşenlerine ayır (FFT)
      - Düşük genlikli (anlamsız) bileşenleri sıfırla
      - Ters FFT ile sadece "sinyal taşıyan" fiyat serisini geri al

    Finansal yorumu:
      - Yüksek frekanslı bileşenler → Gün-içi gürültü / HFT manipülasyonu
      - Düşük frekanslı bileşenler → Gerçek trend ve döngüler
    """

    def __init__(self, keep_ratio: float = 0.15):
        """
        keep_ratio: Tutulacak frekans bileşenlerinin oranı.
                    0.15 → En önemli %15'i tut, geri kalanı sıfırla.
        """
        self.keep_ratio = keep_ratio

    def filter(self, prices: np.ndarray) -> np.ndarray:
        """Fourier filtreli fiyat serisi döner."""
        n           = len(prices)
        fft_vals    = np.fft.rfft(prices)
        n_keep      = max(1, int(len(fft_vals) * self.keep_ratio))
        fft_filtered = np.zeros_like(fft_vals)
        fft_filtered[:n_keep] = fft_vals[:n_keep]
        filtered    = np.fft.irfft(fft_filtered, n=n)
        return filtered

    def dominant_cycles(self, prices: np.ndarray, top_k: int = 3) -> List[Dict]:
        """
        Fiyat serisindeki dominant döngüleri (cycle) tespit eder.
        Returns: [{"period_days": int, "power": float}, ...]
        """
        n        = len(prices)
        fft_vals = np.fft.rfft(prices)
        power    = np.abs(fft_vals) ** 2
        freqs    = np.fft.rfftfreq(n)

        # DC bileşeni (frekans=0) atla
        power[0] = 0

        top_idx = np.argsort(power)[::-1][:top_k]
        cycles  = []
        for i in top_idx:
            freq = freqs[i]
            if freq > 0:
                period = round(1.0 / freq)
                cycles.append({"period_days": int(period), "power": round(float(power[i]), 2)})

        return cycles


# =========================================================================== #
#  3. FİYAT ELASTİSİTESİ — Geri Çekilme Kuvveti Yasası
# =========================================================================== #

class PriceElasticity:
    """
    Hooke Yasası analogu: F = -k * x
      x = Fiyatın hareketli ortalamadan sapması (uzaklık)
      k = Piyasanın "esneklik katsayısı" (tarihsel sapma std'sinden türetilir)
      F = Geri dönüş kuvveti (negatif → aşağı baskı, pozitif → yukarı baskı)

    Pratik Kullanım:
      - Çok uzaklaşmış (overextended) fiyatlar için "yakın zamanda geri döner" uyarısı
      - "Geri çekilme olasılığı" (reversion_prob) skor olarak üretilir
    """

    def __init__(self, window: int = 50):
        self.window = window

    def calculate(self, prices: pd.Series) -> dict:
        """
        Fiyat elastisitesi ve geri dönüş kuvvetini hesaplar.
        """
        if len(prices) < self.window + 5:
            return {"force": 0.0, "reversion_prob": 0.5, "z_distance": 0.0, "tag": "NORMAL"}

        ma   = prices.rolling(self.window).mean()
        std  = prices.rolling(self.window).std()

        last_price = float(prices.iloc[-1]) if not isinstance(prices.iloc[-1], pd.Series) else float(prices.iloc[-1].item())
        last_ma    = float(ma.iloc[-1]) if not isinstance(ma.iloc[-1], pd.Series) else float(ma.iloc[-1].item())
        
        _std_val = std.iloc[-1]
        if isinstance(_std_val, pd.Series): _std_val = _std_val.item()
        last_std = float(_std_val) if float(_std_val) > 0 else 1.0

        # Z-skoru: Kaç standart sapma uzakta?
        z_dist = (last_price - last_ma) / last_std

        # Geri çekilme kuvveti (Hooke Yasası - esneklik)
        # k = 1.0 / last_std → Sapma büyüdükçe geri dönüş gücü artar
        k      = 1.0 / (last_std + 1e-9)
        force  = -k * (last_price - last_ma)    # Negatif → Aşağı baskı

        # Geri dönüş olasılığı (Sigmoid ile normalize)
        # |z| > 2 → olasılık belirgin şekilde artar
        reversion_prob = 1.0 / (1.0 + np.exp(-0.8 * (abs(z_dist) - 1.5)))

        # Etiket
        if z_dist > 2.5:
            tag = "AŞIRI YUKARI (Güçlü Geri Çekilme Beklentisi)"
        elif z_dist > 1.5:
            tag = "UZAKLAŞMIŞ YUKARI (Temkinli)"
        elif z_dist < -2.5:
            tag = "AŞIRI AŞAĞI (Sert Geri Dönüş Potansiyeli)"
        elif z_dist < -1.5:
            tag = "UZAKLAŞMIŞ AŞAĞI (Dip Fırsatı Olabilir)"
        else:
            tag = "NORMAL (Ortalama İçinde)"

        return {
            "z_distance":      round(float(z_dist), 3),
            "force":           round(float(force), 6),
            "reversion_prob":  round(float(reversion_prob), 3),
            "tag":             tag,
            "ma50":            round(float(last_ma), 4),
        }


# =========================================================================== #
#  4. MOMENTUM KORUMU YASASI — Newton'un 1. Yasası
# =========================================================================== #

class MomentumConservation:
    """
    Newton'un 1. Yasası: "Hareket halindeki cisim devinimine devam eder."

    Finansal analogu:
      - Trend ivmesi (acceleration): Fiyat değişim hızının değişimi
      - Momentum'un "kırılması" (momentum break): İvmenin negatife dönmesi
      - Bu kırılma noktaları potansiyel trend dönüşlerini önceden haber verir.
    """

    def __init__(self, short_window: int = 10, long_window: int = 30):
        self.short = short_window
        self.long  = long_window

    def analyze(self, prices: pd.Series) -> dict:
        """
        Fiyat ivmesini ve momentum kırılmalarını tespit eder.
        """
        if len(prices) < self.long + 5:
            return {"acceleration": 0.0, "momentum_state": "NÖTR", "break_detected": False}

        # Velocity (hız): Kısa vadeli getiri
        vel_short = prices.pct_change(self.short).iloc[-1] * 100
        vel_long  = prices.pct_change(self.long).iloc[-1] * 100

        # Acceleration (ivme): Hızın değişimi
        vel_series     = prices.pct_change(self.short) * 100
        accel          = vel_series.diff(self.short).iloc[-1]

        # Momentum Kırılması: Son 'long_window' içinde hız sinyali değişti mi?
        vel_signs    = np.sign(vel_series.tail(self.long).dropna())
        sign_changes = int((np.diff(vel_signs) != 0).sum())
        break_detected = sign_changes > (self.long * 0.35)   # %35'ten fazla tersine dönüş

        # Durum
        if vel_short > 0 and accel > 0:
            state = "IVMELENEN YÜKSELİŞ"
        elif vel_short > 0 and accel < 0:
            state = "YAVAŞLAYAN YÜKSELİŞ (Dikkat)"
        elif vel_short < 0 and accel < 0:
            state = "IVMELENEN DÜŞÜŞ"
        elif vel_short < 0 and accel > 0:
            state = "YAVAŞLAYAN DÜŞÜŞ (Dip Olabilir)"
        else:
            state = "NÖTR"

        return {
            "velocity_short":   round(float(vel_short), 3),
            "velocity_long":    round(float(vel_long), 3),
            "acceleration":     round(float(accel), 3),
            "momentum_state":   state,
            "break_detected":   bool(break_detected),
            "sign_changes":     sign_changes,
        }


# =========================================================================== #
#  5. PINN ÖZELLİK ÜRETİCİ — Tüm Fizik Metriklerini ML Özelliğine Dönüştür
# =========================================================================== #

class PhysicsFeatureExtractor:
    """
    Tüm fizik tabanlı hesapları çalıştırır ve
    scoring.py / trainer_service.py için tek bir özellik sözlüğü üretir.
    """

    def __init__(self):
        self.kalman   = KalmanPriceFilter(process_var=1e-5, observation_var=5e-3)
        self.fourier  = FourierNoiseFilter(keep_ratio=0.20)
        self.elastic  = PriceElasticity(window=50)
        self.momentum = MomentumConservation(short_window=10, long_window=30)

    def extract(self, df: pd.DataFrame) -> dict:
        """
        OHLCV DataFrame'inden fizik özelliklerini çıkarır.
        Returns: {feature_name: float, ...}  — scoring.py'ye eklenebilir
        """
        if df is None or "Close" not in df.columns or len(df) < 60:
            return {}

        prices = df["Close"].astype(float).dropna()
        arr    = prices.values

        features = {}

        # --- Kalman ---
        try:
            _ = self.kalman.filter(arr)
            features["kalman_noise_ratio"] = self.kalman.noise_ratio(arr)
            # Kalman fiyatı ile ham fiyat arasındaki son sapma
            kalman_smooth = self.kalman.x
            features["kalman_deviation"] = round(
                float((arr[-1] - kalman_smooth[-1]) / (kalman_smooth[-1] + 1e-9) * 100), 3
            )
        except Exception:
            features["kalman_noise_ratio"] = 0.5
            features["kalman_deviation"]   = 0.0

        # --- Fourier ---
        try:
            filtered_arr = self.fourier.filter(arr)
            # Fourier filtreli fiyat ile ham fiyat farkı → Ne kadar "fake hareket" var?
            fourier_residual = arr[-1] - filtered_arr[-1]
            features["fourier_residual_pct"] = round(
                float(fourier_residual / (arr[-1] + 1e-9) * 100), 3
            )
            cycles = self.fourier.dominant_cycles(arr, top_k=1)
            features["dominant_cycle_days"] = cycles[0]["period_days"] if cycles else 0
        except Exception:
            features["fourier_residual_pct"]  = 0.0
            features["dominant_cycle_days"]    = 0

        # --- Elastisite ---
        try:
            elast = self.elastic.calculate(prices)
            features["elastic_z_distance"]    = elast["z_distance"]
            features["elastic_reversion_prob"] = elast["reversion_prob"]
            features["elastic_force"]          = float(np.tanh(elast["force"] * 1000))
        except Exception:
            features["elastic_z_distance"]    = 0.0
            features["elastic_reversion_prob"] = 0.5
            features["elastic_force"]          = 0.0

        # --- Momentum Fiziği ---
        try:
            mom = self.momentum.analyze(prices)
            features["momentum_acceleration"]  = float(np.tanh(mom["acceleration"]))
            features["momentum_velocity_ratio"] = round(
                float(mom["velocity_short"] / (abs(mom["velocity_long"]) + 1e-9)), 3
            )
            features["momentum_break"]         = int(mom["break_detected"])
        except Exception:
            features["momentum_acceleration"]   = 0.0
            features["momentum_velocity_ratio"] = 1.0
            features["momentum_break"]          = 0

        return features

    def score_for_trading(self, df: pd.DataFrame) -> dict:
        """
        Ham fizik özelliklerini alıp insan okunabilir sinyal skoru üretir.
        scoring.py'den çağrılmak üzere tasarlandı.

        Returns:
          {
            "physics_score": float, # (-15 ile +15 arası puan)
            "noise_level":   str, # ("DÜŞÜK" / "ORTA" / "YÜKSEK")
            "tags":          List[str],
            "features":      dict (ML eğitimi için ham özellikler)
          }
        """
        features = self.extract(df)
        if not features:
            return {"physics_score": 0.0, "noise_level": "ORTA", "tags": [], "features": {}}

        score = 0.0
        tags  = []

        # 1. Gürültü değerlendirmesi
        noise_r = features.get("kalman_noise_ratio", 0.5)
        if noise_r < 0.20:
            noise_level = "DÜŞÜK"
            score      += 5.0
            tags.append("⚡ TEMİZ SİNYAL (Gürültü Düşük)")
        elif noise_r < 0.45:
            noise_level = "ORTA"
        else:
            noise_level = "YÜKSEK"
            score      -= 5.0
            tags.append("🌊 YÜKSEK GÜRÜLTÜ (Fake Hareket Riski)")

        # 2. Fourier sapması
        f_res = features.get("fourier_residual_pct", 0.0)
        if abs(f_res) > 3.0:
            score -= 3.0
            tags.append(f"📡 FOURİER SAPMASI: %{f_res:+.1f} (Anlamsız Spike)")

        # 3. Elastisite / Mean Reversion
        z = features.get("elastic_z_distance", 0.0)
        rev_prob = features.get("elastic_reversion_prob", 0.5)
        if z > 2.5:
            score -= 8.0
            tags.append(f"🔴 ELASTİSİTE: Aşırı Uzak (Z={z:.2f}) — Geri Çekilme Riski Yüksek")
        elif z > 1.5:
            score -= 3.0
            tags.append(f"⚠️ ELASTİSİTE: Biraz Uzak (Z={z:.2f})")
        elif z < -2.0:
            score += 6.0
            tags.append(f"🟢 ELASTİSİTE: Aşırı Geri Çekilmiş (Z={z:.2f}) — Dip Fırsatı")
        elif -1.0 <= z <= 1.0:
            score += 3.0    # Ortada, sağlıklı

        # 4. Momentum
        accel = features.get("momentum_acceleration", 0.0)
        if accel > 0.3:
            score += 4.0
            tags.append("🚀 MOMENTUM FİZİĞİ: İvme Artıyor")
        elif accel < -0.3:
            score -= 4.0
            tags.append("📉 MOMENTUM FİZİĞİ: İvme Azalıyor")

        if features.get("momentum_break", 0):
            score -= 5.0
            tags.append("💥 MOMENTUM KIRILMASI Tespit Edildi!")

        # Dominant döngü yorum
        cyc = features.get("dominant_cycle_days", 0)
        if 15 <= cyc <= 25:
            tags.append(f"🌀 Dominant Döngü: {cyc} gün (Aylık periyot)")
        elif 50 <= cyc <= 70:
            tags.append(f"🌀 Dominant Döngü: {cyc} gün (Çeyrek periyot)")

        return {
            "physics_score": round(float(max(-15.0, min(15.0, score))), 2),
            "noise_level":   noise_level,
            "tags":          tags,
            "features":      features,
        }


# Singleton
_physics_engine = None

def get_physics_engine() -> PhysicsFeatureExtractor:
    global _physics_engine
    if _physics_engine is None:
        _physics_engine = PhysicsFeatureExtractor()
    return _physics_engine


if __name__ == "__main__":
    import yfinance as yf
    df = yf.download("THYAO.IS", period="2y", interval="1d", progress=False)
    engine = get_physics_engine()

    # Ham özellikler
    feats = engine.extract(df)
    print("\n📐 Fizik Özellikleri:", feats)

    # Trading skoru
    result = engine.score_for_trading(df)
    print(f"\n⚛️ Fizik Skoru: {result['physics_score']}")
    print(f"🔊 Gürültü Seviyesi: {result['noise_level']}")
    for tag in result["tags"]:
        print(f"  {tag}")
