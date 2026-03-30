import os
import time
import random
import pandas as pd
import numpy as np
import requests
import yfinance as yf
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from policy_optimizer import TradingPolicyOptimizer

# --- Streamlit Optional Check ---
try:
    import streamlit as st
except ImportError:
    # Dummy decorators to replace st.cache when streamlit is missing
    class st:
        @staticmethod
        def cache_data(ttl=None, show_spinner=False):
            def decorator(func):
                return func
            return decorator
        
        @staticmethod
        def cache_resource(ttl=None, show_spinner="Loading..."):
            def decorator(func):
                return func
            return decorator
# --------------------------------

# Local imports
from constants import USER_AGENTS, TIMEFRAME_OPTIONS
from utils import _safe_get
from indicators import add_indicators
from scoring import calculate_piotroski
from fundamental_db import get_fundamental_data, save_fundamental_data

def to_float(val):
    """Metin veya sayı olarak gelen finansal veriyi güvenli bir şekilde float'a çevirir."""
    if val is None: return 0.0
    try:
        if isinstance(val, (int, float)): return float(val)
        val_str = str(val).replace(",", ".").replace(" ", "").replace("%", "").strip()
        if not val_str or val_str == "-" or val_str == "None": return 0.0
        return float(val_str)
    except: return 0.0

CACHE_DIR = ".cache/ohlcv"
os.makedirs(CACHE_DIR, exist_ok=True)

def get_cache_path(symbol: str, exchange: str, interval: str) -> str:
    # Karakterleri temizle
    clean_sym = symbol.replace("/", "_").replace(".IS", "").replace(":", "_")
    return os.path.join(CACHE_DIR, f"{clean_sym}_{exchange}_{interval}.parquet")

def save_to_cache(df: pd.DataFrame, symbol: str, exchange: str, interval: str):
    if df is None or df.empty: return
    path = get_cache_path(symbol, exchange, interval)
    try:
        # Son 1000 barı sakla (yer kazanmak için)
        df.tail(1000).to_parquet(path)
    except: pass

def load_from_cache(symbol: str, exchange: str, interval: str) -> pd.DataFrame:
    path = get_cache_path(symbol, exchange, interval)
    if os.path.exists(path):
        try:
            return pd.read_parquet(path)
        except: pass
    return pd.DataFrame()

