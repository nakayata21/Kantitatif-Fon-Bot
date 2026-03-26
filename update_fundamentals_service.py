import time
import random
from data_fetcher import fetch_isy_fundamentals
from fundamental_db import init_fund_db, save_fundamental_data
from constants import DEFAULT_BIST_HISSELER

def bulk_update_bist_fundamentals():
    print("🚀 BIST Temel Analiz Güncellemesi Başlatıldı...")
    init_fund_db()
    
    total = len(DEFAULT_BIST_HISSELER)
    count = 0
    errors = 0
    
    for symbol in DEFAULT_BIST_HISSELER:
        count += 1
        print(f"[{count}/{total}] {symbol} verisi çekiliyor...")
        
        try:
            # Rastgele bekleme (İş Yatırım IP engeli yememek için)
            time.sleep(random.uniform(1.2, 2.5))
            
            data = fetch_isy_fundamentals(symbol)
            if not data.get("error"):
                save_fundamental_data(symbol, "BIST", data)
                print(f"✅ {symbol} güncellendi. Skor: {data.get('fundamental_score')}")
            else:
                print(f"⚠️ {symbol} için hata: {data.get('error')}")
                errors += 1
        except Exception as e:
            print(f"❌ {symbol} işlenirken kritik hata: {e}")
            errors += 1
            
    print(f"\n📊 GÜNCELLEME TAMAMLANDI!")
    print(f"✅ Başarılı: {count - errors}")
    print(f"❌ Hatalı: {errors}")

if __name__ == "__main__":
    bulk_update_bist_fundamentals()
