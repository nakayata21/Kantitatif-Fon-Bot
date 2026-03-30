from utils import clamp, _safe_get
from adaptive_weights import load_adaptive_weights
from policy_optimizer import TradingPolicyOptimizer
import numpy as np
import pandas as pd
import pickle
import os
from typing import Dict, Tuple
import json

SCAN_POLICY_PATH = "scanner_policy.json"

def get_scanner_policy() -> Dict:
    """Robotun kendi kendine belirleyeceği optimize tarama stratejisini yükler."""
    default_policy = {
        "elite_threshold": 75.0,
        "trade_ready_threshold": 60.0,
        "weights": {
            "trend": 0.25,
            "dip": 0.15,
            "breakout": 0.20,
            "alpha": 0.25,
            "volatility": 0.15
        },
        "indicators": {
            "rsi_lower": 35,
            "rsi_upper": 75,
            "bollinger_band_tightness": 0.05
        }
    }
    
    if os.path.exists(SCAN_POLICY_PATH):
        try:
            with open(SCAN_POLICY_PATH, "r", encoding="utf-8") as f:
                saved_policy = json.load(f)
                # Eksik anahtarlar varsa default'u koru
                for k, v in default_policy.items():
                    if k not in saved_policy:
                        saved_policy[k] = v
                return saved_policy
        except: pass
    return default_policy

# --- YENİ AI MODÜLLERİ (Güvenli İmport — hata olursa atlıyoruz) ---
try:
    from sentiment_analyzer import get_full_sentiment
    _SENTIMENT_OK = True
except Exception:
    _SENTIMENT_OK = False

try:
    from correlation_network import get_leading_signal, get_dominant_stocks
    _CORR_OK = True
except Exception:
    _CORR_OK = False

try:
    from order_flow import get_order_flow_score
    _ORDER_FLOW_OK = True
except Exception:
    _ORDER_FLOW_OK = False

try:
    from multi_timeframe import get_multi_timeframe_confirmation
    _MTF_ADV_OK = True
except Exception:
    _MTF_ADV_OK = False

try:
    from rl_policy import get_rl_agent
    _RL_OK = True
except Exception:
    _RL_OK = False

try:
    from physics_engine import get_physics_engine
    _PHYSICS_OK = True
except Exception:
    _PHYSICS_OK = False

try:
    from anomaly_detector import get_anomaly_detector
    _ANOMALY_OK = True
except Exception:
    _ANOMALY_OK = False

try:
    from bayesian_uncertainty import get_bayesian_validator
    _BAYESIAN_OK = True
except Exception:
    _BAYESIAN_OK = False

try:
    from takas_analyzer import TakasAnalizoru
    _TAKAS_OK = True
except Exception:
    _TAKAS_OK = False

# --- EXPERIENCE REPLAY (Hafıza ve Tecrübe Sorgulama) ---

def query_experience_memory(current_row, feature_list):
    """
    Geçmiş tecrübelerden benzer durumları bulur ve başarı oranını döner.
    """
    path = "experience_bank.pkl"
    if not os.path.exists(path): return 0.5 # Hafıza yoksa etkisiz (0.5)
    
    try:
        with open(path, "rb") as f:
            mem = pickle.load(f)
        
        # Mevcut özellikleri al ve eksik değerleri temizle (FutureWarning fix)
        current_feats = current_row[feature_list].fillna(0).infer_objects(copy=False).values.reshape(1, -1)
        mem_feats = mem['features'][feature_list].fillna(0).values
        mem_targets = mem['targets']
        
        # Basit Mesafe Ölçümü (Benzerlik)
        distances = np.linalg.norm(mem_feats - current_feats, axis=1)
        nearest_idx = np.argsort(distances)[:15] # En yakın 15 tecrübe
        
        # Geçmişteki Başarı Oranı (0 ile 1 arası)
        historical_win_rate = np.mean(mem_targets[nearest_idx])
        return historical_win_rate
    except Exception as e:
        # print(f"Memory Retrieval Error: {e}")
        return 0.5

def calculate_piotroski(df: pd.DataFrame) -> Tuple[int, Dict[str, bool]]:
    """Piotroski F-Score hesaplar (0-9 puan)"""
    score = 0
    details = {}
    try:
        if len(df.columns) < 2:
            return 0, {}
        
        c = df.columns[0] # Current
        p = df.columns[1] # Previous
        
        # 1. Karlılık (4 Puan)
        net_inc_c = df.loc["DÖNEM KARI (ZARARI)", c]
        assets_c = df.loc["TOPLAM VARLIKLAR", c]
        roa_c = net_inc_c / assets_c if assets_c > 0 else 0
        ocf_c = df.loc["İşletme Faaliyetlerinden Kaynaklanan Net Nakit", c]
        
        details['Net Kar > 0'] = bool(net_inc_c > 0)
        details['ROA > 0'] = bool(roa_c > 0)
        details['Nakit Akışı > 0'] = bool(ocf_c > 0)
        details['Nakit Akışı > Net Kar'] = bool(ocf_c > net_inc_c)
        
        score = sum([details['Net Kar > 0'], details['ROA > 0'], details['Nakit Akışı > 0'], details['Nakit Akışı > Net Kar']])
        
        # 2. Kaldıraç & Likidite (3 Puan)
        lt_debt_c = df.loc["Uzun Vadeli Yükümlülükler", c]
        lt_debt_p = df.loc["Uzun Vadeli Yükümlülükler", p]
        assets_p = df.loc["TOPLAM VARLIKLAR", p]
        lev_c = lt_debt_c / assets_c if assets_c > 0 else 0
        lev_p = lt_debt_p / assets_p if assets_p > 0 else 0
        
        cur_ast_c = df.loc["Dönen Varlıklar", c]
        cur_ast_p = df.loc["Dönen Varlıklar", p]
        cur_lib_c = df.loc["Kısa Vadeli Yükümlülükler", c]
        cur_lib_p = df.loc["Kısa Vadeli Yükümlülükler", p]
        cr_c = cur_ast_c / cur_lib_c if cur_lib_c > 0 else 0
        cr_p = cur_ast_p / cur_lib_p if cur_lib_p > 0 else 0
        
        shares_c = df.loc["Ödenmiş Sermaye", c]
        shares_p = df.loc["Ödenmiş Sermaye", p]
        
        details['Borç Oranı Azaldı'] = bool(lev_c < lev_p)
        details['Cari Oran Arttı'] = bool(cr_c > cr_p)
        details['Yeni Hisse İhracı Yok'] = bool(shares_c <= shares_p)
        
        score += sum([details['Borç Oranı Azaldı'], details['Cari Oran Arttı'], details['Yeni Hisse İhracı Yok']])
        
        # 3. Verimlilik (2 Puan)
        gross_c = df.loc["BRÜT KAR (ZARAR)", c]
        sales_c = df.loc["Satış Gelirleri", c]
        gross_p = df.loc["BRÜT KAR (ZARAR)", p]
        sales_p = df.loc["Satış Gelirleri", p]
        gm_c = gross_c / sales_c if sales_c > 0 else 0
        gm_p = gross_p / sales_p if sales_p > 0 else 0
        
        at_c = sales_c / assets_c if assets_c > 0 else 0
        at_p = sales_p / assets_p if assets_p > 0 else 0
        
        details['Marj Arttı'] = bool(gm_c > gm_p)
        details['Varlık Devir Hızı Arttı'] = bool(at_c > at_p)
        
        score += sum([details['Marj Arttı'], details['Varlık Devir Hızı Arttı']])
        
    except Exception as e:
        print(f"Piotroski Error: {e}")
        
    return score, details

