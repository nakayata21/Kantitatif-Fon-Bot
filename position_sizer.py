
import numpy as np

class PositionSizer:
    """
    Position Sizing Engine: Hesap bakiyesi ve strateji başarısına (win rate) göre
    her işlemde ne kadarlık pozisyon açılması gerektiğini hesaplar.
    """
    
    def __init__(self, 
                 account_balance=100000, 
                 risk_per_trade=0.015, # %1.5 standart risk
                 max_position_pct=0.25, # Tek hissede max %25
                 use_kelly=True):
        self.account_balance = account_balance
        self.risk_per_trade = risk_per_trade
        self.max_position_pct = max_position_pct
        self.use_kelly = use_kelly

    def calculate_kelly_size(self, win_rate, reward_to_risk=1.5):
        """
        Kelly Criterion Formülü: f* = ( (b * p) - q ) / b
        b: Pozitif Getiri / Negatif Kayıp (Odds)
        p: Kazanma Olasılığı (Win Rate)
        q: Kaybetme Olasılığı (1 - p)
        """
        if win_rate <= 0 or win_rate >= 1:
            return 0.0
            
        b = reward_to_risk
        p = win_rate
        q = 1 - p
        
        kelly_f = ((b * p) - q) / b
        
        # Kelly bazen çok agresif olabilir, yarım Kelly (Half-Kelly) kullanarak risk düşürülür.
        half_kelly = kelly_f * 0.5
        return max(0.0, half_kelly)

    def size_position(self, win_rate, reward_to_risk=1.5, current_balance=None):
        """
        Ana hesaplama fonksiyonu.
        """
        balance = current_balance if current_balance else self.account_balance
        
        if self.use_kelly:
            # Kelly bazlı hesaplama
            size_pct = self.calculate_kelly_size(win_rate, reward_to_risk)
        else:
            # Sabit oranlı (Fixed Fractional) - Stop loss bazlı hesaplamaya yardımcı
            size_pct = self.risk_per_trade

        # Sınırlandırmalar (Konfor sınırı)
        final_pct = min(size_pct, self.max_position_pct)
        
        position_amount = balance * final_pct
        return {
            "position_amount": round(position_amount, 2),
            "allocation_pct": round(final_pct * 100, 2),
            "kelly_recommended": round(size_pct * 100, 2)
        }

def get_position_sizer():
    return PositionSizer()

if __name__ == "__main__":
    sizer = get_position_sizer()
    # %55 win rate ve 1.5 risk/kazanç oranı ile test
    res = sizer.size_position(win_rate=0.55, reward_to_risk=1.5, current_balance=50000)
    print(f"💰 Önerilen Pozisyon Büyüklüğü: {res['position_amount']} TL (%{res['allocation_pct']})")
