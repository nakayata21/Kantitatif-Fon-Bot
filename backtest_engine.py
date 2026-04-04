
import pandas as pd
import numpy as np
import yfinance as yf
import os
import json
from datetime import datetime, timedelta
from indicators import add_indicators
from scoring import score_symbol, get_scanner_policy
from constants import DEFAULT_BIST_30
import time

# =====================================================================
# GERÇEKÇİ BACKTEST AYARLARI (REALISTIC SETTINGS)
# =====================================================================
COMMISSION = 0.0005  # %0.05 (Borsa + Aracı Kurum)
SLIPPAGE = 0.001     # %0.1 (Tahta derinliği / Fark)
TP_TARGET = 0.05      # %5 Kar Al
SL_STOP = 0.03        # %3 Zarar Kes
MAX_HOLD_DAYS = 15    # Zaman Aşımı (Bar)
# =====================================================================

def run_real_backtest(symbols=None, start_date="2025-01-01", end_date=None):
    """
    Trained model ve 'Scoring' mantığını kullanarak geçmişte işlem simülasyonu yapar.
    """
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
        
    if symbols is None:
        # BIST30'un en likit 15 hissesi üzerinde test edelim
        symbols = [f"{s}.IS" for s in DEFAULT_BIST_30[:15]]

    all_trades = []
    policy = get_scanner_policy()
    elite_thresh = policy.get("elite_threshold", 75.0)

    print(f"🚀 [BACKTEST] SİNCAP MODEL REEL SİMÜLASYON BAŞLADI")
    print(f"📅 Dönem: {start_date} - {end_date}")
    print(f"🛠️ Ayarlar: Thresh={elite_thresh}, TP=%{TP_TARGET*100}, SL=%{SL_STOP*100}, Cost=%{COMMISSION*100+SLIPPAGE*100}")
    print("-" * 60)

    for sym in symbols:
        clean_sym = sym.replace(".IS", "")
        print(f"   📈 {clean_sym} verileri çekiliyor...", end="\r")
        
        try:
            # TV'den 1 yıllık veri çek (Günlük + Haftalık)
            try:
                from tvDatafeed import TvDatafeed, Interval
                tv = TvDatafeed()
                # 1 yıl = ~250 bar (günlük), ~52 bar (haftalık)
                df = tv.get_hist(symbol=clean_sym, exchange="BIST", interval=Interval.in_daily, n_bars=300)
                df_w = tv.get_hist(symbol=clean_sym, exchange="BIST", interval=Interval.in_weekly, n_bars=100)
                
                if df is not None and not df.empty:
                    df = df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'})
                if df_w is not None and not df_w.empty:
                    df_w = df_w.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'})
            except:
                # Fallback to yfinance with delay
                time.sleep(3)
                df = yf.download(sym, start=start_date, end=end_date, interval="1d", progress=False)
                df_w = yf.download(sym, start=start_date, end=end_date, interval="1wk", progress=False)
            
            if df is None or df.empty or len(df) < 80: continue
            df = add_indicators(df)
            if df_w is not None and not df_w.empty:
                df_w = add_indicators(df_w)
            
            # 2. Zaman Serisi Üzerinde Yürü (Walk-through Backtest)
            # Sinyal tarama i=40'tan başlar (indikatör ısınma süresi)
            i = 40
            while i < len(df) - MAX_HOLD_DAYS:
                last_time = df.index[i]
                row_last = df.iloc[i]
                row_prev = df.iloc[i-1]
                
                # Haftalık teyit verisini bul (o tarihteki son kapalı haftalık bar)
                conf_bars = df_w[df_w.index <= last_time]
                if conf_bars.empty: 
                    i += 1
                    continue
                row_conf = conf_bars.iloc[-1]
                
                # MODEL SKORU AL
                # Sınıf: scoring.score_symbol(last, prev, conf_last, ...)
                result = score_symbol(row_last, row_prev, row_conf, market="BIST", index_healthy=True)
                score = result.get("Kalite", 0)
                
                # İŞLEME GİRİŞ (ENTRY)
                if score >= elite_thresh:
                    # Gerçekçi Giriş Fiyatı: Kapanış + Slippage
                    entry_price = float(row_last['Close']) * (1 + SLIPPAGE)
                    entry_time = last_time
                    
                    # Çıkış Seviyeleri
                    tp_price = entry_price * (1 + TP_TARGET)
                    sl_price = entry_price * (1 - SL_STOP)
                    
                    trade_outcome = None
                    exit_price = None
                    exit_time = None
                    hold_duration = 0
                    
                    # 3. İşlem İzleme (Trading Process)
                    for j in range(i + 1, i + 1 + MAX_HOLD_DAYS):
                        if j >= len(df): break
                        
                        current_bar = df.iloc[j]
                        hold_duration += 1
                        
                        # TP Kontrol (High görmeli)
                        if current_bar['High'] >= tp_price:
                            exit_price = tp_price * (1 - SLIPPAGE)
                            exit_time = df.index[j]
                            trade_outcome = "TARGET"
                            break
                        
                        # SL Kontrol (Low görmeli)
                        if current_bar['Low'] <= sl_price:
                            exit_price = sl_price * (1 - SLIPPAGE)
                            exit_time = df.index[j]
                            trade_outcome = "STOP"
                            break
                    
                    # Zaman Aşımı (Time Exit)
                    if trade_outcome is None:
                        exit_price = float(df.iloc[i + MAX_HOLD_DAYS]['Close']) * (1 - SLIPPAGE)
                        exit_time = df.index[i + MAX_HOLD_DAYS]
                        trade_outcome = "TIMEOUT"
                    
                    # NET PNL HESABI (Komisyonlar dahil)
                    # pnl = (exit/entry - 1) - (comm * 2)
                    raw_pnl = (exit_price - entry_price) / entry_price
                    net_pnl = raw_pnl - (COMMISSION * 2)
                    
                    all_trades.append({
                        "Symbol": clean_sym,
                        "Entry Date": entry_time,
                        "Exit Date": exit_time,
                        "Score": score,
                        "Outcome": trade_outcome,
                        "Hold": hold_duration,
                        "PnL %": round(net_pnl * 100, 2)
                    })
                    
                    # İşlem bitene kadar atla (Aynı anda aynı hissede tek işlem)
                    i = j
                
                i += 1
                
        except Exception as e:
            # print(f"Error {clean_sym}: {e}")
            continue

    print("\n" + "="*60)
    if not all_trades:
        print("❌ HİÇ İŞLEM TESPİT EDİLEMEDİ. Skor eşiği çok yüksek olabilir.")
        return

    # METRİKLER (Performance Analysis)
    trades_df = pd.DataFrame(all_trades)
    trades_df = trades_df.sort_values("Entry Date")
    
    total_trades = len(trades_df)
    win_rate = (trades_df["PnL %"] > 0).mean() * 100
    avg_pnl = trades_df["PnL %"].mean()
    total_cum_pnl = trades_df["PnL %"].sum()
    
    # Max Drawdown
    trades_df["Equity"] = (1 + trades_df["PnL %"] / 100).cumprod()
    equity = trades_df["Equity"]
    drawdown = (equity / equity.cummax()) - 1
    max_dd = drawdown.min() * 100
    
    # Sharpe (Basit Yaklaşım)
    sharpe = (trades_df["PnL %"].mean() / trades_df["PnL %"].std()) * np.sqrt(252) if len(trades_df) > 1 else 0

    print(f"📊 BACKTEST ÖZET RAPORU (Sincap Model V1)")
    print(f"------------------------------------------------------------")
    print(f"✅ Toplam İşlem Sayısı : {total_trades}")
    print(f"✅ Galibiyet Oranı (Win): %{win_rate:.2f}")
    print(f"✅ Ortalama İşlem Getirisi: %{avg_pnl:.2f}")
    print(f"✅ Toplam Kümülatif Getiri: %{total_cum_pnl:.2f}")
    print(f"✅ Sharpe Oranı        : {sharpe:.2f}")
    print(f"✅ Maksimum Drawdown   : %{max_dd:.2f}")
    print(f"------------------------------------------------------------")
    
    # Detaylı Raporu Kaydet
    trades_df.to_csv("backtest_results.csv", index=False)
    print(f"📝 Tüm işlemler 'backtest_results.csv' dosyasına kaydedildi.")
    
    return trades_df

if __name__ == "__main__":
    run_real_backtest()