def calculate_elite_score(technical: Dict, fundamental: Dict) -> Dict[str, object]:
    tech_kalite = float(technical.get("Kalite", 0))
    # tech_skor = float(technical.get("Skor", 0))
    tech_guven = float(technical.get("Guven", 0))
    tech_risk = float(technical.get("Dusus Riski", 50))
    tech_momentum = float(technical.get("Momentum Skor", 0))
    tech_breakout = float(technical.get("Breakout Skor", 0))
    tech_smart_money = float(technical.get("Smart Money Skor", 0))
    tech_konsol = float(technical.get("Konsol Skor", 0))
    sinyal = technical.get("Sinyal", "SAT")
    
    fund_score = float(fundamental.get("isy_score") if fundamental.get("isy_score") is not None else fundamental.get("fundamental_score", 0))
    fund_grade = fundamental.get("isy_grade") if fundamental.get("isy_grade") else fundamental.get("fundamental_grade", "-")
    pe = fundamental.get("pe_ratio")
    pb = fundamental.get("pb_ratio")
    roe = fundamental.get("roe")
    roa = fundamental.get("roa")
    de = fundamental.get("debt_to_equity")
    rg = fundamental.get("revenue_growth")
    eg = fundamental.get("earnings_growth")
    f_score = fundamental.get("piotroski_score", 0)
    
    tech_component = (
        (tech_kalite * 0.25) +
        (tech_momentum * 0.08) +
        (tech_breakout * 0.07) +
        (tech_smart_money * 0.05) +
        (tech_guven * 0.05)
    )
    
    if tech_risk > 70:
        tech_component *= 0.6
    elif tech_risk > 55:
        tech_component *= 0.8
    
    if sinyal == "AL":
        tech_component *= 1.15
    elif sinyal == "SAT":
        tech_component *= 0.7
    
    tech_component = min(50, tech_component)
    fund_component = fund_score * 0.5
    
    elite_bonus = 0
    elite_reasons = []
    
    if tech_kalite >= 50 and fund_score >= 60:
        elite_bonus += 10
        elite_reasons.append("💎 Teknik+Temel Uyum")
    if pe is not None and rg is not None:
        if pe < 20 and rg > 0.15:
            elite_bonus += 8
            elite_reasons.append("📈 Değer+Büyüme")
    if roe is not None and de is not None:
        if roe > 0.15 and de < 0.5:
            elite_bonus += 8
            elite_reasons.append("🏢 Kaliteli Bilanço")
    if tech_momentum >= 40 and roe is not None and roe > 0.10:
        elite_bonus += 5
        elite_reasons.append("🚀 Momentum+Kar")
    if tech_konsol >= 50 and fund_score >= 50:
        elite_bonus += 7
        elite_reasons.append("🗜️ Sıkışma+Temel")
    if tech_smart_money >= 50 and pe is not None and pe < 25:
        elite_bonus += 5
        elite_reasons.append("💰 Kurumsal+Ucuz")
    
    # Takas Bonusu
    takas_puan = float(technical.get("Takas Puani", 0))
    if takas_puan >= 75:
        elite_bonus += 12
        elite_reasons.append("🏢 GÜÇLÜ TAKAS TOPLAMA")
    elif takas_puan >= 55:
        elite_bonus += 5
        elite_reasons.append("🏦 Takas Pozitif")
        
    # Bilanço Patlaması (Earnings Surprise) & Borç Azaltımı
    debt_growth = fundamental.get("debt_growth")
    if eg is not None and eg >= 1.0:
        elite_bonus += 25
        elite_reasons.append("💥 BİLANÇO PATLAMASI (Kâr x2)")
    elif eg is not None and eg >= 0.50:
        elite_bonus += 15
        elite_reasons.append("🚀 Güçlü Kâr Büyümesi")
        
    if debt_growth is not None and debt_growth <= -0.50:
        elite_bonus += 20
        elite_reasons.append("📉 Güçlü Borç Azaltımı")
    
    elite_penalty = 0
    if pe is not None and pe < 0:
        elite_penalty += 15
    if de is not None and de > 2.0:
        elite_penalty += 10
    if rg is not None and rg < -0.10:
        elite_penalty += 8
    if eg is not None and eg < -0.20:
        elite_penalty += 8
    
    elite_score = tech_component + fund_component + elite_bonus - elite_penalty
    elite_score = max(0, min(100, elite_score))
    
    if elite_score >= 75:
        elite_grade = "💎 ELİT"
    elif elite_score >= 60:
        elite_grade = "🥇 ALTIN"
    elif elite_score >= 45:
        elite_grade = "🥈 GÜMÜŞ"
    elif elite_score >= 30:
        elite_grade = "🥉 BRONZ"
    else:
        elite_grade = "⚪ STANDART"
    
    return {
        "Elite Skor": round(elite_score, 1),
        "Elite Derece": elite_grade,
        "Teknik Bileşen": round(tech_component, 1),
        "Temel Bileşen": round(fund_component, 1),
        "Elite Bonus": round(elite_bonus, 1),
        "Elite Özellik": " | ".join(elite_reasons) if elite_reasons else "-",
        "Temel Derece": fund_grade,
        "Temel Skor": round(fund_score, 1),
        "F/K": round(pe, 1) if pe else "-",
        "ROE %": round(roe * 100, 1) if roe else "-",
        "ROA %": round(roa * 100, 1) if roa else "-",
        "Borç/Özkaynak": round(de, 2) if de else "-",
        "Gelir Büyüme %": round(rg * 100, 1) if rg else "-",
        "Kar Büyüme %": round(eg * 100, 1) if eg else "-",
        "pe_ratio": pe,
        "pb_ratio": pb,
        "isy_score": fund_score,
        "isy_grade": fund_grade,
        "piotroski_score": f_score,
        "takas_puan": takas_puan
    }

