"""
takas_analyzer.py

BIST (Borsa İstanbul) için Aracı Kurum Dağılımı (AKD) ve Saklama (Takas) verilerini analiz eder.
Takas analizi, büyük oyuncuların (Citi, Deutsche, Fonlar) hareketlerini ve küçük yatırımcının
(Diğer) malı kime devrettiğini anlamak için kullanılır.

Modüller:
  1. Para Girişi/Çıkışı (İlk 5 Alıcı/Satıcı Farkı)
  2. Küçük Yatırımcı (Diğer) Filtresi — "Diğer" satıyorsa büyükler topluyordur.
  3. Akıllı Para (Kurumsal) Teyidi — Yabancı ve Fon alışları.
  4. Maliyet Kontrolü — Fiyat maliyetin çok üzerindeyse risklidir.
  5. Fiyat/Takas Uyumsuzluğu — Fiyat düşerken takasın düzelmesi (Divergence).
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime


class TakasAnalizoru:
    def __init__(self, veri: Dict):
        """
        veri formatı:
        {
            'hisse_adi': str,
            'ilk_5_alici_oran': float,
            'ilk_5_satici_oran': float,
            'ilk_3_alici_payi': float, (Yeni: Karşılama oranı)
            'diger_alici_orani': float,
            'diger_satici_orani': float,
            'guncel_fiyat': float,
            'kurumsal_maliyet': float, (ilk_5_maliyet ile aynı)
            'fiyat_trend': float,
            'fiyat_degisim': float
        }
        """
        self.veri = veri
        self.skor = 0
        self.sinyaller = []

    def analiz_et(self) -> Dict:
        if not self.veri:
            return {"error": "Veri yok"}

        # --- Modül 1: Para Girişi (İlk 5 Alıcı vs Satıcı) ---
        # İlk 5 kurumun alıcı tarafında daha baskın olması kalitedir.
        alicilar_5 = self.veri.get('ilk_5_alici_oran', 0)
        saticilar_5 = self.veri.get('ilk_5_satici_oran', 0)
        
        if alicilar_5 > saticilar_5:
            # Fark %10'un üzerindeyse daha yüksek puan
            fark = alicilar_5 - saticilar_5
            bonus = 10 if fark > 20 else 0
            self.skor += (20 + bonus)
            self.sinyaller.append(f"✅ Pozitif Para Girişi (Fark: %{round(fark, 1)})")

        # --- Modül 2 & 3: Küçük Yatırımcı (Diğer) Filtresi ---
        # "Diğer" satıyorsa (diger_satici > diger_alici), bu malın küçükten büyüklere geçtiğini gösterir (Accumulation).
        diger_alici = self.veri.get('diger_alici_orani', self.veri.get('diger_alici_oran', 0))
        diger_satici = self.veri.get('diger_satici_orani', self.veri.get('diger_satici_oran', 0))
        
        if diger_satici > diger_alici:
            fark_diger = diger_satici - diger_alici
            self.skor += 25
            self.sinyaller.append(f"💎 Küçük Yatırımcı Çıkıyor (Mal Toplanıyor, Fark: %{round(fark_diger, 1)})")
        elif diger_alici > diger_satici:
            self.skor -= 20
            self.sinyaller.append("⚠️ Risk: Mal Küçük Yatırımcıya Dağıtılıyor (Distribution)")

        # --- Modül 4: Akıllı Para (Yabancı/Fon) Teyidi ---
        # BIST'te Citibank, Deutsche, Emeklilik ve Yatırım Fonları 'akıllı para' olarak kabul edilir.
        akilli_para_kurumlar = ['CITIBANK', 'DEUTSCHE', 'YABANCI', 'EMEKLILIK FON', 'YATIRIM FON']
        for kurum in self.veri.get('ana_alicilar', []):
            kurum_ad = str(kurum.get('ad', '')).upper()
            if any(key in kurum_ad for key in akilli_para_kurumlar):
                # Kurumun takas payı ne kadar yüksekse, alışının etkisi o kadar büyük olur
                pay = kurum.get('toplam_takas_payi', 0.1)
                puan = 15 * (1 + pay) 
                self.skor += puan
                self.sinyaller.append(f"🏦 Akıllı Para Alımı: {kurum_ad} (Pay: %{round(pay*100, 1)})")

        # --- Modül 5: Maliyet Kontrolü ---
        # Fiyat, kurumsal maliyetten çok uzaklaşmamışsa "güvenli alım" bölgesidir.
        fiyat = self.veri.get('guncel_fiyat', 0)
        maliyet = self.veri.get('kurumsal_maliyet', self.veri.get('ilk_5_maliyet', 0))
        
        if fiyat > 0 and maliyet > 0:
            mesafe = (fiyat - maliyet) / maliyet
            if mesafe <= 0.03: # %3'ten az uzaklık
                self.skor += 15
                self.sinyaller.append(f"🎯 Güvenli Bölge (Maliyetten Sadece %{round(mesafe*100, 1)} Uzak)")
            elif mesafe > 0.10: # %10'dan fazla kar edilmişse düzeltme gelebilir
                self.skor -= 10
                self.sinyaller.append("📉 Kar Satışı Riski (Maliyetin %10 Üstü)")

        # --- Modül 6: Fiyat/Takas Uyumsuzluğu (Divergence) ---
        # Fiyat düşerken takasın bu kadar iyi olması DİP dönüşünün en büyük kanıtıdır.
        fiyat_trend = self.veri.get('fiyat_trend', 0)
        fiyat_degisim = self.veri.get('fiyat_degisim', 0) # Günlük yüzde değişim
        ilk_3_pay = self.veri.get('ilk_3_alici_payi', 0)
        
        # Kullanıcının özel "Düşüşte Mal Toplama" filtresi
        if fiyat_degisim < -1.5:
             if diger_satici > 45 and ilk_3_pay > 60:
                 self.skor += 30
                 self.sinyaller.append("🔥 GÜÇLÜ POZİTİF UYUMSUZLUK: Fiyat Düşerken Kurumsal Toplama")
        
        if fiyat_trend <= 0 and self.skor > 50:
            self.skor += 25
            self.sinyaller.append("🚀 KRİTİK: Dipte Mal Toplanıyor (Profesyonel Akümülasyon)")

        # Maliyet Teyidi (Ekstra)
        if fiyat > 0 and maliyet > 0 and fiyat < maliyet * 1.02:
            self.skor += 10
            self.sinyaller.append("🛡️ DESTEK BÖLGESİ: Kurumsal maliyete çok yakın")

        return self.sonuc_getir()

    def sonuc_getir(self) -> Dict:
        """Sonucu normalize eder ve karara bağlar."""
        # 0 - 100 arası normalize et (Skor bazen 100'ü geçebilir)
        final_puan = max(0, min(100, self.skor))
        
        durum = "GÜÇLÜ AL" if final_puan > 75 else "AL" if final_puan > 55 else "İZLE" if final_puan > 35 else "UZAK DUR / SAT"
        
        return {
            "hisse": self.veri.get('hisse_adi', '-'),
            "takas_puani": round(final_puan, 1),
            "takas_karari": durum,
            "sinyaller": self.sinyaller,
            "takas_detay": " | ".join(self.sinyaller) if self.sinyaller else "-"
        }


def get_takas_score(hisse: str, market: str = "BIST") -> Dict:
    """
    Dışarıdan çağrılacak ana fonksiyon. BIST dışındaki piyasalar için nötr döner.
    """
    if market != "BIST":
        return {"takas_puani": 0, "takas_karari": "-", "sinyaller": []}
    
    # Gerçek veri çekici entegre edilene kadar simülasyon/örnek verisi (Veya API ile bağlanacak)
    # TODO: isyatirimhisse veya başka bir kaynaktan gerçek AKD çekilecek.
    
    # Şimdilik örnek veri döner (Veya DB'den en son kaydedileni çeker)
    # (Bu kısım data_fetcher.py içinde geliştirilecek)
    return {"takas_puani": 0, "takas_karari": "VERİ BEKLENİYOR", "sinyaller": []}


if __name__ == "__main__":
    test_veri = {
        'hisse_adi': 'THYAO',
        'ilk_5_alici_oran': 82.0,
        'ilk_5_satici_oran': 45.0,
        'diger_alici_oran': 18.0,
        'diger_satici_oran': 55.0,
        'ana_alicilar': [{'ad': 'CITIBANK', 'toplam_takas_payi': 0.32}, {'ad': 'YATIRIM FONLARI', 'toplam_takas_payi': 0.15}],
        'guncel_fiyat': 282.0,
        'ilk_5_maliyet': 279.5,
        'fiyat_trend': -0.015
    }
    
    analyzer = TakasAnalizoru(test_veri)
    print(analyzer.analiz_et())
