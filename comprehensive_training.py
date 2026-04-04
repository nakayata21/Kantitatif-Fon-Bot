
import yfinance as yf
import pandas as pd
import numpy as np
import time
import os
import json
import sqlite3
from datetime import datetime, timedelta
from constants import DEFAULT_BIST_100, DEFAULT_NASDAQ_100
from indicators import add_indicators
from signals_db import log_signal, update_label, init_db as init_signals_db, DB_PATH
from trainer_service import retrain_model
from physics_engine import get_physics_engine

# =====================================================================
# KAPSAMLI (LOGICAL) EĞİTİM AYARLARI
# =====================================================================
LOOKBACK_DAYS = 365 # 1 Tam Yıl (Daha geniş hafıza)
TP_PERCENT = 4.0    # Daha gerçekçi hedef
SL_PERCENT = 2.5    # Daha sıkı stop
MAX_DAYS = 15       # Bekleme süresi (Swing vade)
# =====================================================================

def comprehensive_training():
    print("🚀 KAPSAMLI (FULL MARKET) EĞİTİM BAŞLATILIYOR...")
    init_signals_db()
    
    # Tüm Sembolleri Al (LFM YÜKSELTMESİ: BIST 100 + GENİŞ NASDAQ)
    from constants import DEFAULT_BIST_100, DEFAULT_NASDAQ_100
    symbols_bist = [f"{s}.IS" for s in DEFAULT_BIST_100]
    symbols_nasdaq = DEFAULT_NASDAQ_100 
    
    all_targets = {"BIST": symbols_bist, "NASDAQ": symbols_nasdaq}
    
    physics_engine = get_physics_engine()
    total_signals_added = 0
    
    # Veritabanı bağlantısı
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    for exchange, symbols in all_targets.items():
        print(f"\n🌐 {exchange} Piyasası Analiz Ediliyor ({len(symbols)} Hisse)...")
        from data_fetcher import fetch_quick_fundamentals
        
        for sym in symbols:
            clean_sym = sym.replace(".IS", "")
            print(f"   ⚙️ {clean_sym} işleniyor...", end="\r")
            
            # --- MANTIKLI VERİ ÇEKİMİ (RATE LIMIT & CACHE) ---
            # 1. Önce Temel Verileri Çek/Cache'le (PD/DD, Defter Değeri vb.)
            # fetch_quick_fundamentals zaten DB cache kontrolü yapar.
            try:
                fetch_quick_fundamentals(clean_sym, market=exchange)
            except: pass
            
            # Rate Limit Engeli: API'yi yormadan yavaşça ilerle
            time.sleep(random.uniform(0.8, 1.5))
            
            try:
                # 2. OHLCV Verisini İndir (TV Öncelikli, 1 Yıllık)
                try:
                    from tvDatafeed import TvDatafeed, Interval
                    tv = TvDatafeed()
                    tv_exch = "BIST" if exchange == "BIST" else "NASDAQ"
                    df = tv.get_hist(symbol=clean_sym, exchange=tv_exch, interval=Interval.in_daily, n_bars=260)
                    if df is not None and not df.empty:
                        df = df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'})
                    else:
                        raise ValueError("No TV data")
                except:
                    # Fallback to yfinance with slightly more delay
                    time.sleep(1.0)
                    df = yf.download(sym, period="1y", interval="1d", progress=False)
                
                if df is None or df.empty or len(df) < 60: continue
                
                # 2. İndikatörleri Ekle
                df = add_indicators(df)
                
                # Geçmiş Üzerinde Simüle Et
                for i in range(40, len(df) - MAX_DAYS):
                    row = df.iloc[i]
                    prev_row = df.iloc[i-1]

                    # KRİTİK FİX: Sadece sinyal anına kadar olan veriyi kullan (Forward Leak Önleme)
                    past_hist = df.iloc[:i+1] # T'ye kadar olan kısım
                    phys_row = physics_engine.extract(past_hist)
                    
                    # Mantıklı Sinyal Kriterleri (Hybrid)
                    is_signal = False
                    
                    # 1. Stoch RSI + BB Sıkışması
                    if row.get('stoch_k', 50) < 20 and row.get('stoch_k', 50) > row.get('stoch_d', 0): is_signal = True
                    # 2. Hacimli Kırılım + Trend
                    if row['vol_spike'] > 1.8 and row['close'] > row['ema20'] and row['adx'] > 25: is_signal = True
                    # 3. Fiziksel Momentum Patlaması
                    if phys_row.get('momentum_velocity_ratio', 0) > 1.2: is_signal = True

                    if is_signal:
                        # Özellikleri Paketle
                        features = {
                            "rsi": float(row['rsi']),
                            "macd_hist": float(row['macd_hist']),
                            "adx": float(row['adx']),
                            "atr_pct": float(row['atr_pct']),
                            "vol_spike": float(row['vol_spike']),
                            "ema20_slope": float(row.get('ema20_slope', 0)),
                            "bb_width": float(row.get('bb_width', 5)),
                            "roc20": float(row.get('roc20', 0)),
                            # --- AI SUPER FEATURES (PHASE 10) ---
                            "feat_rsi_mom": float(row.get('feat_rsi_mom', 0)),
                            "feat_vol_atr": float(row.get('feat_vol_atr', 0)),
                            "feat_trend_strength": float(row.get('feat_trend_strength', 0)),
                            "feat_order_imbalance_proxy": float(row.get('feat_order_imbalance_proxy', 0)),
                            "stat_arb_zscore": float(row.get('stat_arb_zscore', 0.0)),
                        }
                        # Fizik özelliklerini ekle (phys_ önekiyle sakla)
                        for k, v in phys_row.items():
                            features[f"phys_{k}"] = float(v)
                        
                        signal_time = df.index[i]
                        entry_price = float(row['close'])
                        feat_json = json.dumps(features)
                        
                        c.execute(
                            "INSERT INTO signals (symbol, exchange, time_at_signal, price_at_signal, signal_type, features) VALUES (?, ?, ?, ?, ?, ?)",
                            (clean_sym, exchange, signal_time.isoformat(), entry_price, "COMPREHENSIVE", feat_json)
                        )
                        signal_id = c.lastrowid
                        
                        # GELECEK ÜZERİNDEN ETİKETLE
                        future_bars = df.iloc[i+1 : i+1+MAX_DAYS]
                        tp_level = entry_price * (1 + TP_PERCENT/100)
                        sl_level = entry_price * (1 - SL_PERCENT/100)
                        
                        outcome = None
                        label_type = "TIME"
                        max_p = float(future_bars['High'].max())
                        min_p = float(future_bars['Low'].min())
                        last_c = float(future_bars['Close'].iloc[-1])
                        
                        for _, f_row in future_bars.iterrows():
                            if f_row['High'] >= tp_level:
                                outcome = ((f_row['High'] - entry_price) / entry_price) * 100
                                label_type = "TP"
                                break
                            if f_row['Low'] <= sl_level:
                                outcome = ((f_row['Low'] - entry_price) / entry_price) * 100
                                label_type = "SL"
                                break
                        
                        if outcome is None: 
                            outcome = ((last_c - entry_price) / entry_price) * 100
                            label_type = "TIME"
                        
                        c.execute(
                            "UPDATE signals SET outcome=?, is_labeled=1, label_time=?, label_type=?, max_price=?, min_price=? WHERE id=?",
                            (outcome, datetime.now().isoformat(), label_type, max_p, min_p, signal_id)
                        )
                        total_signals_added += 1
                        
                conn.commit()
                
            except Exception as e:
                # print(f"      ❌ Hata ({clean_sym}): {e}")
                continue

    conn.close()
    print(f"\n✅ Toplam {total_signals_added} adet YÜKSEK KALİTELİ tecrübe eklendi.")
    
    if total_signals_added > 50:
        print("🧠 KOMPLEKS AI EĞİTİMİ (DEEP LEARNING SWEEP) BAŞLATILIYOR...")
        # trainer_service içindeki retrain_model normalde çok kapsamlıdır. 
        # Onu burada çağırdığımızda tüm Optuna denemelerini yapacaktır.
        retrain_model()
        
        # --- 🛡️ ANOMALİ DEDEKTÖRÜLÜ (AUTOENCODER) EĞİTİMİ ---
        print("🛡️ ANOMALİ DEDEKTÖRÜ (Autoencoder) Güncelleniyor...")
        from anomaly_detector import train_anomaly_detector_from_db
        train_anomaly_detector_from_db()
        
        print("🎉 AI Modeli ve Otokodlayıcı en kapsamlı verilerle (BIST+NASDAQ 1 Yıl) eğitildi ve mükemmelleştirildi!")
    else:
        print("⚠️ Yeterli veri toplanamadı.")

if __name__ == "__main__":
    comprehensive_training()
