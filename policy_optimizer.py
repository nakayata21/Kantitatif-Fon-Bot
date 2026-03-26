"""
policy_optimizer.py

AI Güven Skoru + Kelly Criterion → İdeal Pozisyon Büyüklüğü
Volatility-Adjusted Risk Rebalancing dahil.
"""

import numpy as np
import json
import os

POLICY_CONFIG_PATH = "policy_config.json"


class TradingPolicyOptimizer:
    def __init__(self, path=POLICY_CONFIG_PATH):
        self.path   = path
        self.config = self._load_config()

    def _load_config(self):
        if os.path.exists(self.path):
            with open(self.path, "r") as f:
                return json.load(f)
        return {
            "max_kelly_fraction": 0.25,   # Maksimum kasanın %25'i (güvenli Kelly)
            "volatility_cap":     0.30,   # ATR > %30 → İşlem yok
            "drawdown_limit":     10.0,   # Portföy %10 eridiyse → İşlem yok
            "base_unit":          1.0,
        }

    def save_config(self):
        with open(self.path, "w") as f:
            json.dump(self.config, f, indent=4)

    # ------------------------------------------------------------------ #
    # KELLY CRITERION
    # ------------------------------------------------------------------ #

    def kelly_fraction(self, win_rate: float, avg_win_pct: float, avg_loss_pct: float) -> float:
        """
        f* = (p * b - q) / b
        p  = win_rate
        q  = 1 - win_rate
        b  = avg_win / avg_loss
        """
        if avg_loss_pct <= 0:
            return 0.0
        b = abs(avg_win_pct) / abs(avg_loss_pct)
        f = (win_rate * b - (1 - win_rate)) / b
        # Half-Kelly güvenlik marjı
        f_half = f * 0.5
        return max(0.0, min(self.config["max_kelly_fraction"], round(f_half, 3)))

    # ------------------------------------------------------------------ #
    # ANA POZİSYON BÜYÜKLÜĞÜ
    # ------------------------------------------------------------------ #

    def calculate_position_size(self, ai_confidence: float, atr_pct: float,
                                 current_drawdown: float = 0.0,
                                 win_rate: float = 0.55,
                                 avg_win: float = 5.0,
                                 avg_loss: float = 3.0) -> dict:
        """
        Kelly + Volatilite + Drawdown korumalarını birleştirir.
        Returns: {"size": float, "kelly_f": float, "reason": str}
        """
        reason_parts = []

        # 1. Drawdown Koruması
        if current_drawdown > self.config["drawdown_limit"]:
            return {"size": 0.0, "kelly_f": 0.0, "size_pct": 0.0, "label": "GEÇIN",
                    "reason": f"Drawdown limiti aşıldı (%{current_drawdown:.1f})"}

        # 2. Volatilite Üst Sınırı
        if atr_pct > self.config["volatility_cap"] * 100:
            return {"size": 0.0, "kelly_f": 0.0, "size_pct": 0.0, "label": "GEÇIN",
                    "reason": f"Aşırı volatilite (%{atr_pct:.1f} ATR)"}

        # 3. Kelly Fraksiyonu
        kelly_f = self.kelly_fraction(win_rate, avg_win, avg_loss)
        reason_parts.append(f"Kelly={kelly_f:.2f}")

        # 4. AI Güven Ayarı
        conf_scale = max(0.0, (ai_confidence - 0.4) / 0.6)
        reason_parts.append(f"Conf={ai_confidence:.2f}")

        # 5. Volatilite Ölçeği
        vol_scale  = max(0.3, 1.0 - (atr_pct / 20.0))
        reason_parts.append(f"VolScale={vol_scale:.2f}")

        size = kelly_f * conf_scale * vol_scale
        size = round(max(0.0, min(self.config["max_kelly_fraction"], size)), 3)

        size_pct = size * 100
        if size_pct < 2:
            label = "COK KUCUK - Gecin"
        elif size_pct < 8:
            label = f"Kucuk Giris (%{size_pct:.0f})"
        elif size_pct < 18:
            label = f"Normal Giris (%{size_pct:.0f})"
        else:
            label = f"Buyuk Giris (%{size_pct:.0f})"

        return {
            "size":     size,
            "size_pct": round(size_pct, 1),
            "kelly_f":  kelly_f,
            "label":    label,
            "reason":   " | ".join(reason_parts),
        }

    # ------------------------------------------------------------------ #
    # VOLATİLİTE BAZLI REBALANCİNG ÖNERİSİ
    # ------------------------------------------------------------------ #

    def rebalance_signal(self, portfolio_atr_avg: float, market_vix_proxy: float) -> dict:
        risk_level = 0
        actions    = []

        if portfolio_atr_avg > 5.0:
            risk_level += 1
            actions.append("Yüksek volatiliteli hisselerin boyutunu küçült")

        if market_vix_proxy > 3.0:
            risk_level += 1
            actions.append("Piyasa geneli volatilite yüksek → Nakit oranını artır")

        if risk_level >= 2:
            action = "KUCULT"
        elif risk_level == 1:
            action = "IZLE"
        else:
            action = "NORMAL"

        return {"action": action, "risk_level": risk_level, "suggestions": actions}

    # ------------------------------------------------------------------ #
    # KENDİNİ OPTİMİZE ETME
    # ------------------------------------------------------------------ #

    def self_improve_policy(self, trade_history: list) -> str:
        if len(trade_history) < 20:
            return "Yetersiz veri (min 20 islem)"

        wins    = [t for t in trade_history if t.get("return", 0) > 0]
        losses  = [t for t in trade_history if t.get("return", 0) <= 0]

        if not wins or not losses:
            return "Heterojen sonuclar yetersiz"

        win_rate = len(wins) / len(trade_history)
        avg_win  = float(np.mean([t["return"] for t in wins]))
        avg_loss = float(np.mean([abs(t["return"]) for t in losses]))

        new_kelly = self.kelly_fraction(win_rate, avg_win, avg_loss)
        self.config["max_kelly_fraction"] = max(0.05, min(0.30, new_kelly))
        self.save_config()

        return (f"Politika Guncellendi: Kelly={new_kelly:.3f} | "
                f"WinRate=%{win_rate*100:.1f} | AvgWin={avg_win:.1f}% | AvgLoss={avg_loss:.1f}%")


if __name__ == "__main__":
    opt = TradingPolicyOptimizer()
    result = opt.calculate_position_size(
        ai_confidence=0.72, atr_pct=4.2,
        win_rate=0.58, avg_win=5.5, avg_loss=3.0
    )
    print(result)