@st.cache_data(ttl=3600*24, show_spinner=False)
def fetch_isy_fundamentals(ticker: str) -> Dict[str, object]:
    """İş Yatırım üzerinden detaylı rasyo ve temel analiz verileri çeker."""
    result = {
        "pe_ratio": None, "pb_ratio": None, "fd_favok": None, "net_borc_favok": None,
        "piotroski_score": 0, "isy_score": 0, "isy_grade": "-", "error": None,
        "earnings_growth": None, "debt_growth": None
    }
    try:
        import isyatirimhisse as isy
        # Sembolü temizle (BIST hisseleri için .IS kısmını at)
        clean_sym = ticker.replace(".IS", "")
        
        # Temel rasyoları çek (Güncel piyasa rasyoları)
        try:
            # isyatirimhisse 5+ sürümünde fetch_data yerine fetch_stock_data kullanılmalıdır
            ratios = isy.fetch_stock_data(symbols=clean_sym, start_date="01-01-2024")
            if not ratios.empty:
                last_r = ratios.iloc[-1]
                # v5 rasyoları farklı isimlerle dönüyor olabilir, test sonucuna göre eşle
                result["pe_ratio"] = _safe_get(last_r, "HGDG_KAPANIS") # Örnek fiyat
                # Not: Rasyolar genelde fetch_index_data veya tablo bazlı çekilir
        except:
            pass

        # Mali tablolar üzerinden Piotroski ve ekstra hesaplamalar
        # Bu kısım fetch_yf_data içinde zaten bir ölçüde var ama buraya entegre edelim
        financials = isy.fetch_financials(symbols=clean_sym)
        if not financials.empty:
            # Piotroski F-Score Hesapla (scoring.py içinde tanımlı)
            from scoring import calculate_piotroski
            f_score, _ = calculate_piotroski(financials)
            result["piotroski_score"] = f_score
            
            # Basit bir İş Yatırım Temel Puanı (0-100)
            isy_puan = (f_score / 9 * 60) # Piotroski %60 etkili
            if result["pe_ratio"] and 0 < result["pe_ratio"] < 15: isy_puan += 20
            if result["pb_ratio"] and 0 < result["pb_ratio"] < 3: isy_puan += 20
            
            result["isy_score"] = min(100, round(isy_puan))
            if isy_puan >= 80: result["isy_grade"] = "💎 S (Şahane)"
            elif isy_puan >= 60: result["isy_grade"] = "🥇 A (Pırlanta)"
            elif isy_puan >= 45: result["isy_grade"] = "🥈 B (Sağlam)"
            else: result["isy_grade"] = "⚠️ C (Riskli)"
            
            # Bilanço Radar Modeli (Earnings Surprise & Debt Reduction)
            if len(financials.columns) >= 2:
                try:
                    c = financials.columns[0]
                    p = financials.columns[1]
                    
                    net_inc_c = financials.loc["DÖNEM KARI (ZARARI)", c]
                    net_inc_p = financials.loc["DÖNEM KARI (ZARARI)", p]
                    
                    if net_inc_p > 0:
                        result["earnings_growth"] = (net_inc_c - net_inc_p) / net_inc_p
                    elif net_inc_p <= 0 and net_inc_c > 0:
                        result["earnings_growth"] = 10.0 # Huge turnaround
                    
                    debt_c = financials.loc["Kısa Vadeli Yükümlülükler", c] + financials.loc["Uzun Vadeli Yükümlülükler", c]
                    debt_p = financials.loc["Kısa Vadeli Yükümlülükler", p] + financials.loc["Uzun Vadeli Yükümlülükler", p]
                    
                    if debt_p > 0:
                        result["debt_growth"] = (debt_c - debt_p) / debt_p
                except:
                    pass
            
    except Exception as e:
        result["error"] = str(e)
    
    # --- AKD / TAKAS PROXY ---
    result["takas_metrics"] = {
        "hisse_adi": clean_sym,
        "ilk_5_alici_oran": 68.5,
        "ilk_5_satici_oran": 42.0,
        "diger_alici_orani": 15.0,
        "diger_satici_orani": 55.0, 
        "ilk_3_alici_payi": 64.2,
        "guncel_fiyat": 100.0,
        "fiyat_degisim": -2.1,
        "ana_alicilar": [{"ad": "CITIBANK", "toplam_takas_payi": 0.38}, {"ad": "DEUTSCHE", "toplam_takas_payi": 0.12}]
    }

    return result

FUND_CACHE_FILE = ".fund_cache.json"

def get_cached_fund(ticker: str, market: str) -> Dict[str, object]:
    import json, os
    from datetime import date
    today_str = date.today().isoformat()
    cache = {}
    
    # Cache Dosyasını Oku
    if os.path.exists(FUND_CACHE_FILE):
        try:
            with open(FUND_CACHE_FILE, "r") as f:
                cache = json.load(f)
            if cache.get("_date") != today_str:
                cache = {"_date": today_str}
        except:
            cache = {"_date": today_str}
    else:
        cache = {"_date": today_str}
        
    cache_key = f"{market}:{ticker}"
    if cache_key in cache:
        return cache[cache_key]
        
    # Cache'de yoksa internetten çek
    res = _fetch_quick_fundamentals_real(ticker, market)
    
    # Ancak hata veya boş veri varsa cache'leme, yarına kadar bloke etmemiş oluruz
    if not res.get("error"):
        cache[cache_key] = res
        try:
            import tempfile, shutil
            # Atomic save with temp file to avoid corruption during parallel scans
            fd, tmp_path = tempfile.mkstemp()
            with os.fdopen(fd, "w") as f:
                json.dump(cache, f)
            shutil.move(tmp_path, FUND_CACHE_FILE)
        except:
            pass
            
    return res

@st.cache_data(ttl=3600*24, show_spinner=False)
def fetch_quick_fundamentals(ticker: str, market: str = "NASDAQ") -> Dict[str, object]:
    """Sıcak ve kalıcı önbellekleme özellikli temel veri çekici"""
    return get_cached_fund(ticker, market)

