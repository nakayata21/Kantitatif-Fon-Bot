
import pandas as pd
import numpy as np
import time
import os
import sys
from datetime import datetime, timedelta
from tvDatafeed import TvDatafeed

# Proje dizinini ekle
sys.path.append("/Users/selmanaslan/Documents/New project")

from indicators import add_indicators
from scoring import score_symbol
from signals_db import log_signal, init_db

# Mock ShapExplainer to prevent pickle errors during scoring imports
try:
    from trainer_service import ShapExplainer
except ImportError:
    class ShapExplainer: pass
import __main__
if not hasattr(__main__, 'ShapExplainer'):
    setattr(__main__, 'ShapExplainer', ShapExplainer)

from constants import DEFAULT_BIST_HISSELER, TIMEFRAME_OPTIONS
from data_fetcher import interval_obj
import yfinance as yf

def get_historical_macro(years=1.5):
    """Geçmiş makro verileri (USDTRY, Altın, Endeks) indirir ve sözlük olarak döner."""
    macros = {"USDTRY": "USDTRY=X", "GOLD": "GC=F", "XU100": "XU100.IS"}
    macro_dfs = {}

    for name, ticker in macros.items():
        try:
            df = yf.download(ticker, period=f"{int(years*365)}d", interval="1d", progress=False)
            if not df.empty:
                # Günlük değişimleri hesapla
                df['pct_change'] = df['Close'].pct_change() * 100
                macro_dfs[name] = df
        except: pass
    return macro_dfs

def run_backfill(symbol_limit=50, years=1.5):
    tv = TvDatafeed()
    init_db()
    
    # Makro verileri çek
    macro_data = get_historical_macro(years)
    
    all_symbols = DEFAULT_BIST_HISSELER[:symbol_limit]
    print(f"🚀 {len(all_symbols)} BIST Hisse Senedi + Makro Veriler Toplanıyor...")
    
    n_bars = int(years * 260) + 350
    total_signals_logged = 0
    
    for sym in all_symbols:
        try:
            print(f"📊 {sym} Analiz Ediliyor...")
            df = tv.get_hist(symbol=sym, exchange='BIST', interval=interval_obj('1d'), n_bars=n_bars)
            if df is None or df.empty: continue
            
            df_with_ind = add_indicators(df)
            valid_df = df_with_ind.dropna(subset=['rsi', 'adx', 'ema20'])
            
            for i in range(1, len(valid_df) - 15):
                row = valid_df.iloc[i]
                prev_row = valid_df.iloc[i-1]
                dt = row.name.date() # Sinyal tarihi
                
                s = score_symbol(row, prev_row, row, "BIST", index_healthy=True)
                
                if s['Sinyal'] == 'AL':
                    feature_list = ["rsi", "macd_hist", "adx", "atr_pct", "bb_width", "roc20", "ema20_slope", "vol_spike"]
                    feats = {f: float(row.get(f, 0)) for f in feature_list}
                    
                    # MAKRO VERİ EKLEME
                    for m_name, m_df in macro_data.items():
                        # O tarihteki makro değişimi bul
                        try:
                            # Tarih bazlı erişim
                            m_row = m_df.loc[m_df.index.date == dt]
                            if not m_row.empty:
                                feats[f"macro_{m_name}_change"] = float(m_row['pct_change'].iloc[0])
                            else:
                                feats[f"macro_{m_name}_change"] = 0
                        except:
                            feats[f"macro_{m_name}_change"] = 0
                    
                    price = float(row['close'])
                    log_signal(sym, "BIST", price, s['Aksiyon'], feats, signal_time=row.name)
                    total_signals_logged += 1
            
            print(f"   ✅ {sym} Tamamlandı. (Sinyal: {total_signals_logged})")
            time.sleep(0.1)
        except Exception as e:
            print(f"   ❌ {sym} Hatası: {e}")

    print(f"\n✨ Operasyon Tamamlandı! Toplam {total_signals_logged} adet geçmiş sinyal veritabanına işlendi.")
    print("👉 Şimdi 'python3 trainer_service.py' çalıştırarak etikleme ve eğitimi başlatabilirsiniz.")

if __name__ == "__main__":
    # Parametre: symbol_limit=X (Kaç hisse taranacak), years=Y (Kaç yıllık geçmiş)
    run_backfill(symbol_limit=20, years=1.5)
