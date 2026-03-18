
import time
import random
import pandas as pd
import numpy as np
import requests
import streamlit as st
import yfinance as yf
from typing import Dict, List, Optional, Tuple
from datetime import datetime

# Local imports
from constants import USER_AGENTS, TIMEFRAME_OPTIONS
from utils import _safe_get
from indicators import add_indicators
from scoring import calculate_piotroski

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_quick_fundamentals(ticker: str, market: str = "NASDAQ") -> Dict[str, object]:
    result = {
        "pe_ratio": None, "pb_ratio": None, "roe": None, "roa": None,
        "debt_to_equity": None, "current_ratio": None, "profit_margin": None,
        "revenue_growth": None, "earnings_growth": None, "dividend_yield": None,
        "market_cap": None, "beta": None, "fundamental_score": 0,
        "fundamental_grade": "-", "error": None
    }
    
    if market == "CRYPTO":
        result["error"] = "Kripto para temel verisi yok."
        return result
        
    try:
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        session = requests.Session()
        retry = Retry(connect=3, backoff_factor=0.5)
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        session.headers.update({"User-Agent": random.choice(USER_AGENTS)})

        yf_ticker = f"{ticker}.IS" if market == "BIST" else ticker
        tk = yf.Ticker(yf_ticker, session=session)
        info = tk.info
        
        if not info or info.get("regularMarketPrice") is None:
            info = tk.fast_info
            if not info:
                result["error"] = "Veri bulunamadı"
                return result
        
        result["pe_ratio"] = info.get("trailingPE")
        result["pb_ratio"] = info.get("priceToBook")
        result["roe"] = info.get("returnOnEquity")
        result["roa"] = info.get("returnOnAssets")
        result["debt_to_equity"] = info.get("debtToEquity")
        result["current_ratio"] = info.get("currentRatio")
        result["profit_margin"] = info.get("profitMargins")
        result["revenue_growth"] = info.get("revenueGrowth")
        result["earnings_growth"] = info.get("earningsGrowth")
        result["dividend_yield"] = info.get("dividendYield")
        result["market_cap"] = info.get("marketCap")
        result["beta"] = info.get("beta")
        
        fund_score = 0
        roe = result["roe"]
        if roe: fund_score += 15 if roe > 0.20 else (10 if roe > 0.10 else 5)
        pe = result["pe_ratio"]
        if pe: 
            if 0 < pe < 15: fund_score += 15
            elif 15 <= pe < 30: fund_score += 10
            elif pe < 0: fund_score -= 10
        de = result["debt_to_equity"]
        if de is not None: fund_score += 15 if de < 0.5 else (10 if de < 1.0 else 0)
        
        fund_score = max(0, min(100, fund_score + 20))
        result["fundamental_score"] = fund_score
        
        if fund_score >= 70: result["fundamental_grade"] = "🏆 A (Mükemmel)"
        elif fund_score >= 50: result["fundamental_grade"] = "🥇 B (İyi)"
        elif fund_score >= 30: result["fundamental_grade"] = "🥈 C (Orta)"
        else: result["fundamental_grade"] = "⚠️ D (Zayıf)"
        
    except Exception as e:
        result["error"] = str(e)
    
    return result



@st.cache_data(ttl=3600, show_spinner=False)
def fetch_yf_data(ticker_symbol: str, market: str = "NASDAQ") -> dict:
    isy_financials = None
    if ticker_symbol.endswith(".IS"):
        try:
            import isyatirimhisse as isy
            isy_sym = ticker_symbol.replace(".IS", "")
            isy_financials = isy.fetch_financials(symbols=isy_sym, exchange="TRY")
        except:
            pass
    
    last_err = None
    y_fin, y_bal, y_cf = None, None, None
    info_data = {}

    for attempt in range(3):
        try:
            session = requests.Session()
            session.headers.update({
                "User-Agent": random.choice(USER_AGENTS),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.5",
                "Accept-Language": "en-US,en;q=0.5",
                "Connection": "keep-alive"
            })
            time.sleep(random.uniform(1.0, 3.0))
            tk = yf.Ticker(ticker_symbol, session=session)
            y_fin = tk.financials
            y_bal = tk.balance_sheet
            y_cf = tk.cashflow
            try:
                info_data = tk.info
            except:
                info_data = {}
            
            if isy_financials is not None and not isy_financials.empty:
                try:
                    df_isy = isy_financials.copy()
                    df_isy = df_isy.set_index('FINANCIAL_ITEM_NAME_TR')
                    date_cols = [c for c in df_isy.columns if '/' in str(c)]
                    df_isy = df_isy[date_cols]
                    df_isy = df_isy[sorted(date_cols, reverse=True)]
                    
                    if len(df_isy.columns) >= 1:
                        latest_col = df_isy.columns[0]
                        net_profit = df_isy.loc["DÖNEM KARI (ZARARI)", latest_col]
                        total_assets = df_isy.loc["TOPLAM VARLIKLAR", latest_col]
                        equity = df_isy.loc["TOPLAM ÖZKAYNAKLAR", latest_col]
                        long_term_debt = df_isy.loc["Uzun Vadeli Yükümlülükler", latest_col]
                        
                        if total_assets > 0:
                            info_data['returnOnAssets'] = (net_profit / total_assets)
                            info_data['leverageRatioLatest'] = (long_term_debt / total_assets)
                        if equity > 0:
                            info_data['returnOnEquity'] = (net_profit / equity)
                            info_data['debtToEquity'] = (long_term_debt / equity)
                        if len(df_isy.columns) >= 2:
                            prev_col = df_isy.columns[1]
                            prev_assets = df_isy.loc["TOPLAM VARLIKLAR", prev_col]
                            prev_long_debt = df_isy.loc["Uzun Vadeli Yükümlülükler", prev_col]
                            if prev_assets > 0:
                                prev_leverage = prev_long_debt / prev_assets
                                curr_leverage = info_data.get('leverageRatioLatest', 1.0)
                                info_data['leverageScore'] = 1 if curr_leverage < prev_leverage else 0
                                info_data['leverageTrend'] = "📉 İyileşiyor" if curr_leverage < prev_leverage else "📈 Artıyor"
                        
                        f_score, f_details = calculate_piotroski(df_isy)
                        info_data['piotroskiScore'] = f_score
                        info_data['piotroskiDetails'] = f_details
                    
                    y_fin, y_bal, y_cf = df_isy, df_isy, df_isy
                except:
                    pass
            return {"info": info_data, "financials": y_fin, "balance": y_bal, "cashflow": y_cf, "error": None}
        except Exception as e:
            last_err = str(e)
            time.sleep((2 ** attempt) + random.uniform(0.5, 1.5))
            continue
    return {"error": last_err, "info": info_data, "financials": y_fin, "balance": y_bal, "cashflow": y_cf}

