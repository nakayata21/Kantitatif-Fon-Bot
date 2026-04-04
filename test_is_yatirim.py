
import os
import json
import pandas as pd
from data_fetcher import fetch_quick_fundamentals

def test_fundamentals():
    # Test edilecek hisseler
    test_symbols = ['THYAO', 'ASELS', 'EREGL']
    print('🔍 IS YATIRIM TEMEL VERI DOGRULAMA TESTI (CANLI)\n' + '='*60)

    for sym in test_symbols:
        try:
            # fetch_quick_fundamentals içindeki isyatirim.com.tr motorunu çağırır
            res = fetch_quick_fundamentals(sym, 'BIST')
            
            if not res or res.get('error'):
                err_msg = res.get("error", "Bilinmeyen hata") if res else "Veri çekilemedi"
                print('❌ {}: Hata - {}'.format(sym, err_msg))
            else:
                print('✅ {} Verileri Yakalandı:'.format(sym))
                print('   - F/K (P/E): {} (İstenen Aralık: 0-60)'.format(res.get("pe_ratio", "-")))
                print('   - PD/DD (P/B): {}'.format(res.get("pb_ratio", "-")))
                print('   - Bilanço Puanı (İş Yatırım): {}'.format(res.get("isy_score", "-")))
                print('   - Önerilen Derece: {}'.format(res.get("isy_grade", "-")))
                # Yeni kural kontrolü
                pe = res.get("pe_ratio")
                if pe is not None:
                    if 0 <= pe <= 60:
                        print('   🛡️  DURUM: KURALA UYGUN ✅')
                    else:
                        print('   🚨  DURUM: KURALA UYGUN DEGİL (ELENECEK) ❌')
                print('-'*60)
        except Exception as e:
            print('⚠️ {} taranırken sistem hatası oluştu: {}'.format(sym, str(e)))

if __name__ == '__main__':
    test_fundamentals()
