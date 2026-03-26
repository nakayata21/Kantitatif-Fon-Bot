"""
policy_optimizer.py

Bu modül, AI modelinin güven skoru ile piyasa oynaklığını birleştirerek
'İdeal Pozisyon Büyüklüğü' katsayısını hesaplar. 

Kendi kendini optimize eden bir Policy Network mantığıyla çalışır.
"""

import numpy as np
import json
import os

POLICY_CONFIG_PATH = "policy_config.json"

class TradingPolicyOptimizer:
    def __init__(self, path=POLICY_CONFIG_PATH):
        self.path = path
        self.config = self._load_config()

    def _load_config(self):
        if os.path.exists(self.path):
            with open(self.path, "r") as f:
                return json.load(f)
        return {
            "confidence_weight": 1.5,   # Güven skoru çarpanı
            "volatility_penalty": 0.8, # Oynaklık cezası
            "drawdown_limit": 5.0,     # Max kabul edilebilir düşüş %
            "base_unit": 1.0           # Standart pozisyon büyüklüğü
        }

    def save_config(self):
        with open(self.path, "w") as f:
            json.dump(self.config, f, indent=4)

    def calculate_position_size(self, ai_confidence, atr_pct, current_drawdown=0.0):
        """
        AI Güven Skoru + Volatilite + Portföy Durumu -> Birleşik Pozisyon Katsayısı
        """
        # 1. Base Multiplier (Kelly Criterion benzeri mantık)
        # confidence: 0.0 - 1.0 arası
        conf_mult = (ai_confidence * self.config["confidence_weight"]) - 0.5
        
        # 2. Volatilite Ayarı (Aşırı oynaklıkta vites küçült)
        # atr_pct: Hissenin % bazlı günlük ortalama hareketi
        vol_mult = 1.0
        if atr_pct > 5.0:  # %5'ten fazla oynaklık
            vol_mult = 1.0 - (atr_pct * 0.05 * self.config["volatility_penalty"])
        
        # 3. Drawdown Koruması (Portföy eriyorsa risk azalt)
        dd_mult = 1.0
        if current_drawdown > self.config["drawdown_limit"]:
            dd_mult = 1.0 - (current_drawdown / 100.0)
            
        position_size = self.config["base_unit"] * conf_mult * vol_mult * dd_mult
        
        # Sınırlar: 0.0 (Girme) ile 2.0 (Kaldıraçlı girilebilir) arası
        return max(0.0, min(2.0, round(position_size, 2)))

    def self_improve_policy(self, trade_history):
        """
        Geçmiş işlemleri simüle ederek katsayıları (weights) optimize eder.
        """
        if len(trade_history) < 20: 
            return "⚠️ Yetersiz veri (Min 20 işlem)."

        best_reward = -99999
        best_params = self.config.copy()
        
        print("\n🏦 Sermaye Politikası Optimizasyonu (Monte Carlo Simulation)...")
        # Basit bir deneme-yanılma (Policy Search) simülasyonu
        for _ in range(100):
            # Rastgele yeni politika adayları üret
            trial_conf_w = self.config["confidence_weight"] + np.random.uniform(-0.5, 0.5)
            trial_vol_p = self.config["volatility_penalty"] + np.random.uniform(-0.2, 0.2)
            
            simulated_pnl = 0
            for trade in trade_history:
                # Trade: {'conf': 0.65, 'atr': 3.2, 'return': 5.2}
                size = (trade['conf'] * trial_conf_w - 0.5) * (1.0 - (trade['atr'] * 0.05 * trial_vol_p))
                size = max(0.0, min(2.0, size))
                simulated_pnl += size * trade['return']
            
            if simulated_pnl > best_reward:
                best_reward = simulated_pnl
                best_params["confidence_weight"] = trial_conf_w
                best_params["volatility_penalty"] = trial_vol_p
        
        self.config = best_params
        self.save_config()
        return "✅ Politika Optimize Edildi."

if __name__ == "__main__":
    opt = TradingPolicyOptimizer()
    # Örnek hesaplama: %70 güven, %4 volatilite
    size = opt.calculate_position_size(0.70, 4.0)
    print(f"Önerilen Pozisyon Büyüklüğü: {size}x")