def interval_obj(key: str):
    from tvDatafeed import Interval
    mp = {"4h": Interval.in_4_hour, "1d": Interval.in_daily, "1w": Interval.in_weekly}
    return mp[key]

def fetch_hist(tv, symbol: str, exchange: str, interval, bars: int, retries: int = 3):
    last_err: Exception = RuntimeError("bilinmeyen hata")
    for i in range(retries):
        try:
            d = tv.get_hist(symbol=symbol, exchange=exchange, interval=interval, n_bars=bars)
            if d is not None and not d.empty:
                return d
            last_err = RuntimeError(f"API bos DataFrame dondu (deneme {i+1}/{retries})")
        except Exception as e:
            last_err = RuntimeError(f"{type(e).__name__}: {e} (deneme {i+1}/{retries})")
        time.sleep((1.0 * (2 ** i)) + random.uniform(0.2, 0.8))
    raise last_err

def check_index_health(tv, exchange: str, tf_name: str) -> bool:
    tf = TIMEFRAME_OPTIONS[tf_name]
    try:
        if exchange == "CRYPTO":
            index_sym = "BTCUSDT"
            exch_name = "BINANCE"
        else:
            index_sym = "QQQ" if exchange == "NASDAQ" else "XU100"
            exch_name = exchange
            
        index_raw = fetch_hist(tv, index_sym, exch_name, interval_obj(tf["base"]), 100, retries=2)
        if index_raw is None or index_raw.empty: return True
        index_df = add_indicators(index_raw)
        last = index_df.iloc[-1]
        is_healthy = (float(last["close"]) > float(last["sma20"])) and (float(last["close"]) > float(last["sma50"]) * 0.99)
        # Ek koruma: Index RSI aşırı alımdaysa (80+) dikkat
        if float(last["rsi"]) > 80: is_healthy = False 
        return is_healthy
    except: return True

@st.cache_resource(ttl=3600*24, show_spinner="🤖 Yapay Zeka Modeli Eğitiliyor...")
def get_ai_model(market: str, tf_name: str, _tv=None) -> tuple:
    try:
        from sklearn.ensemble import RandomForestClassifier
    except ImportError: return None, None
    if _tv is None:
        from tvDatafeed import TvDatafeed
        _tv = TvDatafeed()
    tf = TIMEFRAME_OPTIONS[tf_name]
    if market == "CRYPTO":
        sym = "BTCUSDT"
        exch_name = "BINANCE"
    else:
        sym = "QQQ" if market == "NASDAQ" else "XU100"
        exch_name = market
        
    try:
        df_raw = fetch_hist(_tv, sym, exch_name, interval_obj(tf["base"]), 2500, retries=3)
    except: return None, None
    if df_raw is None or df_raw.empty: return None, None
    df = add_indicators(df_raw)
    df["target"] = (df["close"].shift(-5) > (df["close"] * 1.02)).astype(int)
    df["ema20_dist"] = (df["close"] - df["ema20"]) / df["ema20"] * 100
    df["sma50_dist"] = (df["close"] - df["sma50"]) / df["sma50"] * 100
    feature_cols = ["rsi", "macd_hist", "adx", "atr_pct", "bb_width", "roc20", "ema20_slope", "vol_spike", "ema20_dist", "sma50_dist"]
    df = df.dropna(subset=feature_cols + ["target"])
    if len(df) < 100: return None, None
    X, y = df[feature_cols], df["target"]
    model = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42, n_jobs=-1)
    model.fit(X, y)
    return model, feature_cols

@st.cache_data(ttl=600)
def fetch_global_indices() -> Dict[str, str]:
    """Dünya endekslerini ve pariteleri çeker."""
    indices = {
        "BIST100": "XU100.IS",
        "NASDAQ": "^IXIC",
        "ALTIN (G)": "GC=F",
        "USD/TRY": "USDTRY=X"
    }
    results = {}
    for name, sym in indices.items():
        try:
            tk = yf.Ticker(sym)
            # Fast info or history
            price = tk.fast_info.get("last_price")
            if price is None:
                hist = tk.history(period="1d")
                if not hist.empty:
                    price = hist["Close"].iloc[-1]
            
            if price:
                if "GC=F" in sym: # Gram altın hesabı yaklaşığı
                    results[name] = f"{round(price, 2)} $"
                elif "USDTRY" in sym:
                    results[name] = f"{round(price, 2)} ₺"
                else:
                    results[name] = f"{round(price, 2)}"
            else:
                results[name] = "Veri Yok"
        except:
            results[name] = "Hata"
    return results