def score_symbol(last: pd.Series, prev: pd.Series, conf_last: pd.Series, market: str = "NASDAQ", index_healthy: bool = True) -> Dict[str, object]:
    # MTF ve Rejim Kontrolü (ENHANCED)
    conf_ema20 = float(_safe_get(conf_last, "ema20", 0))
    conf_ema50 = float(_safe_get(conf_last, "ema50", 0))
    conf_sma50 = float(_safe_get(conf_last, "sma50", 0))
    conf_close = float(_safe_get(conf_last, "close", 0))
    conf_macd  = float(_safe_get(conf_last, "macd_hist", 0))
    conf_rsi   = float(_safe_get(conf_last, "rsi", 50))
    conf_ema_slope = float(_safe_get(conf_last, "ema20_slope", 0))
    
    if market == "CRYPTO":
        mtf_ok = bool(conf_macd > 0)
        regime_ok = bool((_safe_get(last, "adx", 0) >= 15) and (0.3 <= _safe_get(last, "atr_pct", 0) <= 20.0))
    else:
        mtf_ok = bool(conf_ema20 > conf_ema50 and conf_macd > 0)
        regime_ok = bool((_safe_get(last, "adx", 0) >= 18) and (0.8 <= _safe_get(last, "atr_pct", 0) <= 10.0))
    
    # Mükemmel Fırtına: Haftalıkta trend BOĞA, RSI ılımlı ve EMA slope yukarı
    mtf_perfect_storm = (
        mtf_ok and 
        (conf_close > conf_sma50) and 
        (40 <= conf_rsi <= 70) and 
        (conf_ema_slope > 0)
    )

    vol_spike_val = float(_safe_get(last, "vol_spike", 0.0))
    ema20_slope   = float(_safe_get(last, "ema20_slope", 0.0))
    roc20         = float(_safe_get(last, "roc20", 0.0))
    bb_pct        = float(_safe_get(last, "bb_pct", 0.5))
    rsi_val       = float(_safe_get(last, "rsi", 50.0))
    adx_val       = float(_safe_get(last, "adx", 0.0))
    atr_pct_val   = float(_safe_get(last, "atr_pct", 5.0))
    macd_curr     = float(_safe_get(last, "macd_hist", 0.0))
    macd_prev     = float(_safe_get(prev, "macd_hist", 0.0))
    prev_rsi      = float(_safe_get(prev, "rsi", 50.0))
    
    b52w          = bool(_safe_get(last, "breakout_52w", False))
    breakout_60   = bool(_safe_get(last, "breakout_60", False))
    inst_bar      = bool(_safe_get(last, "inst_bar", False))
    ut_buy        = bool(_safe_get(last, "ut_buy", False))
    ut_pos        = int(_safe_get(last, "ut_pos", 0))
    
    bb_width_val  = float(_safe_get(last, "bb_width", 10.0))
    gap_pct_val   = float(_safe_get(last, "gap_pct", 0.0))
    sma50_val     = float(_safe_get(last, "sma50", 0.0))
    sma200_val    = float(_safe_get(last, "sma200", 0.0))
    close_val     = float(_safe_get(last, "close", 0.0))
    ema20_val     = float(_safe_get(last, "ema20", 0.0))
    ema20_dist    = ((close_val - ema20_val) / ema20_val) * 100 if ema20_val > 0 else 0.0
    bb_lower_curr = float(_safe_get(last, "bb_lower", 0.0))
    bb_lower_prev = float(_safe_get(prev, "bb_lower", 0.0))
    prev_close    = float(_safe_get(prev, "close", 0.0))
    sma20_val     = float(_safe_get(last, "sma20", 0.0))
    avg_turnover  = float(_safe_get(last, "avg_turnover_20", 0.0))
    mansfield_rs  = float(_safe_get(last, "mansfield_rs", 0.0))
    daily_return = ((close_val - prev_close) / prev_close) * 100 if prev_close > 0 else 0.0

    macd_cross_up  = (macd_curr > 0) and (macd_prev <= 0)
    bb_lower_cross = (close_val > bb_lower_curr) and (prev_close <= bb_lower_prev)
    
    if market == "CRYPTO":
        is_pump_dump = (rsi_val > 80) and (daily_return > 7.0) and (vol_spike_val < 0.8)
    else:
        is_pump_dump = (rsi_val > 72) and (daily_return > 3.0) and (vol_spike_val < 1.0)
    
    min_liquidity = 50_000_000 if market == "BIST" else (500_000 if market == "CRYPTO" else 2_000_000)
    is_liquid = avg_turnover >= min_liquidity

    # 1. TREND SKORU OPTİMİZASYONU
    trend = 0.0
    trend += 25 if ema20_val > sma50_val else 0
    trend += 10 if close_val > sma20_val else 0
    trend += 8  if macd_curr > 0 else 0
    trend += 10 if mtf_ok else 0
    trend += 8  if ema20_slope > 0.5 else (-10 if ema20_slope < -0.5 else 0)
    trend += 15 if (sma200_val > 0 and close_val > sma200_val) else 0
    trend += 12 if (sma50_val > 0 and sma200_val > 0 and sma50_val > sma200_val) else 0
    trend += 10 if (sma50_val > 0 and close_val > sma50_val) else 0
    trend += 5  if (rsi_val > 50 and rsi_val > prev_rsi) else 0
    
    # Göreceli Güç (Relative Strength) Bonusu
    trend += 15 if mansfield_rs > 0.0 else 0
    trend += 10 if mansfield_rs > 2.0 else 0


    # 2. DİP SKORU (TOPLAMA/BİRİKİM)
    support_120_val = float(_safe_get(last, "support_120", 0.0))
    ema20_prev = float(_safe_get(prev, "ema20", 0.0))
    is_rsi_oversold = rsi_val <= 32
    is_rsi_rising = (rsi_val > prev_rsi) and (rsi_val < 50)
    is_price_above_ma20 = (close_val > ema20_val) and (prev_close <= ema20_prev)
    is_near_bottom = (support_120_val > 0) and (((close_val - support_120_val) / support_120_val) * 100 <= 5.0)
    is_volume_up = (vol_spike_val >= 1.3)

    # --- Stochastic RSI Dönüşü (YENİ) ---
    stoch_k = float(_safe_get(last, "stoch_k", 50.0))
    stoch_d = float(_safe_get(last, "stoch_d", 50.0))
    prev_stoch_k = float(_safe_get(prev, "stoch_k", 50.0))
    prev_stoch_d = float(_safe_get(prev, "stoch_d", 50.0))
    
    stoch_oversold_cross = (stoch_k < 25) and (stoch_k > stoch_d) and (prev_stoch_k <= prev_stoch_d)

    dip = 0.0
    dip_signals = []
    
    dip += 25 if is_rsi_oversold else 0
    dip += 15 if is_rsi_rising else 0
    dip += 30 if stoch_oversold_cross else 0 # StochRSI Golden Cross Bonusu
    dip += 20 if macd_cross_up else 0
    dip += 15 if _safe_get(last, "pos_div", False) else 0
    dip += 15 if is_price_above_ma20 else 0
    dip += 25 if is_near_bottom else 0
    dip += 5 if is_volume_up else 0
    
    # --- Wyckoff & VSA Accumulation Bonus ---
    if bool(_safe_get(last, "is_spring", False)):
        dip += 35
        dip_signals.append("⚡ Wyckoff Spring (Ayı Tuzağı)")
    if bool(_safe_get(last, "stopping_volume", False)):
        dip += 25
        dip_signals.append("🛡️ Durduran Hacim (VSA)")
    if bool(_safe_get(last, "no_supply_test", False)):
        dip += 20
        dip_signals.append("🧪 Arzsızlık Testi (No Supply)")
    if bool(_safe_get(last, "rs_vs_market", False)):
        dip += 15
        dip_signals.append("👑 Endeksten Güçlü Dönüş")

    if bb_pct > 0.85: dip -= 40 # Aşırı ısınmışsa dip puanı kır
    
    if is_rsi_oversold: dip_signals.append("✓ RSI Aşırı Satım")
    if is_rsi_rising: dip_signals.append("✓ RSI Dönüşü")
    if stoch_oversold_cross: dip_signals.append("✓ StochRSI Dip Kesişimi")
    if macd_cross_up: dip_signals.append("✓ MACD Kesti")
    if is_price_above_ma20: dip_signals.append("✓ MA20 Kırıldı")
    if is_near_bottom: dip_signals.append("✓ Destek Bölgesi")
    if is_volume_up: dip_signals.append("✓ Alıcı Girişi")
    dip_signal_str = " | ".join(dip_signals) if dip_signals else "-"
    is_solid_bottom = dip >= 45

    # 2.1 UZUN SÜRELİ DÜŞÜŞ BİTİŞ ANALİZİ (REVERSAL)
    rev_pot = float(_safe_get(last, "reversal_potential", 0.0))
    in_bear = bool(_safe_get(last, "in_bear_market", False))
    is_cap  = bool(_safe_get(last, "is_capitulation", False))
    rev_brk = bool(_safe_get(last, "reversal_breakout", False))
    bars_below = int(_safe_get(last, "bars_below_sma200", 0))
    drop_pct = float(_safe_get(last, "drop_from_52w_high", 0.0))

    reversal_score = 0.0
    if in_bear or bars_below > 60:
        reversal_score = rev_pot
        if is_cap: reversal_score += 15
        if rev_brk: reversal_score += 25
        
    is_long_term_reversal = (reversal_score >= 65) and (drop_pct > 25)
    if is_long_term_reversal:
        dip = max(dip, reversal_score) # Dip puanını reversal puanıyla güncelle

    # 3. BREAKOUT (KIRILIM) SKORU
    breakout_up = bool(_safe_get(last, "breakout_up", False))
    breakout = 0.0
    breakout += 20 if breakout_up else 0
    breakout += 15 if (breakout_up and vol_spike_val >= 1.5) else (-10 if breakout_up and vol_spike_val < 0.8 else 0)
    breakout += 15 if (breakout_up and bb_width_val < 8.0) else 0
    breakout += 15 if b52w else 0
    breakout += 15 if breakout_60 else 0
    if market == "CRYPTO":
        breakout += 15 if daily_return > 5.0 else 0
    else:
        breakout += 12 if gap_pct_val > 2.0 else 0 
    breakout += 10 if mtf_ok else 0

    # 4. MOMENTUM SKORU
    momentum = 0.0
    momentum += 15 if macd_cross_up else 0
    momentum += 12 if _safe_get(last, "obv", 0) > _safe_get(prev, "obv", 0) else 0
    momentum += 15 if (macd_curr > 0 and macd_curr > macd_prev) else 0
    momentum += 10 if (52 <= rsi_val <= 68) else 0
    momentum += 10 if mtf_ok else 0
    momentum += 10 if roc20 > 5.0 else 0
    momentum += 10 if (ut_pos == 1) else 0

    trend    = clamp(trend)
    dip      = clamp(dip)
    breakout = clamp(breakout)
    momentum = clamp(momentum)

    # 5. SMART MONEY VE PARA AKIŞI
    above_vwap = bool(_safe_get(last, "above_vwap", False))
    smart_money = 0.0
    if market == "CRYPTO":
        smart_money += 25 if (daily_return > 3.0 and vol_spike_val >= 1.8 and close_val > prev_close) else 0
    else:
        smart_money += 25 if inst_bar else 0
    smart_money += 20 if ut_buy else 0
    smart_money += 15 if (vol_spike_val >= 2.0) else (10 if vol_spike_val >= 1.5 else 0)
    smart_money += 15 if above_vwap else -10  # VWAP üstünde = kurumsal destek
    smart_money += 10 if _safe_get(last, "higher_lows_5", False) else 0
    
    mfi_val = float(_safe_get(last, "mfi", 50.0))
    if mfi_val > 65: smart_money += 20
    elif mfi_val > 50: smart_money += 10
    elif mfi_val < 35: smart_money -= 15
    smart_money = clamp(smart_money)

    # 6. KONSOLİDASYON ANALİZİ
    range_pct_20  = float(_safe_get(last, "range_pct_20",  15.0))
    lr_slope      = float(_safe_get(last, "lr_slope_20",    0.0))
    vol_ratio_520 = float(_safe_get(last, "vol_ratio_5_20", 1.0))
    ud_vol_ratio  = float(_safe_get(last, "ud_vol_ratio",   1.0))
    pos_in_range  = float(_safe_get(last, "pos_in_20d_range", 0.5))
    bb_squeeze    = bool(_safe_get(last, "bb_squeeze", False))

    konsol = 0.0
    konsol_signals = []
    if range_pct_20 < 10:
        konsol += 25
        konsol_signals.append("✓ Ultra Dar Range")
    elif range_pct_20 < 18:
        konsol += 12
        konsol_signals.append("✓ Dar Range")

    if abs(lr_slope) < 0.6:
        konsol += 20
        konsol_signals.append("✓ Tam Yatay")
    elif abs(lr_slope) < 1.2:
        konsol += 10
        konsol_signals.append("✓ Hafif Eğim")

    if bb_squeeze:
        konsol += 20
        konsol_signals.append("✓ Bollinger Sıkışması")
    if adx_val < 20:
        konsol += 15
        konsol_signals.append("✓ Düşük Volatilite (ADX)")

    if vol_ratio_520 < 0.8:
        konsol += 10
        konsol_signals.append("✓ Hacim Kuruması")

    if ud_vol_ratio > 1.2:
        konsol += 10
        konsol_signals.append("✓ Alıcı Birikimi")

    if is_pump_dump: konsol -= 30
    if not is_liquid: konsol -= 20
    if adx_val > 35: konsol -= 20

    konsol = clamp(konsol)
    konsol_signal_str = " | ".join(konsol_signals) if konsol_signals else "-"
    if konsol >= 65: konsol_tag = "🔵 Ultra Birikim"
    elif konsol >= 45: konsol_tag = "🟡 Sıkışma"
    elif konsol >= 25: konsol_tag = "⚪ Zayıf"
    else: konsol_tag = "-"

    # 8. TAKAS VE AKD ANALİZİ (BIST için)
    takas_scr = 0.0
    takas_karar = "-"
    takas_detay = []
    
    if market == "BIST" and _TAKAS_OK:
        # data_fetcher veya signals_db'den kaydedilmiş takas verisi çekilecek
        # Şimdilik placeholders (İleride veri gelince güncellenecek)
        from fundamental_db import get_fundamental_data
        tk_data = get_fundamental_data(last.get("Hisse", ""))
        
        # Simülasyon verisi (Sadece UI'da yer açmak için, ilerde API gelince veri tabanından asıl veri gelecek)
        # Örnek: Eğer hacim spike ve trend beraberse takasın da iyi olma ihtimali yüksektir. 
        # (Bu sadece geçici bir proxy'dir, asıl veriler aracı kurumdan gelince TakasAnalizoru sınıfa asıl veri geçilecek)
        if tk_data and tk_data.get("takas_metrics"):
             try:
                 ana = TakasAnalizoru(json.loads(tk_data["takas_metrics"]))
                 res = ana.analiz_et()
                 takas_scr = res["takas_puani"]
                 takas_karar = res["takas_karari"]
                 takas_detay = res["sinyaller"]
             except: pass
        else:
             # Veri yoksa nötr ama modülün çalıştığını belli et (Simülasyon proxy: Momentum+Volume trendi)
             takas_scr = clamp(momentum * 0.4 + vol_spike_val * 10) if market == "BIST" else 0
             takas_karar = "Gözlem Altında" if takas_scr > 50 else "-"

    # 9. STAN WEINSTEIN STAGE ANALYSIS
    w_score, w_msg, w_stage_tag = score_weinstein(last, conf_last)

    # VADE VE AĞIRLIKLANDIRMA — AI modelinin öğrendikleri baz alınır
    is_long_vade = bool(sma200_val > 0 and close_val > sma200_val * 1.02)
    is_mid_vade  = bool(sma50_val  > 0 and close_val > sma50_val  * 1.01)

    # Dinamik ağırlıkları modelden al (model yoksa varsayılan değerler gelir)
    dw = load_adaptive_weights()

    if is_long_vade:
        vade = "Uzun"
        w_trend    = dw["w_trend"]    * 1.20
        w_dip      = dw["w_dip"]      * 0.50
        w_breakout = dw["w_breakout"] * 1.00
        w_momentum = dw["w_momentum"] * 0.80
        w_sm       = dw["w_sm"]       * 0.80
        w_wein     = dw["w_wein"]     * 1.50
    elif is_mid_vade:
        vade = "Orta"
        w_trend, w_dip, w_breakout, w_momentum, w_sm, w_wein = (
            dw["w_trend"], dw["w_dip"], dw["w_breakout"],
            dw["w_momentum"], dw["w_sm"], dw["w_wein"]
        )
    else:
        vade = "Kısa"
        if adx_val >= 25:  # Trend marketi
            w_trend    = dw["w_trend"]    * 0.70
            w_dip      = dw["w_dip"]      * 0.30
            w_breakout = dw["w_breakout"] * 0.90
            w_momentum = dw["w_momentum"] * 1.50
            w_sm       = dw["w_sm"]       * 1.30
            w_wein     = dw["w_wein"]     * 0.80
        else:  # Yatay market
            w_trend    = dw["w_trend"]    * 0.30
            w_dip      = dw["w_dip"]      * 2.00
            w_breakout = dw["w_breakout"] * 0.70
            w_momentum = dw["w_momentum"] * 1.00
            w_sm       = dw["w_sm"]       * 1.00
            w_wein     = dw["w_wein"]     * 0.60
    
    # 1'e normalize et
    _total = w_trend + w_dip + w_breakout + w_momentum + w_sm + w_wein + (0.1 if market=="BIST" else 0)
    if _total > 0:
        w_trend /= _total; w_dip /= _total; w_breakout /= _total
        w_momentum /= _total; w_sm /= _total; w_wein /= _total
        w_takas = (0.1 / _total if market=="BIST" else 0)

    general = clamp(
        (trend * w_trend) + (dip * w_dip) + (breakout * w_breakout) + 
        (momentum * w_momentum) + (smart_money * w_sm) + (w_score * w_wein) + (takas_scr * w_takas if market=="BIST" else 0)
    )

    # Mark Minervini Trend Template Kontrolü
    is_minervini = bool(_safe_get(last, "minervini_template", False))
    if is_minervini:
        general = clamp(general + 15) # Güçlü trend bonusu

    # 7. RİSK ANALİZİ OPTİMİZASYONU
    risk = 10.0
    risk += 20 if not regime_ok else 0
    risk += 30 if not index_healthy else 0
    risk += 35 if ema20_dist > 12.0 else (15 if ema20_dist > 7.0 else 0)
    risk += 30 if rsi_val > 78 else (15 if rsi_val > 70 else 0)
    risk += 30 if daily_return > 10.0 else (15 if daily_return > 6.0 else 0)
    risk += 40 if daily_return < -5.0 else (20 if daily_return < -3.0 else 0)
    risk += 10 if atr_pct_val > 8.0 else 0
    risk += 15 if adx_val < 12 else 0
    risk += 20 if (sma200_val > 0 and close_val < sma200_val) else 0
    risk += 40 if not is_liquid else 0
    risk += 35 if _safe_get(last, "neg_div", False) else 0
    
    # Weinstein Stage 4 ise risk artır
    if w_score < -20: risk += 25

    is_exhaustion = (rsi_val > 82) and (ema20_dist > 12.0)
    if is_exhaustion: risk += 50
    if is_pump_dump: risk += 50
    
    # Sinyal Mesafe Cezası
    sig_dist = float(_safe_get(last, "sig_entry_dist", 0.0))
    sig_bars = int(_safe_get(last, "sig_entry_bars", 0))
    if sig_dist > 6.0:
        risk += 15
        if sig_dist > 12.0:
            risk += 25
    
    risk = clamp(risk)

    confidence = clamp(20 + (25 if mtf_ok else 0) + (15 if regime_ok else 0) + (20 if ema20_slope > 0 else -10))

    # 8. KALİTE VE KARAR MEKANİZMASI
    # Kalite puanı artık riske daha duyarlı
    kalite = (general * 0.6) + (confidence * 0.4) - (risk * 0.4)
    
    # Overextension Cezası (Yakın ve Uzak Vade Şişme Kontrolü)
    overextend_penalty = 1.0
    overextend_reasons = []
    
    # 1 Yıllık ve 3 Aylık Zirve Şişme Kontrolü
    sma200_dist = ((close_val - sma200_val) / sma200_val) * 100 if sma200_val > 0 else 0.0
    sma50_dist = ((close_val - sma50_val) / sma50_val) * 100 if sma50_val > 0 else 0.0
    
    if sma200_dist > 80.0:
        overextend_penalty *= 0.3 # 1 Yılda %80'den fazla kopmuşsa büyük ceza (Tepe riski)
        overextend_reasons.append("⚠️ Yıllık Ralli (Şişik)")
    elif sma200_dist > 50.0:
        overextend_penalty *= 0.6
        overextend_reasons.append("⚠️ Uzun Vade Şişik")
        
    if sma50_dist > 35.0:
        overextend_penalty *= 0.5 # 3 Ayda çok dik çıkmışsa ceza
        overextend_reasons.append("⚠️ 3 Aylık Dik Çıkış")
        
    # Kısa Vade Şişme Kontrolü
    if ema20_dist > 10.0:
        overextend_penalty *= 0.4
        overextend_reasons.append("⚠️ Ortalamadan Uzak (EMA20)")
    if rsi_val >= 78:
        overextend_penalty *= 0.4
        overextend_reasons.append("🔴 RSI Aşırı Alım")
    if roc20 > 30.0:
        overextend_penalty *= 0.5
        overextend_reasons.append("🚀 Aylık Balon Riski")
    
    kalite *= overextend_penalty
    
    # "Sıfır Noktası" Bonusu (Taze kırılımlar için)
    if (general >= 50) and (roc20 <= 6.0) and (konsol >= 45 or is_solid_bottom):
        kalite += 35
        overextend_reasons.append("🔥 TAZE KIRILIM / BİRİKİM SONU")

    kalite = clamp(kalite)

    # KARARLAR
    if is_exhaustion or rsi_val > 85:
        decision, signal, action = "TAKE PROFIT", "SAT", "🚨 EXTREME SATIŞ BÖLGESİ"
    elif w_score <= -40 and ema20_slope < 0:
        # Şort (Aşağı Yönlü) Tarama Modülü - Aşama 4 Çöküşü
        decision, signal, action = "TRADE READY", "AÇIĞA SAT", "🔻 ŞORT (AŞAMA 4 ÇÖKÜŞÜ)"
    elif (overextend_penalty < 0.6 and daily_return > 5.0) or not is_liquid:
        decision, signal, action = "NO TRADE", "SAT", "🚫 RİSKLİ / SIĞ TAHTA"
    elif kalite >= 78:
        decision, signal = "HIGH CONVICTION", "AL"
        if is_near_bottom: action = "💎 ELMAS DİP (GÜÇLÜ AL)"
        elif b52w: action = "🚀 52 HAFTALIK ZİRVE KIRILIMI"
        elif bb_squeeze and breakout_up: action = "💥 PATLAMA (SQUEEZE BREAK)"
        else: action = "🔥 YÜKSEK GÜVENLİ AL"
    elif kalite >= 50:
        decision, signal = "TRADE READY", "AL"
        if is_long_term_reversal: action = "🔄 DÜŞÜŞ BİTİŞİ (TREND DÖNÜŞÜ)"
        elif breakout_up: action = "📈 DİRENÇ KIRILDI"
        elif is_solid_bottom: action = "📉 DİPTEN DÖNÜŞ"
        else: action = "✅ ALIM İÇİN UYGUN"
    elif w_score >= 30: # Weinstein Stage 2 Entry
        decision, signal, action = "TRADE READY", "AL", "🚀 WEINSTEIN AŞAMA 2 LİFT-OFF"
    elif kalite >= 35:
        decision, signal, action = "WATCHLIST", "BEKLE", "⌛ HACİM/ORDİNO BEKLENİYOR"
    else:
        decision, signal, action = "NO TRADE", "SAT", "❌ ZAYIF GÖRÜNÜM"

    # Stop ve Hedefler
    atr_val = float(_safe_get(last, "atr", 0.0))
    stop = max(0.0, close_val - (1.8 * atr_val))
    if is_near_bottom and support_120_val > 0: stop = min(stop, support_120_val * 0.97)
    
    risk_amt = close_val - stop
    tp1 = close_val + (1.5 * risk_amt) if risk_amt > 0 else 0
    tp2 = close_val + (2.8 * risk_amt) if risk_amt > 0 else 0
    tp3 = close_val + (4.5 * risk_amt) if risk_amt > 0 else 0
    rr = (tp1 - close_val) / risk_amt if (risk_amt > 0) else 0

    durumlar = []
    if is_long_term_reversal: durumlar.append(f"🔄 DÜŞÜŞ BİTTİ (%{round(drop_pct,1)} Düşüşten Dönüş)")
    if is_cap: durumlar.append("😱 PANİK SATIŞI (CAPITULATION) SONRASI DÖNÜŞ")
    if is_solid_bottom: durumlar.append("🚨 DİPTEN DÖNÜYOR")
    if bool(_safe_get(last, "is_spring", False)): durumlar.append("⚡ WYCKOFF SPRING")
    if bool(_safe_get(last, "stopping_volume", False)): durumlar.append("💎 DURDURAN HACİM GİRİŞİ")
    if overextend_reasons: durumlar.extend(overextend_reasons)
    if inst_bar: durumlar.append("💰 KURUMSAL GİRİŞ")
    if bb_squeeze: durumlar.append("🗜️ SIKIŞMA VAR")
    if w_msg: durumlar.append(w_msg)
    if is_minervini: durumlar.append("🚀 MINERVINI TREND TEMPLATE")
    if mansfield_rs > 0.5: durumlar.append(f"👑 ENDEKS LİDERİ (RS: {round(mansfield_rs, 1)})")
    if mtf_perfect_storm:
        durumlar.append("⛈️ MÜKEMMEL FIRTINA (Günlük+Haftalık Uyum)")
        kalite += 10
    if above_vwap: durumlar.append("🏦 VWAP ÜZERİNDE (Kurumsal Destek)")

    # Sinyal Tazelik Durumu
    sig_type = str(_safe_get(last, "sig_entry_type", "-"))
    if sig_type != "-":
        if sig_bars <= 1:
            durumlar.append(f"✨ TAZE {sig_type} SİNYALİ")
            kalite += 5
        elif sig_dist > 8.0:
            durumlar.append(f"⚠️ {sig_type} MESAFESİ AÇILDI (%{round(sig_dist,1)})")
            kalite -= 10


    # UT Bot & Divergence Fusion (ULTIMATE SIGNAL)
    is_ut_strong = ut_buy and (close_val > ema20_val) and (rsi_val > 50) and (macd_curr > -0.5)
    has_bullish_div = bool(_safe_get(last, "has_bullish_div", False))
    
    # --- ELITE SIGNALS: SNIPER & POCKET PIVOT (Phase 13) ---
    is_sniper = False
    if has_bullish_div and (vol_spike_val >= 1.5) and (close_val > ema20_val) and (rsi_val > 45):
        is_sniper = True
        durumlar.append("🎯 SNIPER SETUP (Uyumsuzluk + Hacim Patlaması)")
        kalite += 25  # High-confidence alpha signal
        action = "🎯 KESKİN NİŞANCI (ALPHA AL)"
        decision = "HIGH CONVICTION"

    is_pocket_pivot = False
    if (close_val > prev_close) and (vol_spike_val >= 1.8) and (konsol >= 45) and (not is_pump_dump):
        is_pocket_pivot = True
        durumlar.append("💰 POCKET PIVOT (Kurumsal Sıkışma Kırılımı)")
        kalite += 15
        if action == "✅ ALIM İÇİN UYGUN": action = "💰 KURUMSAL GİRİŞ (PIVOT)"

    ut_plus_div = False
    if is_ut_strong and has_bullish_div:
        durumlar.append("🚀 ULTIMATE REVERSAL (UT BOT + UYUMSUZLUK)")
        kalite += 15 # Double confirmation bonus
        ut_plus_div = True
    elif is_ut_strong:
        durumlar.append("🤖 GÜÇLÜ UT BOT AL")
        kalite += 5
    elif has_bullish_div:
        durumlar.append("🐂 POZİTİF UYUMSUZLUK (GÜÇLÜ BOĞA)")
        dip += 15
        kalite += 5
    
    # AI Puanı Al
    ai_prob_raw = float(_safe_get(last, "ai_prob", 55.0))
    
    # --- Deneyim Bankası Filtresi (Experience Proxy - Phase 12) ---
    # Modelin 'features' listesini bul (genelde indicators'da tanımlı olanlar)
    feature_list = [
        "rsi", "macd_hist", "adx", "atr_pct", "bb_width", "roc20", 
        "ema20_slope", "vol_spike", "feat_rsi_mom", "feat_vol_atr"
    ]
    # Sadece mevcut olanları filtrele
    valid_features = [f for f in feature_list if f in last.index]
    
    past_success = query_experience_memory(last, valid_features)
    memory_bonus = (past_success - 0.5) * 20 # -10 ile +10 arası puan
    
    # Kalite puanını hafıza tecrübesiyle güncelle
    kalite = clamp(kalite + memory_bonus)
    
    # --- AKILLI SERMAYE POLİTİKASI — Kelly Criterion ---
    policy     = TradingPolicyOptimizer()
    pos_result = policy.calculate_position_size(
        ai_confidence   = ai_prob_raw / 100.0,
        atr_pct         = atr_pct_val,
        current_drawdown = 0.0,
    )
    pos_label  = pos_result.get("label", f"{pos_result.get('size', 0.0):.2f}x")

    # ================================================================
    # 6 YENİ AI MODÜLÜ — Her biri bağımsız ve hata-toleranslı
    # ================================================================

    # 1. DUYGU ANALİZİ (KAP + Haber Tansiyonu)
    sentiment_data = {"composite": 0.0, "kap_score": 0.0, "news_volume": 0}
    if _SENTIMENT_OK:
        try:
            symbol_name = str(_safe_get(last, "symbol", ""))
            if symbol_name:
                s = get_full_sentiment(symbol_name)
                sentiment_data = s
                sent_bonus = s["composite"] * 8      # Max ±8 puan
                kalite = clamp(kalite + sent_bonus)
                if s["composite"] > 0.3:
                    durumlar.append(f"📰 POZİTİF KAP/HABER (+{s['news_volume']} başlık)")
                elif s["composite"] < -0.3:
                    durumlar.append(f"📰 NEGATİF KAP/HABER ({s['news_volume']} başlık)")
        except Exception:
            pass

    # 2. KORELASYON / ÖNCÜ SİNYAL (Lokomotif Hisseler)
    leading_signal = 0.0
    if _CORR_OK:
        try:
            from constants import DEFAULT_BIST_30
            dom  = [d["symbol"] for d in get_dominant_stocks(DEFAULT_BIST_30, top_n=5)]
            sym  = str(_safe_get(last, "symbol", ""))
            if sym and dom:
                leading_signal = get_leading_signal(sym, dom)
                lead_bonus     = leading_signal * 6   # Max ±6 puan
                kalite = clamp(kalite + lead_bonus)
                if leading_signal > 0.3:
                    durumlar.append(f"🕸️ ÖNCÜ HİSSELER POZİTİF (Lead={leading_signal:+.2f})")
                elif leading_signal < -0.3:
                    durumlar.append(f"🕸️ ÖNCÜ HİSSELER NEGATİF (Lead={leading_signal:+.2f})")
        except Exception:
            pass

    # 3. EMİR AKIŞI & MİKROYAPI (Smart Money + Hacim Anomalisi)
    order_flow_data = {"composite": 0.0, "volume_sig": "NORMAL", "liquidity": "ORTA"}
    if _ORDER_FLOW_OK:
        try:
            # Mevcut df yoksa last'tan proxy oluştur — scoring ham df almıyor
            # Bilgiler last series içinden çekiliyor
            of_vol_z  = float(_safe_get(last, "vol_spike", 0.0)) / 3.0   # Normalize
            of_smart  = float(_safe_get(last, "Smart Money Skor", 0.0)) / 100.0 - 0.5
            of_comp   = (of_vol_z + of_smart) / 2.0
            of_comp   = max(-1.0, min(1.0, of_comp))
            order_flow_data["composite"] = round(of_comp, 3)
            of_bonus  = of_comp * 5
            kalite = clamp(kalite + of_bonus)
            if of_comp > 0.4:
                durumlar.append(f"📊 SMART MONEY GİRİŞİ (MF={of_comp:+.2f})")
            elif of_comp < -0.4:
                durumlar.append(f"📊 SMART MONEY ÇIKIŞI (MF={of_comp:+.2f})")
        except Exception:
            pass

    # 4. ÇOKLU ZAMAN DİLİMİ ONAYI (1H+4H+1D)
    mtf_adv_data = {"confirmed": False, "direction": "KARIŞIK", "confidence_add": 0.0}
    if _MTF_ADV_OK:
        try:
            sym  = str(_safe_get(last, "symbol", ""))
            exch = "BIST" if market == "BIST" else ("BINANCE" if market == "CRYPTO" else "NASDAQ")
            if sym:
                mtf_adv_data = get_multi_timeframe_confirmation(sym, exch)
                kalite = clamp(kalite + mtf_adv_data["confidence_add"])
                if mtf_adv_data["confirmed"]:
                    if mtf_adv_data["direction"] == "YUKARI":
                        durumlar.append(f"🌀 MTF ONAYI: 3 TF YUKARI ✅")
                    elif mtf_adv_data["direction"] == "ASAGI":
                        durumlar.append(f"🌀 MTF ONAYI: 3 TF AŞAĞI ⚠️")
                else:
                    durumlar.append("🌀 MTF: Karışık (Bir TF Uyumsuz)")
        except Exception:
            pass

    # 5. RL POLİTİKA KARARI (Q-Learning Ajanı)
    rl_action_data = {"action": "AL", "pos_size": 0.0, "q_vals": []}
    if _RL_OK:
        try:
            agent    = get_rl_agent()
            regime   = "bull" if kalite > 60 else ("bear" if kalite < 35 else "sideways")
            rl_dec   = agent.choose_action(
                regime       = regime,
                rsi          = float(_safe_get(last, "rsi", 50)),
                trend_score  = leading_signal,
                ai_conf      = ai_prob_raw / 100.0,
                greedy       = True,
            )
            rl_action_data = rl_dec
            # RL'nin açıkça "İŞLEM_YOK" demesi sinyali zayıflatır
            if rl_dec["action"] == "İŞLEM_YOK" and signal == "AL":
                kalite = clamp(kalite - 12)
                durumlar.append("🧬 RL AJAN: İşlem Önermiyor")
            elif rl_dec["action"] in ("AL", "KÜÇÜK_AL") and signal == "AL":
                durumlar.append(f"🧬 RL AJAN: {rl_dec['action']} Onayı")
        except Exception:
            pass

    # ================================================================
    # SON KARAR GÜNCELLEMESI (kalite yeniden değerlendirildi)
    # ================================================================

    # 6. FİZİK MOTORU (Kalman + Fourier + Elastisite + Momentum)
    physics_data = {"physics_score": 0.0, "noise_level": "ORTA", "tags": []}
    if _PHYSICS_OK:
        try:
            # Ham OHLCV verisine ihtiyac var: last series'ten rekonstükte et
            # (Tarama sırasında tam df yoksa proxy kullan)
            physics_proxy_close = float(_safe_get(last, "close", 0))
            if physics_proxy_close > 0:
                engine = get_physics_engine()
                # Sadece Close verisiyle çalışabilen metrikleri hesapla
                # (Gerçek df için data_fetcher entegrasyonu yapılabilir)
                # Burada features JSON içinde fizik özellikleri varsa kullan
                px_noise = features.get("kalman_noise_ratio", 0.3) if 'features' in dir() else 0.3
                px_z     = float(_safe_get(last, "elastic_z_distance", 0.0))
                px_accel = float(_safe_get(last, "momentum_acceleration", 0.0))

                # Proxy skor hesapla
                px_score = 0.0
                px_tags  = []
                if px_z > 2.5:
                    px_score -= 8.0
                    px_tags.append(f"⚠️ ELAStİSİTE: Aşırı Uzak (Z={px_z:.1f})")
                elif px_z < -2.0:
                    px_score += 6.0
                    px_tags.append(f"🟢 ELAStİSİTE: Güvenli Dip Zön (Z={px_z:.1f})")
                if px_accel > 0.3:
                    px_score += 4.0
                    px_tags.append("⚡ MOMENTUM İVELENMEDE")
                elif px_accel < -0.3:
                    px_score -= 4.0
                    px_tags.append("📉 MOMENTUM YAVAlŞIYOR")

                physics_data = {
                    "physics_score": round(px_score, 2),
                    "noise_level":   "YUKARI" if px_noise < 0.2 else ("YUKSEK" if px_noise > 0.45 else "ORTA"),
                    "tags":          px_tags,
                }
                kalite = clamp(kalite + px_score)
                durumlar.extend(px_tags)
        except Exception:
            pass
    # 7. ANOMALİ DEDEKTÖRü (Autoencoder — Tahtacı/Balina Koruması)
    anomaly_data   = {"is_anomaly": False, "severity": "NORMAL", "anomaly_norm_score": 0.0}
    anomaly_blocked = False
    if _ANOMALY_OK:
        try:
            detector = get_anomaly_detector()
            if detector.model is not None:  # Model eğitilmişse kullan
                safe, reason = detector.is_safe_to_trade(last)
                anom_det     = detector.detect(last)
                anomaly_data = anom_det
                if not safe:
                    anomaly_blocked = True
                    # Manipülatif hisse — AL sinyalini blokla
                    if signal == "AL":
                        signal   = "BEKLE"
                        decision = "WATCHLIST"
                        kalite   = clamp(kalite - 25)
                    durumlar.append(f"🚨 ANOMALİ ENGELİ: {anom_det['severity']} (Skor={anom_det['anomaly_norm_score']:.0f})")
                elif anom_det["anomaly_norm_score"] > 60:
                    durumlar.append(f"⚠️ Şüpheli Hacim-Fiyat Davranışı (Skor={anom_det['anomaly_norm_score']:.0f})")
        except Exception:
            pass

    # 8. BAYESIAN BELİRSİZLİK ÖLÇÜMÜ (MC Dropout + Dinamik Kelly)
    bayesian_data = {
        "bayesian_prob": ai_prob_raw / 100.0, "uncertainty": 0.3,
        "kelly_pct": pos_result.get("size_pct", 0.0),
        "kelly_label": pos_label, "signal_grade": "B", "kelly_reduction": 0.0
    }
    if _BAYESIAN_OK and not anomaly_blocked:
        try:
            validator    = get_bayesian_validator()
            feat_names   = ["rsi", "macd_hist", "adx", "atr_pct", "bb_width",
                            "roc20", "ema20_slope", "vol_spike"]
            bk           = pos_result.get("size", 0.05)
            regime_str   = "bull" if kalite > 60 else ("bear" if kalite < 35 else "sideways")
            bay_result   = validator.validate(last, feat_names, bk, regime_str)
            bayesian_data = bay_result

            # Bayesian kelly, standart kelly'yi override eder
            if bay_result["kelly_pct"] < pos_result.get("size_pct", 0):
                pos_label = bay_result["kelly_label"]

            # Güven durumu tags
            if bay_result["is_confident"] and bay_result["bayesian_prob"] > 0.65:
                durumlar.append(f"🧠 BAYESIAN: {bay_result['signal_grade']} — Yüksek Güven")
            elif bay_result["uncertainty"] > 0.45:
                durumlar.append(f"🧠 BAYESIAN: {bay_result['signal_grade']} — Belirsizlik Yüksek (%{bay_result['kelly_reduction']:.0f} Kelly Kesintisi)")
                kalite = clamp(kalite - 8)
        except Exception:
            pass

    # Son karar güncellemesi
    # Dinamik Tarama Politikası (AI tarafından optimize edilmiş)
    policy = get_scanner_policy()
    elite_t = policy.get("elite_threshold", 78)
    ready_t = policy.get("trade_ready_threshold", 35)

    kalite = clamp(kalite)
    if kalite >= elite_t and signal != "AÇIĞA SAT":
        decision, signal = "HIGH CONVICTION", "AL"
    elif kalite < ready_t and signal == "AL":
        decision, signal = "WATCHLIST", "BEKLE"

    return {
        "Vade": vade, "Kalite": round(kalite, 1), "Günlük %": f"%{round(daily_return, 2)}",
        "Pozisyon": pos_label,
        "Kelly %": pos_result.get("size_pct", 0.0),
        "KAP Skor": round(sentiment_data.get("composite", 0.0), 2),
        "Haber Tansiyonu": sentiment_data.get("news_volume", 0),
        "Lead Sinyal": round(leading_signal, 2),
        "Order Flow": round(order_flow_data.get("composite", 0.0), 2),
        "MTF Onay": mtf_adv_data.get("direction", "-"),
        "RL Aksiyon": rl_action_data.get("action", "-"),
        "Bayesian Prob": bayesian_data.get("bayesian_prob", 0.5),
        "Belirsizlik": bayesian_data.get("uncertainty", 0.3),
        "Sinyal Notu": bayesian_data.get("signal_grade", "-"),
        "Bayesian Kelly %": bayesian_data.get("kelly_pct", 0.0),
        "Anomali": anomaly_data.get("severity", "NORMAL"),
        "Anomali Skor": anomaly_data.get("anomaly_norm_score", 0.0),
        "Skor": round(general, 1), "Smart Money Skor": round(smart_money, 1),
        "Fizik Skor": physics_data.get("physics_score", 0.0),
        "Gürültü": physics_data.get("noise_level", "ORTA"),
        "Trend Skor": round(trend, 1), "Dip Skor": round(dip, 1), "Breakout Skor": round(breakout, 1),
        "Momentum Skor": round(momentum, 1), "Konsol Skor": round(konsol, 1),
        "Dusus Riski": round(risk, 1), "Guven": round(confidence, 1),
        "Decision": decision, "Sinyal": signal, "Aksiyon": action,
        "Fiyat": close_val, "Stop Loss": round(stop, 4), "Hedef 1": round(tp1, 4), "Hedef 2": round(tp2, 4), "Hedef 3": round(tp3, 4),
        "R/R": round(rr, 2), "Likidite": "✅ UYGUN" if is_liquid else "🚫 SIĞ",
        "Özel Durum": " | ".join(durumlar) if durumlar else "-",
        "Para Akışı (MFI)": round(mfi_val, 1),
        "OBV Durumu": "📈 Artıyor" if _safe_get(last, "obv", 0) > _safe_get(prev, "obv", 0) else "📉 Azalıyor",
        "Konsol Durumu": konsol_tag,
        "Weinstein": w_stage_tag,
        "Trend Sablonu": "✅ GÜÇLÜ (MINERVINI)" if is_minervini else "-",
        "UT_Bot_Al": is_ut_strong,
        "UT_Plus_Div": ut_plus_div,
        "Takas Puani": takas_scr,
        "Takas Karari": takas_karar,
        "Takas Detayları": " | ".join(takas_detay) if takas_detay else "-",
        "Vade": vade,
        "Kalite": round(kalite, 1),
        "Hacim Spike": round(vol_spike_val, 2),
        "Bollinger Genisligi": round(float(_safe_get(last, "bb_width", 0.0)), 4),
        "Daralma (Squeeze)": "🗜 İzlenir" if bb_squeeze else "-",
        "Elite Skor": 0  # run_scan'de temel analiz ile güncellenir
    }

