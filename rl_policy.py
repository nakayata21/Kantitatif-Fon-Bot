"""
rl_policy.py

Reinforcement Learning Politika Modülü:
  - Q-Learning tabanlı basit ajan (State → Action → Reward döngüsü)
  - State: (regime, rsi_bucket, trend_bucket, ai_confidence_bucket)
  - Action: 0=İŞLEM_YOK, 1=AL, 2=KÜÇÜK_AL, 3=ŞORT (opsiyonel)
  - Reward: Triple-Barrier sonucu (TP=+1, SL=-1, TIME=outcome*0.1)
"""

import numpy as np
import pickle
import os
import json
from datetime import datetime

RL_TABLE_PATH   = "rl_q_table.pkl"
RL_HISTORY_PATH = "rl_history.json"

ACTIONS = {0: "İŞLEM_YOK", 1: "AL", 2: "KÜÇÜK_AL", 3: "ŞORT"}

# Hiperparametreler
ALPHA   = 0.1    # Öğrenme hızı
GAMMA   = 0.9    # Discount factor (gelecek ödüllerin ağırlığı)
EPSILON = 0.15   # Keşif oranı (rastgele deney)


def _discretize_state(regime: str, rsi: float, trend_score: float, ai_conf: float) -> tuple:
    """
    Sürekli değişkenleri ayrıklaştırır → Q-Table index'i.
    """
    reg_bucket = {"bull": 0, "bear": 1, "sideways": 2}.get(regime.lower(), 2)

    # RSI: 0-40=Oversold(0), 40-60=Nötr(1), 60-100=Overbought(2)
    if rsi < 40:
        rsi_b = 0
    elif rsi < 60:
        rsi_b = 1
    else:
        rsi_b = 2

    # Trend: Negatif(0), Nötr(1), Pozitif(2)
    if trend_score < -0.3:
        trend_b = 0
    elif trend_score < 0.3:
        trend_b = 1
    else:
        trend_b = 2

    # AI Confidence: Düşük(0), Orta(1), Yüksek(2)
    if ai_conf < 0.45:
        conf_b = 0
    elif ai_conf < 0.65:
        conf_b = 1
    else:
        conf_b = 2

    return (reg_bucket, rsi_b, trend_b, conf_b)


class RLTradingAgent:
    """
    Basit Q-Learning ajanı. Kalıcı Q-Table ile deneyimden öğrenir.
    """

    def __init__(self):
        self.q_table  = self._load_table()
        self.history  = self._load_history()

    # ------------------------------------------------------------------ #
    # Q-Table Yönetimi
    # ------------------------------------------------------------------ #

    def _load_table(self) -> dict:
        if os.path.exists(RL_TABLE_PATH):
            try:
                with open(RL_TABLE_PATH, "rb") as f:
                    return pickle.load(f)
            except Exception:
                pass
        return {}

    def _save_table(self):
        with open(RL_TABLE_PATH, "wb") as f:
            pickle.dump(self.q_table, f)

    def _load_history(self) -> list:
        if os.path.exists(RL_HISTORY_PATH):
            try:
                with open(RL_HISTORY_PATH, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save_history(self):
        with open(RL_HISTORY_PATH, "w") as f:
            json.dump(self.history[-500:], f)  # Son 500 işlem

    def _get_q(self, state: tuple, action: int) -> float:
        return self.q_table.get((state, action), 0.0)

    def _set_q(self, state: tuple, action: int, value: float):
        self.q_table[(state, action)] = value

    # ------------------------------------------------------------------ #
    # Karar Alma
    # ------------------------------------------------------------------ #

    def choose_action(self, regime: str, rsi: float, trend_score: float,
                      ai_conf: float, greedy: bool = False) -> dict:
        """
        Epsilon-greedy politika ile en iyi aksiyonu seçer.
        greedy=True → Her zaman en yüksek Q değerini seç (üretim modu).
        """
        state    = _discretize_state(regime, rsi, trend_score, ai_conf)
        n_act    = len(ACTIONS)

        if not greedy and np.random.random() < EPSILON:
            action_id = np.random.randint(n_act)   # Keşif
        else:
            q_vals    = [self._get_q(state, a) for a in range(n_act)]
            action_id = int(np.argmax(q_vals))

        action_name = ACTIONS[action_id]

        # Position size önerisini de hesapla
        if action_id == 0:
            pos_size = 0.0
        elif action_id == 1:
            pos_size = min(ai_conf * 1.5, 1.0)     # Tam giriş
        elif action_id == 2:
            pos_size = min(ai_conf * 0.7, 0.5)     # Yarı giriş
        else:
            pos_size = -min(ai_conf * 0.5, 0.3)    # Şort

        return {
            "action":    action_name,
            "action_id": action_id,
            "pos_size":  round(pos_size, 2),
            "state":     state,
            "q_vals":    [round(self._get_q(state, a), 3) for a in range(n_act)],
        }

    # ------------------------------------------------------------------ #
    # Öğrenme (Feedback Loop)
    # ------------------------------------------------------------------ #

    def learn_from_outcome(self, state: tuple, action_id: int,
                           outcome_pct: float, label_type: str):
        """
        Gerçek işlem sonucuyla Q-Table'ı günceller.
        outcome_pct: Triple-Barrier sonucu (%)
        label_type: "TP" | "SL" | "TIME"
        """
        # Ödül fonksiyonu
        if label_type == "TP":
            reward = +1.0
        elif label_type == "SL":
            reward = -1.0
        else:
            reward = float(np.tanh(outcome_pct / 5.0))   # TIME: -1 ile +1 arası

        # Q-Learning güncelleme
        old_q        = self._get_q(state, action_id)
        # Bir sonraki durumu basitçe aynı kabul ediyoruz (episodic)
        max_next_q   = 0.0
        new_q        = old_q + ALPHA * (reward + GAMMA * max_next_q - old_q)
        self._set_q(state, action_id, new_q)

        self.history.append({
            "state":      str(state),
            "action":     ACTIONS[action_id],
            "outcome":    round(outcome_pct, 2),
            "label":      label_type,
            "reward":     round(reward, 3),
            "new_q":      round(new_q, 3),
            "ts":         datetime.now().isoformat(),
        })

        self._save_table()
        self._save_history()

    def get_policy_report(self) -> str:
        """Q-Table'dan insan okunabilir rapor üretir."""
        n_states  = len(set(s for s, _ in self.q_table.keys()))
        n_actions = len(self.q_table)
        if not self.history:
            return "⚠️ Henüz RL deneyimi yok."

        rewards = [h["reward"] for h in self.history[-100:]]
        avg_r   = round(float(np.mean(rewards)), 3)
        action_counts = {}
        for h in self.history[-100:]:
            a = h["action"]
            action_counts[a] = action_counts.get(a, 0) + 1

        lines = [
            f"🧬 RL Ajan Raporu ({len(self.history)} toplam deneyim)",
            f"   Q-Table boyutu: {n_states} durum × {n_actions} kayıt",
            f"   Son 100 ödül ortalaması: {avg_r}",
            f"   Aksiyon dağılımı: {action_counts}",
        ]
        return "\n".join(lines)


# Singleton
_rl_agent = None

def get_rl_agent() -> RLTradingAgent:
    global _rl_agent
    if _rl_agent is None:
        _rl_agent = RLTradingAgent()
    return _rl_agent


if __name__ == "__main__":
    agent = get_rl_agent()
    decision = agent.choose_action("bull", 62.0, 0.7, 0.75, greedy=True)
    print("RL Kararı:", decision)
    print(agent.get_policy_report())