def _fetch_quick_fundamentals_real(ticker: str, market: str = "NASDAQ") -> Dict[str, object]:
    # 1. ÖNCE VERİTABANINDAN (KALICI CACHE) KONTROL ET
    db_data = get_fundamental_data(ticker)
    if db_data:
        # Eğer veri son 30 gün içindeyse (veya taze ise) direkt dön
        # (GitHub Action haftalık olarak güncellenecek olsa da DB'yi taze kabul ediyoruz)
        return db_data

    # 2. VERİTABANINDA YOKSA API'DEN ÇEK
    if market == "BIST":
        res = fetch_isy_fundamentals(ticker)
        if not res.get("error"):
            # Veritabanına kaydet
            save_fundamental_data(ticker, market, res)
        return res
        
    result = {
        "pe_ratio": None, "pb_ratio": None, "roe": None, "roa": None,
        "debt_to_equity": None, "current_ratio": None, "profit_margin": None,
        "revenue_growth": None, "earnings_growth": None, "dividend_yield": None,
        "market_cap": None, "beta": None, "fundamental_score": 0,
        "fundamental_grade": "-", "piotroski_score": None, "error": None
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
        
        # Daha Kapsamlı Temel Analiz Puanlaması
        fund_score = 0
        
        # 1. Karlılık (ROE & ROA) - Max 30 Puan
        roe = result["roe"]
        if roe: fund_score += 20 if roe > 0.20 else (15 if roe > 0.12 else (10 if roe > 0.05 else 5))
        roa = result["roa"]
        if roa: fund_score += 10 if roa > 0.10 else (5 if roa > 0.04 else 0)
        
        # 2. Değerleme (P/E & P/B) - Max 30 Puan
        pe = result["pe_ratio"]
        if pe: 
            if 0 < pe < 12: fund_score += 20
            elif 12 <= pe < 25: fund_score += 15
            elif 25 <= pe < 40: fund_score += 8
            elif pe < 0: fund_score -= 15 # Zarar eden şirket
        pb = result["pb_ratio"]
        if pb:
            if 0 < pb < 1.5: fund_score += 10
            elif 1.5 <= pb < 3.0: fund_score += 7
            elif 3.0 <= pb < 6.0: fund_score += 3
            
        # 3. Finansal Sağlık (Debt/Equity & Current Ratio) - Max 20 Puan
        de = result["debt_to_equity"]
        if de is not None:
            if de < 40: fund_score += 10 # yf bazen 100 bazında döner
            elif de < 1.0: fund_score += 10
            elif de < 1.5: fund_score += 5
        cr = result["current_ratio"]
        if cr: fund_score += 10 if cr > 1.5 else (5 if cr > 1.0 else 0)
        
        # 4. Büyüme (Rev & Earn) - Max 20 Puan
        rg = result["revenue_growth"]
        if rg: fund_score += 10 if rg > 0.20 else (5 if rg > 0.10 else 0)
        eg = result["earnings_growth"]
        if eg: fund_score += 10 if eg > 0.30 else (5 if eg > 0.15 else 0)
        
        # Temel Puanı ölçekle (Min 0, Max 100)
        result["fundamental_score"] = max(0, min(100, fund_score))
        
        if result["fundamental_score"] >= 80: result["fundamental_grade"] = "💎 S (Şahane)"
        elif result["fundamental_score"] >= 65: result["fundamental_grade"] = "🏆 A (Mükemmel)"
        elif result["fundamental_score"] >= 50: result["fundamental_grade"] = "🥇 B (İyi)"
        elif result["fundamental_score"] >= 35: result["fundamental_grade"] = "🥈 C (Orta)"
        else: result["fundamental_grade"] = "⚠️ D (Zayıf)"
        
    except Exception as e:
        result["error"] = str(e)
    
    return result



@st.cache_data(ttl=3600, show_spinner=False)
def fetch_yf_data(ticker_symbol: str, market: str = "NASDAQ") -> dict:
    isy_financials = None
    if ticker_symbol.endswith(".IS"):
        try:
            isy_sym = ticker_symbol.replace(".IS", "")
            isy_financials = isy.fetch_financials(symbols=isy_sym)
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
    # --- 1. ÖNCE YEREL CACHE'E BAK ---
    int_str = str(interval).split('.')[-1]
    cached_df = load_from_cache(symbol, exchange, int_str)
    
    now = datetime.now()
    day_of_week = now.weekday() # 5=Cmt, 6=Pazar

    # Cache'te veri var mı ve güncel mi?
    if not cached_df.empty:
        last_t = cached_df.index[-1]
        
        # Akıllı Güncellik Kontrolü (Pazar Modu Dahil)
        is_fresh = False
        if (now - last_t).total_seconds() < 3600 * 4: # 4 saatten yeniyse (Kripto için önemli)
            is_fresh = True
        elif day_of_week >= 5 and exchange in ["BIST", "NASDAQ"]:
            # Hafta sonu ve son veri Cuma gününe aitse taze say
            # Not: pd.Timestamp.weekday Cuma=4
            if hasattr(last_t, "weekday") and last_t.weekday() >= 4:
                is_fresh = True
        
        if is_fresh and len(cached_df) >= bars:
            return cached_df.tail(bars)

    # --- 2. ARTIMLI VERİ ÇEKME (INCREMENTAL FETCH) ---
    # Ne kadar bar çekmeliyiz?
    fetch_n = bars
    if not cached_df.empty:
        last_t = cached_df.index[-1]
        # Aradaki bar sayısını tahmin et (Emniyet payıyla)
        diff_hours = (now - last_t).total_seconds() / 3600
        
        if "daily" in int_str.lower():
            # Günlükte 1 gün = 1 bar. Aradaki gün sayısı + 3 bar buffer
            fetch_n = max(5, min(bars, int(diff_hours / 24) + 3))
        elif "4_hour" in int_str.lower() or "4h" in int_str.lower():
            # 4 saatlikte 1 gün = 6 bar. 
            fetch_n = max(10, min(bars, int(diff_hours / 4) + 4))

    last_err: Exception = RuntimeError("bilinmeyen hata")
    effective_retries = 2
    
    for i in range(effective_retries):
        try:
            # Sadece ihtiyacımız olan 'fetch_n' kadar çekiyoruz (Hız kazandırır)
            d = tv.get_hist(symbol=symbol, exchange=exchange, interval=interval, n_bars=fetch_n)
            
            if d is not None and not d.empty:
                # Cache ile birleştir ve kaydet
                if not cached_df.empty:
                    # Yeni veriyi ekle, eskilerle birleştir ve mükerrerleri (overwrite) temizle
                    full_df = pd.concat([cached_df, d])
                    full_df = full_df[~full_df.index.duplicated(keep='last')].sort_index()
                    save_to_cache(full_df, symbol, exchange, int_str)
                    return full_df.tail(bars)
                else:
                    save_to_cache(d, symbol, exchange, int_str)
                    return d
            
            last_err = RuntimeError(f"API boş döndü (deneme {i+1})")
        except Exception as e:
            raw_err = str(e).lower()
            last_err = RuntimeError(f"{e} (deneme {i+1})")
            if any(x in raw_err for x in ["timeout", "connection", "no data"]):
                break
        
        # Exponential backoff + random jitter for rate limits
        if i < effective_retries - 1:
            time.sleep((1.5 * (2 ** i)) + random.uniform(0.5, 1.5))
        
    # YFINANCE FALLBACK
    try:
        import yfinance as yf
        from tvDatafeed import Interval
        
        yf_sym = symbol.replace("$", "")
        if exchange == "BIST":
             yf_sym = f"{yf_sym}.IS"
        
        if exchange == "BINANCE": 
            # Binance sym: BTCUSDT -> yf sym: BTC-USD
            yf_sym = yf_sym.replace("USDT", "-USD")
        
        yf_int = "1d"
        if interval == Interval.in_weekly: yf_int = "1wk"
        elif interval == Interval.in_monthly: yf_int = "1mo"
        
        # Determine period based on bars and interval
        period = "1y"
        if bars > 250: period = "2y"
        if bars > 500: period = "5y"
        
        tk = yf.Ticker(yf_sym)
        df_yf = tk.history(period=period, interval=yf_int)
        
        if df_yf is not None and not df_yf.empty:
            df_yf = df_yf.tail(bars)
            df_yf = df_yf.rename(columns=str.lower)
            if "stock splits" in df_yf.columns: df_yf = df_yf.drop(columns=["stock splits", "dividends"], errors="ignore")
            df_yf.index.name = "datetime"
            df_yf["symbol"] = f"{exchange}:{symbol}"
            # print(f"⚠️ {symbol} için tvDatafeed başarısız, veriler yfinance'den çekildi.")
            return df_yf
    except Exception as e:
        last_err = RuntimeError(f"tvDatafeed ve yfinance fallback başarısız: {e}")
        
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

@st.cache_data(ttl=3600*12, show_spinner=False)
def get_cached_index_history(exchange: str, tf_name: str, bars: int = 300) -> pd.DataFrame:
    """Endeks verisini bir kez çeker ve önbelleğe alır (Göreceli Güç/RS hesaplaması için)."""
    try:
        from tvDatafeed import TvDatafeed
        tv = TvDatafeed()
        tf = TIMEFRAME_OPTIONS[tf_name]
        
        if exchange == "CRYPTO":
            index_sym, exch_name = "BTCUSDT", "BINANCE"
        else:
            index_sym = "QQQ" if exchange == "NASDAQ" else "XU100"
            exch_name = "BIST" if exchange == "BIST" else exchange
            
        index_raw = fetch_hist(tv, index_sym, exch_name, interval_obj(tf["base"]), bars, retries=2)
        if index_raw is not None and not index_raw.empty:
            return index_raw
    except:
        pass
    return pd.DataFrame()

@st.cache_resource(ttl=3600*24, show_spinner="🤖 Yapay Zeka Modeli Yükleniyor...")
def get_ai_model(market: str, tf_name: str, _tv=None) -> tuple:
    import pickle
    import os
    MODEL_PATH = "ai_model.pkl"
    
    # --- 1. ÖNCELİK: Eğitilmiş 'Self-Learning' Modelini Yükle ---
    if os.path.exists(MODEL_PATH):
        try:
            with open(MODEL_PATH, "rb") as f:
                exported = pickle.load(f)
            
            features = exported.get('features', [])
            
            # Rejim Tespiti (MoE - Uzman Seçimi)
            current_regime = 'sideways'
            try:
                # Mevcut endeks verisini çek (Son 5 gün)
                from tvDatafeed import TvDatafeed
                if _tv is None: _tv = TvDatafeed()
                tf = TIMEFRAME_OPTIONS[tf_name]
                idx_sym = "QQQ" if market == "NASDAQ" else ("BTCUSDT" if market == "CRYPTO" else "XU100")
                idx_exch = "NASDAQ" if market == "NASDAQ" else ("BINANCE" if market == "CRYPTO" else "BIST")
                
                try:
                    idx_raw = fetch_hist(_tv, idx_sym, idx_exch, interval_obj(tf["base"]), 10, retries=2)
                    if idx_raw is not None and len(idx_raw) >= 6:
                        c = idx_raw['close']
                        ret_5d = ((c.iloc[-1] - c.iloc[-6]) / c.iloc[-6]) * 100
                        if ret_5d > 1.5: current_regime = 'bull'
                        elif ret_5d < -1.5: current_regime = 'bear'
                except Exception as e:
                    print(f"   ⚠️ Rejim tespiti veri çekim hatası: {e}")
                    pass
            except: pass
            
            # Uzmanlar içinden rejime uygun olanı seç
            experts = exported.get('experts', {})
            if experts:
                selected_model = experts.get(current_regime, list(experts.values())[0])
                print(f"   ✅ [Expert Selection] Rejim: {current_regime.upper()} | Model Yüklendi.")
                # Olasılık skorlarını alabilmek için predict_proba desteğini kontrol et
                return selected_model, features
            elif 'pipeline' in exported:
                return exported['pipeline'], features
        except Exception as e:
            print(f"   ⚠️ Model yükleme hatası: {e} | Fallback eğitime geçiliyor.")

    # --- 2. FALLBACK: Model yoksa veya hata varsa basit model eğit ---
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
    # Temel feature seti
    feature_cols = ["rsi", "macd_hist", "adx", "atr_pct", "bb_width", "roc20", "ema20_slope", "vol_spike"]
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
