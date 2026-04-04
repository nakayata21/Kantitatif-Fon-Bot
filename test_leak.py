
import sqlite3
import json
import pandas as pd
import numpy as np
from datetime import datetime
from physics_engine import get_physics_engine
from trainer_service import get_cached_history

def test_no_forward_leak():
    """
    Veritabanındaki sinyallerin özelliklerini (features), 
    sinyal anından önceki verilerle tekrar hesaplayıp karşılaştırır.
    Eğer fark varsa 'Look-Ahead Bias' (Sızıntı) var demektir.
    """
    print("🔍 VERİ SIZINTISI (FORWARD LEAK) TESTİ BAŞLATILIYOR...\n")
    
    conn = sqlite3.connect("signals_log.db")
    df_signals = pd.read_sql_query("SELECT * FROM signals WHERE is_labeled=1 LIMIT 50", conn)
    conn.close()
    
    if df_signals.empty:
        print("⚠️ Test edilecek etiketli sinyal bulunamadı.")
        return

    physics_engine = get_physics_engine()
    leaks_found = 0
    total_tested = 0

    for _, row in df_signals.iterrows():
        symbol = row['symbol']
        exchange = row['exchange']
        signal_time = pd.to_datetime(row['time_at_signal'])
        stored_features = json.loads(row['features'])
        
        # Sadece fizik özelliklerini kontrol edelim (sızıntı şüphesi burada)
        phys_keys = [k for k in stored_features.keys() if k.startswith('phys_')]
        if not phys_keys: continue
        
        total_tested += 1
        
        # 1. Ham veriyi al (Full history)
        hist = get_cached_history(symbol, exchange)
        if hist is None or hist.empty: continue
        
        # 2. Sinyal anına kadar olan kısmı KESİP features'ı tekrar hesapla (DOGRU YÖNTEM)
        # UTC/Naive karmaşasını önlemek için tz_localize(None) yapıyoruz
        hist.index = pd.to_datetime(hist.index).tz_localize(None)
        signal_time_naive = signal_time.tz_localize(None)
        
        past_hist = hist[hist.index <= signal_time_naive]
        
        # Tekrar hesapla
        recalculated_phys = physics_engine.extract(past_hist)
        
        # Karşılaştır
        is_leaking = False
        for k in phys_keys:
            # db'de 'phys_kalman_noise_ratio' iken engine 'kalman_noise_ratio' döner
            engine_key = k.replace('phys_', '')
            if engine_key in recalculated_phys:
                stored_val = stored_features[k]
                recalc_val = recalculated_phys[engine_key]
                
                # Küçük yüzer nokta farklarını görmezden gel (atol=1e-5)
                if not np.isclose(stored_val, recalc_val, atol=1e-4):
                    print(f"❌ SIZINTI TESPİT EDİLDİ! | Hisse: {symbol} | Tarih: {signal_time}")
                    print(f"   Özellik: {k}")
                    print(f"   DB'deki Değer: {stored_val} (Geleceği görüyor olabilir!)")
                    print(f"   Doğru Değer:    {recalc_val} (Sadece geçmiş veriyle)")
                    is_leaking = True
                    break
        
        if is_leaking:
            leaks_found += 1
        else:
            # print(f"✅ {symbol} ({signal_time}) - Temiz.")
            pass

    print(f"\n📊 TEST SONUCU:")
    print(f"   - Toplam Test Edilen Sinyal: {total_tested}")
    print(f"   - Sızıntı Bulunan (Hatalı):  {leaks_found}")
    
    if leaks_found > 0:
        print("\n🚨 KRİTİK UYARI: Özellik çıkarımı sırasında 'Forward Leak' (Gelecek Verisi Sızıntısı) var!")
        print("   Model geleceği görerek öğrenmiş olabilir, bu da gerçek piyasada başarısızlığa yol açar.")
    else:
        print("\n✨ TEBRİKLER: Veri sızıntısı bulunamadı. Modeliniz sağlıklı.")

if __name__ == "__main__":
    test_no_forward_leak()
