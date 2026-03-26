
import yfinance as yf
import pandas as pd
import numpy as np
import time
import os
from datetime import datetime, timedelta

def get_macro_data():
    """USD/TRY, Altın (XAU/USD) ve BIST 100 verilerini çeker."""
    macros = {
        "USDTRY": "USDTRY=X",
        "GOLD": "GC=F",
        "BIST100": "XU100.IS",
        "VIX": "^VIX"
    }
    results = {}
    try:
        for name, ticker in macros.items():
            data = yf.download(ticker, period="5d", interval="1d", progress=False)
            if not data.empty:
                # Günlük değişim yüzdesi
                last_close = data['Close'].iloc[-1].item()
                prev_close = data['Close'].iloc[-2].item()
                change = ((last_close - prev_close) / prev_close) * 100
                results[f"{name}_price"] = last_close
                results[f"{name}_change"] = change
        return results
    except Exception as e:
        print(f"Macro veri hatası: {e}")
        return {}

def calculate_market_breadth(tv, symbols):
    """Piyasa genişliğini hesaplar: Kaç hisse SMA200 üzerinde?"""
    try:
        from data_fetcher import fetch_hist, interval_obj
        above_sma200 = 0
        total = 0
        
        # Hız için sadece ilk 50 hisseye bakıyoruz (Piyasa temsili için yeterli)
        test_list = symbols[:50]
        
        for sym in test_list:
            df = fetch_hist(tv, sym, "BIST", interval_obj("1d"), 300)
            if df is not None and not df.empty:
                sma200 = df['close'].rolling(200).mean().iloc[-1]
                last_price = df['close'].iloc[-1]
                if last_price > sma200:
                    above_sma200 += 1
                total += 1
        
        breadth_ratio = (above_sma200 / total) * 100 if total > 0 else 50
        return {
            "market_breadth_sma200": breadth_ratio,
            "market_sentiment": "BULLISH" if breadth_ratio > 60 else ("BEARISH" if breadth_ratio < 40 else "NEUTRAL")
        }
    except Exception as e:
        print(f"Breadth hatası: {e}")
        return {"market_breadth_sma200": 50, "market_sentiment": "NEUTRAL"}

def get_company_financials(symbol):
    """IsYatirim üzerinden temel analiz verilerini çeker."""
    try:
        from isyatirimhisse import fetch_financials
        # Sadece son yılı çek
        year = datetime.now().year - 1
        df = fetch_financials(symbols=symbol, start_year=year, end_year=year)
        if df is not None and not df.empty:
            # Örnek: Net Kar, Satışlar vb. (Burada basitleştirilmiş bir sözlük döndürüyoruz)
            return {"has_financials": True, "data": df.to_dict()}
    except:
        pass
    return {"has_financials": False}

if __name__ == "__main__":
    print("--- Alternatif Veri Testi ---")
    print(get_macro_data())