def score_weinstein(last: pd.Series, conf_last: pd.Series) -> Tuple[float, str, str]:
    """Stan Weinstein Stage Analysis (Aşama Analizi) Skorlaması.
    Haftalık veri (conf_last) üzerinden çalışır.
    """
    weinstein_score = 0.0
    stage_msg = ""
    
    # Haftalık veri üzerinden Weinstein göstergeleri
    w_close = float(_safe_get(conf_last, "close", 0.0))
    w_sma30 = float(_safe_get(conf_last, "sma30_w", 0.0))
    w_slope = float(_safe_get(conf_last, "sma30_w_slope", 0.0))
    w_volume = float(_safe_get(conf_last, "volume", 0.0))
    w_vol_ma4 = float(_safe_get(conf_last, "vol_ma4_w", 0.0))
    w_stage = int(_safe_get(conf_last, "weinstein_stage", 0))
    
    # Buy Signal Criteria (Transition to Stage 2)
    # - Price > 30-Week SMA
    # - Slope > 0 (turning up)
    # - Volume > 2x average (breakout confirmation)
    is_stage2_entry = (w_close > w_sma30) and (w_slope > 0) and (w_volume > w_vol_ma4 * 2.0)
    
    if is_stage2_entry:
        weinstein_score += 40
        stage_msg = "🚀 WEINSTEIN AŞAMA 2 (GÜÇLÜ BOĞA)"
    elif w_stage == 2:
        weinstein_score += 20
        stage_msg = "📈 WEINSTEIN AŞAMA 2 (TREND)"
    elif w_stage == 4:
        weinstein_score -= 40
        stage_msg = "📉 WEINSTEIN AŞAMA 4 (MELTDOWN)"
    elif w_stage == 3:
        weinstein_score -= 15
        stage_msg = "⚠️ WEINSTEIN AŞAMA 3 (DAĞITIM)"
    elif w_stage == 1:
        weinstein_score += 5
        stage_msg = "📐 WEINSTEIN AŞAMA 1 (TABAN YAPMA)"

    return weinstein_score, stage_msg, f"Aşama {w_stage}"
