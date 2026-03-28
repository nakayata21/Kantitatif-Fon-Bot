
import yfinance as yf
import pandas as pd
import numpy as np
import time
import os
import json
from datetime import datetime, timedelta
from constants import DEFAULT_BIST_30, DEFAULT_NASDAQ_HISSELER
from indicators import add_indicators
from signals_db import log_signal, update_label, init_db as init_signals_db
from trainer_service import retrain_model

# =====================================================================
# HIZLANDIRILMIŞ EĞİTİM AYARLARI
# =====================================================================
LOOKBACK_DAYS = 65  # Ne kadar geriden başlayıp simüle edelim?
TP_PERCENT = 5.0    # Başarı kriteri
SL_PERCENT = 3.0    # Kayıp kriteri
MAX_DAYS = 10       # Hedefe ulaşma süresi
# =====================================================================

def bootstrap_training():
    print("🚀 AI Hızlandırılmış Eğitim (Bootstrap) Başlatılıyor...")
    init_signals_db()
    
    # BİST30 ve NASDAQ'tan ana hisseleri al
    symbols_bist = [f"{s}.IS" for s in DEFAULT_BIST_30[:20]]
    symbols_nasdaq = DEFAULT_NASDAQ_HISSELER[:20]
    
    all_targets = {"BIST": symbols_bist, "NASDAQ": symbols_nasdaq}
    
    total_signals_added = 0
    
    for exchange, symbols in all_targets.items():
        print(f"\n🌐 {exchange} Piyasası Verileri Toplanıyor...")
        
        for sym in symbols:
            clean_sym = sym.replace(".IS", "")
            print(f"   📈 {clean_sym} inceleniyor...")
            
            try:
                # 1. Veriyi İndir (TradingView Öncelikli)
                from tvDatafeed import TvDatafeed, Interval
                tv = TvDatafeed()
                tv_exch = "BIST" if exchange == "BIST" else "NASDAQ"
                df = tv.get_hist(symbol=clean_sym, exchange=tv_exch, interval=Interval.in_daily, n_bars=150)
                
                if df is not None and not df.empty:
                    # Sütunları standart formata uyarla
                    df = df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'})
                else:
                    # Fallback to yfinance
                    print(f"      ⚠️ {clean_sym} TV'den alınamadı, Yahoo deneniyor...")
                    df = yf.download(sym, period="4mo", interval="1d", progress=False)
                
                if df is None or df.empty or len(df) < 40: continue
                
                # 2. İndikatörleri Ekle
                df = add_indicators(df)
                
                # 3. Geçmiş Üzerinde Simüle Et
                # Sinyallerin oluşabileceği bir aralık seç (son 10 gün hariç, çünkü sonuç belli olmalı)
                for i in range(30, len(df) - MAX_DAYS):
                    row = df.iloc[i]
                    prev_row = df.iloc[i-1]
                    
                    # Basit "Sinyal" kriterleri (Eğitim verisi üretmek için yapay sinyaller)
                    # Gerçek sinyal algoritmalarımızdan bazılarını simüle edelim
                    is_signal = False
                    
                    # RSI Reversal
                    if prev_row['rsi'] < 35 and row['rsi'] > 35: is_signal = True
                    # MACD Cross
                    if prev_row['macd_hist'] <= 0 and row['macd_hist'] > 0: is_signal = True
                    # Vol Spike + Trend
                    if row['vol_spike'] > 1.5 and row['close'] > row['ema20']: is_signal = True
                    
                    if is_signal:
                        # Bu hisse için bu tarihteki teknik özellikleri paketle
                        features = {
                            "rsi": float(row['rsi']),
                            "macd_hist": float(row['macd_hist']),
                            "adx": float(row['adx']),
                            "atr_pct": float(row['atr_pct']),
                            "vol_spike": float(row['vol_spike']),
                            "ema20_slope": float(row.get('ema20_slope', 0)),
                            "bb_width": float(row.get('bb_width', 5)),
                            "roc20": float(row.get('roc20', 0)),
                        }
                        
                        # Sinyali veritabanına "geçmiş tarihli" olarak kaydet
                        signal_time = df.index[i]
                        entry_price = float(row['close'])
                        
                        # signals_db içindeki log_signal'i kullan
                        # Not: signals_db.py'de log_signal'e signal_time parametresi eklemiştim.
                        from signals_db import DB_PATH
                        import sqlite3
                        conn = sqlite3.connect(DB_PATH)
                        c = conn.cursor()
                        feat_json = json.dumps(features)
                        
                        c.execute(
                            "INSERT INTO signals (symbol, exchange, time_at_signal, price_at_signal, signal_type, features) VALUES (?, ?, ?, ?, ?, ?)",
                            (clean_sym, exchange, signal_time.isoformat(), entry_price, "BOOTSTRAP", feat_json)
                        )
                        signal_id = c.lastrowid
                        conn.commit()
                        
                        # 4. SONUCU ETİKETLE (Geleceği bildiğimiz için hemen şimdi)
                        future_bars = df.iloc[i+1 : i+1+MAX_DAYS]
                        tp_level = entry_price * (1 + TP_PERCENT/100)
                        sl_level = entry_price * (1 - SL_PERCENT/100)
                        
                        outcome = None
                        label_type = "TIME"
                        max_p = float(future_bars['high'].max())
                        min_p = float(future_bars['low'].min())
                        last_c = float(future_bars['close'].iloc[-1])
                        
                        # Triple Barrier Kontrolü
                        for _, f_row in future_bars.iterrows():
                            if f_row['high'] >= tp_level:
                                outcome = ((f_row['high'] - entry_price) / entry_price) * 100
                                label_type = "TP"
                                break
                            if f_row['low'] <= sl_level:
                                outcome = ((f_row['low'] - entry_price) / entry_price) * 100
                                label_type = "SL"
                                break
                        
                        if outcome is None: # Zaman aşımı
                            outcome = ((last_c - entry_price) / entry_price) * 100
                            label_type = "TIME"
                        
                        # Veritabanında güncelle
                        # update_label(signal_id, outcome, label_type, max_p, min_p)
                        c.execute(
                            "UPDATE signals SET outcome=?, is_labeled=1, label_time=?, label_type=?, max_price=?, min_price=? WHERE id=?",
                            (outcome, datetime.now().isoformat(), label_type, max_p, min_p, signal_id)
                        )
                        conn.commit()
                        conn.close()
                        
                        total_signals_added += 1
                        
                time.sleep(0.5) # API koruması
                
            except Exception as e:
                print(f"      ❌ Hata ({clean_sym}): {e}")
                continue

    print(f"\n✅ Toplam {total_signals_added} adet geçmiş tecrübe (sinyal) veritabanına eklendi.")
    
    if total_signals_added > 20:
        print("🧠 AI Modeli Eğitiliyor (Retraining)...")
        retrain_model()
        print("🎉 AI Modeli başarıyla uyanmış ve tecrübe kazanmıştır!")
    else:
        print("⚠️ Yeterli sinyal üretilemedi, eğitim ertelendi.")

if __name__ == "__main__":
    bootstrap_training()
