
import pandas as pd
from typing import Dict, Tuple
from utils import clamp, _safe_get

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
    
    fund_score = float(fundamental.get("fundamental_score", 0))
    fund_grade = fundamental.get("fundamental_grade", "-")
    pe = fundamental.get("pe_ratio")
    roe = fundamental.get("roe")
    roa = fundamental.get("roa")
    de = fundamental.get("debt_to_equity")
    rg = fundamental.get("revenue_growth")
    eg = fundamental.get("earnings_growth")
    
    tech_component = (
        (tech_kalite * 0.25) +
        (tech_momentum * 0.08) +
        (tech_breakout * 0.07) +
        (tech_smart_money * 0.05) +
        (tech_guven * 0.05)
    )
    
    if tech_risk > 60:
        tech_component *= 0.6
    elif tech_risk > 45:
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
    }

def score_symbol(last: pd.Series, prev: pd.Series, conf_last: pd.Series, market: str = "NASDAQ", index_healthy: bool = True) -> Dict[str, object]:
    mtf_ok    = bool(_safe_get(conf_last, "ema20", 0) > _safe_get(conf_last, "ema50", 0) and _safe_get(conf_last, "macd_hist", 0) > 0)
    regime_ok = bool((_safe_get(last, "adx", 0) >= 18) and (1.0 <= _safe_get(last, "atr_pct", 0) <= 9.0))

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
    daily_return = ((close_val - prev_close) / prev_close) * 100 if prev_close > 0 else 0.0

    macd_cross_up  = (macd_curr > 0) and (macd_prev <= 0)
    bb_lower_cross = (close_val > bb_lower_curr) and (prev_close <= bb_lower_prev)
    is_pump_dump = (rsi_val > 68) and (daily_return > 2.5) and (vol_spike_val < 1.0)
    
    min_liquidity = 50_000_000 if market == "BIST" else 5_000_000
    is_liquid = avg_turnover >= min_liquidity

    trend = 0.0
    trend += 20 if ema20_val > sma50_val else 0
    trend += 10 if close_val > sma20_val else 0
    trend += 8  if macd_curr > 0 else 0
    trend += 8  if mtf_ok else 0
    trend += 6  if ema20_slope > 0.5 else 0
    trend += 15 if (sma200_val > 0 and close_val > sma200_val) else 0
    trend += 10 if (sma50_val > 0 and sma200_val > 0 and sma50_val > sma200_val) else 0
    trend += 10 if (sma50_val > 0 and close_val > sma50_val) else 0

    support_120_val = float(_safe_get(last, "support_120", 0.0))
    ema20_prev = float(_safe_get(prev, "ema20", 0.0))
    is_rsi_oversold = rsi_val <= 30
    is_rsi_rising = (rsi_val > prev_rsi) and (rsi_val < 50)
    is_price_above_ma20 = (close_val > ema20_val) and (prev_close <= ema20_prev)
    is_near_bottom = (support_120_val > 0) and (((close_val - support_120_val) / support_120_val) * 100 <= 6.0)
    is_volume_up = (vol_spike_val >= 1.5)

    dip = 0.0
    dip += 20 if is_rsi_oversold else 0
    dip += 15 if is_rsi_rising else 0
    dip += 15 if macd_cross_up else 0
    dip += 10 if _safe_get(last, "pos_div", False) else 0
    dip += 15 if is_price_above_ma20 else 0
    dip += 20 if is_near_bottom else 0
    dip += 5 if is_volume_up else 0
    if bb_pct > 0.8:
        dip -= 30
    
    dip_signals = []
    if is_rsi_oversold: dip_signals.append("✓ RSI < 30")
    if is_rsi_rising: dip_signals.append("✓ RSI Yükseliyor")
    if macd_cross_up: dip_signals.append("✓ MACD Kesti")
    if is_price_above_ma20: dip_signals.append("✓ MA20 Kırıldı")
    if is_near_bottom: dip_signals.append("✓ Son Dönem Dibi")
    if is_volume_up: dip_signals.append("✓ Hacim Patladı")
    dip_signal_str = " | ".join(dip_signals) if dip_signals else "-"
    is_solid_bottom = dip >= 40

    breakout_up = bool(_safe_get(last, "breakout_up", False))
    breakout = 0.0
    breakout += 18 if breakout_up else 0
    breakout += 15 if (breakout_up and bb_width_val < 8.0) else 0
    breakout += 12 if b52w else 0
    breakout += 15 if breakout_60 else 0
    breakout += 12 if gap_pct_val > 2.0 else 0 
    breakout +=  8 if mtf_ok else 0

    momentum = 0.0
    momentum += 15 if macd_cross_up else 0
    momentum += 10 if _safe_get(last, "obv", 0) > _safe_get(prev, "obv", 0) else 0
    momentum += 16 if (macd_curr > 0 and macd_curr > macd_prev) else 0
    momentum += 10 if (50 <= rsi_val <= 70) else 0
    momentum +=  8 if mtf_ok else 0
    momentum +=  8 if roc20 > 3.0 else 0

    trend    = clamp(trend)
    dip      = clamp(dip)
    breakout = clamp(breakout)
    momentum = clamp(momentum)

    smart_money = 0.0
    smart_money += 20 if inst_bar else 0
    smart_money += 20 if ut_buy else 0
    smart_money += 15 if (vol_spike_val >= 2.0) else 0
    smart_money += 10 if (vol_spike_val >= 1.5) else 0
    smart_money += 10 if _safe_get(last, "higher_lows_5", False) else 0
    smart_money += 10 if adx_val >= 20 else 0
    smart_money = clamp(smart_money)

    market_regime = "TREND" if adx_val >= 20 else "CHOP"
    if market_regime == "TREND":
        w_trend, w_dip, w_breakout, w_momentum, w_sm = 0.15, 0.05, 0.30, 0.30, 0.20
    else: 
        w_trend, w_dip, w_breakout, w_momentum, w_sm = 0.10, 0.35, 0.15, 0.20, 0.20

    general  = clamp((trend * w_trend) + (dip * w_dip) + (breakout * w_breakout) + (momentum * w_momentum) + (smart_money * w_sm))

    risk = 15.0
    risk += 30 if not regime_ok else 0
    risk += 50 if not index_healthy else 0
    risk += 25 if ema20_dist > 15.0 else 0    
    risk += 15 if ema20_dist > 8.0 else 0     
    risk += 20 if rsi_val > 70 else 0         
    risk += 30 if daily_return > 8.0 else 0   
    risk += 15 if daily_return > 6.0 and daily_return <= 8.0 else 0 
    risk += 35 if daily_return < -4.0 else 0  
    risk += 15 if daily_return < -2.5 and daily_return >= -4.0 else 0
    risk +=  8 if atr_pct_val > 7.0 else 0   
    risk +=  8 if adx_val < 15 else 0         
    risk += 15 if (sma200_val > 0 and close_val < sma200_val) else 0 
    risk += 35 if not is_liquid else 0
    risk += 40 if gap_pct_val > 2.0 and vol_spike_val < 1.0 else 0
    is_pd_aggressive = (rsi_val > 75) and (daily_return > 3.0) and (vol_spike_val < 1.2)
    risk += 60 if (is_pump_dump or is_pd_aggressive) else 0
    risk += 30 if _safe_get(last, "neg_div", False) else 0
    risk += 25 if (daily_return > 0 and vol_spike_val < 0.8) else 0 # Hacimsiz yükseliş (Distribution riski)
    risk += 10 if gap_pct_val < -2.0 else 0   
    risk = clamp(risk)

    confidence = clamp(
        20
        + (20 if mtf_ok else 0)
        + (18 if regime_ok else 0)
        + (15 if ema20_slope > 0 else 0)
    )

    ut_recent = ut_buy or bool(prev.get("ut_buy", False))
    ut_long   = (ut_pos == 1)

    if market == "NASDAQ":
        buy_general, buy_conf, buy_risk, buy_sm = 45, 55, 50, 10
    else:
        buy_general, buy_conf, buy_risk, buy_sm = 45, 50, 55, 5

    is_fresh_buy = ut_recent and general >= buy_general and risk <= buy_risk and index_healthy
    is_bottom_buy = is_solid_bottom and risk <= (buy_risk - 5) and index_healthy
    is_trend_buy = ut_long and general >= (buy_general + 5) and confidence >= buy_conf and smart_money >= buy_sm and risk <= buy_risk and index_healthy

    is_overextended_hard = (ema20_dist > 8.0) or (rsi_val > 75) or (roc20 > 18.0) # Sert koruma: Hızlı gitmişse peşinden koşma
    
    atr_val = float(_safe_get(last, "atr", 0.0))
    support_120_val = float(_safe_get(last, "support_120", 0.0))
    stop = max(0.0, close_val - (1.5 * atr_val))
    if is_solid_bottom and support_120_val > 0 and support_120_val < close_val:
        stop = min(stop, support_120_val * 0.98)
        
    risk_amount = close_val - stop
    tp1 = close_val + (1.5 * risk_amount) if risk_amount > 0 else 0.0
    tp2 = close_val + (2.5 * risk_amount) if risk_amount > 0 else 0.0
    tp3 = close_val + (4.0 * risk_amount) if risk_amount > 0 else 0.0
    target = tp3
    rr = (tp1 - close_val) / risk_amount if (risk_amount > 0 and tp1 > close_val) else 0.0
    
    is_rr_bad = rr < 1.2
    
    engine_type = "SAFE"
    if vol_spike_val >= 2.0 and float(_safe_get(last, "bb_width", 100)) < 15.0:
        engine_type = "OPPORTUNITY"

    kalite = general - (risk * 0.50) + (confidence * 0.25)
    
    if is_overextended_hard or not is_liquid or (is_rr_bad and engine_type == "SAFE"):
        decision = "NO TRADE"
        signal, action = "SAT", "NO TRADE (Risk Filtresi)"
    elif kalite >= 80 and is_rr_bad == False:
        decision = "HIGH CONVICTION"
        signal = "AL"
        if is_bottom_buy: action = "🚀 Dip Reversal (Trend Devamı)"
        elif is_trend_buy: action = "📈 Trend Continuation"
        else: action = "🔥 Momentum Ignition"
    elif kalite >= 60:
        decision = "TRADE READY"
        signal = "AL"
        if engine_type == "OPPORTUNITY": action = "⚡ Squeeze Breakout (Agresif)"
        elif is_bottom_buy: action = "📉 Dip Fırsatı"
        else: action = "🔥 Potansiyel Setup"
    elif kalite >= 45:
        decision = "WATCHLIST"
        signal = "BEKLE"
        action = "Hacim ve Kırılım Bekleniyor"
    else:
        decision = "NO TRADE"
        signal, action = "SAT", "Kriterleri Karşılamadı"
        
    sma200_dist = ((close_val - sma200_val) / sma200_val) * 100 if sma200_val > 0 else 0.0
    overextend_penalty = 1.0
    overextend_reasons = []
    
    if ema20_dist > 8.0:
        overextend_penalty *= 0.30
        overextend_reasons.append("⚠️ EMA20'den %8+ Kopuk (Geç Kalınmış)")
    elif ema20_dist > 5.0:
        overextend_penalty *= 0.60
        overextend_reasons.append("⚠️ EMA20'den %5+ Uzaklaştı")
    
    if rsi_val >= 75:
        overextend_penalty *= 0.30
        overextend_reasons.append("🔴 RSI 75+ (Riskli Bölge)")
    elif rsi_val >= 68:
        overextend_penalty *= 0.60
        overextend_reasons.append("🟡 RSI 68+ (Isınmış)")
    
    if sma200_dist > 50.0:
        overextend_penalty *= 0.50
        overextend_reasons.append("🎈 SMA200'den %50+ (Balon Riski)")
    elif sma200_dist > 30.0:
        overextend_penalty *= 0.75
        overextend_reasons.append("⚠️ SMA200'den %30+ Uzak")
    
    if roc20 > 18.0:
        overextend_penalty *= 0.30
        overextend_reasons.append("🚀 20 Günde %18+ Yükselmiş (Fırsat Kaçmış)")
    elif roc20 > 10.0:
        overextend_penalty *= 0.60
        overextend_reasons.append("📈 20 Günde %10+ Yükselmiş")
    
    is_overextended = overextend_penalty < 0.95
    kalite *= overextend_penalty
    
    # "Sıfır Noktası" (Henüz patlamamış olanları) Liste başına itme algoritması
    if (signal == "AL") and (roc20 <= 5.0) and (konsol >= 40 or is_solid_bottom):
        kalite += 30  # Telegramda en üste çıksın diye büyük bonus
    elif (signal == "AL") and (roc20 <= 8.0):
        kalite += 15

    kalite = clamp(kalite)

    range_pct_20  = float(_safe_get(last, "range_pct_20",  15.0))
    lr_slope      = float(_safe_get(last, "lr_slope_20",    0.0))
    vol_ratio_520 = float(_safe_get(last, "vol_ratio_5_20", 1.0))
    ud_vol_ratio  = float(_safe_get(last, "ud_vol_ratio",   1.0))
    pos_in_range  = float(_safe_get(last, "pos_in_20d_range", 0.5))
    close_vs_ema  = close_val > ema20_val
    bb_squeeze    = bool(_safe_get(last, "bb_squeeze", False))

    konsol = 0.0
    konsol_signals = []
    if range_pct_20 < 12:
        konsol += 20
        konsol_signals.append("✓ Çok Dar Aralık")
    elif range_pct_20 < 18:
        konsol += 12
        konsol_signals.append("✓ Dar Aralık")
    elif range_pct_20 < 25:
        konsol += 5

    if abs(lr_slope) < 0.8:
        konsol += 15
        konsol_signals.append("✓ Yatay Sürünme")
    elif abs(lr_slope) < 1.5:
        konsol += 8
        konsol_signals.append("✓ Hafif Eğim")
    elif abs(lr_slope) < 2.5:
        konsol += 3

    if bb_squeeze:
        konsol += 20
        konsol_signals.append("✓ Bollinger Sıkışması")
    if adx_val < 20:
        konsol += 15
        konsol_signals.append("✓ Trendsiz (ADX<20)")
    elif adx_val < 25:
        konsol += 8
        konsol_signals.append("✓ Zayıf Trend")

    if atr_pct_val < 3:
        konsol += 12
        konsol_signals.append("✓ Çok Düşük Vol.")
    elif atr_pct_val < 5:
        konsol += 7
        konsol_signals.append("✓ Düşük Vol.")

    if vol_ratio_520 < 0.7:
        konsol += 10
        konsol_signals.append("✓ Hacim Kurudu")
    elif vol_ratio_520 < 0.9:
        konsol += 5
        konsol_signals.append("✓ Hacim Azaldı")

    if pos_in_range > 0.65:
        konsol += 8
        konsol_signals.append("✓ Range Üstü")
    elif pos_in_range > 0.45:
        konsol += 4
    if close_vs_ema:
        konsol += 5
        konsol_signals.append("✓ EMA20 Üstü")
    if ud_vol_ratio > 1.3:
        konsol += 8
        konsol_signals.append("✓ Alıcı Baskın")
    elif ud_vol_ratio > 1.1:
        konsol += 4

    if is_pump_dump: konsol -= 20
    if not is_liquid: konsol -= 15
    if atr_pct_val > 7: konsol -= 10
    if adx_val > 30: konsol -= 15
    if vol_ratio_520 > 2.0: konsol -= 10

    konsol = clamp(konsol)
    konsol_signal_str = " | ".join(konsol_signals) if konsol_signals else "-"
    if konsol >= 60: konsol_tag = "🔵 Güçlü Birikim"
    elif konsol >= 40: konsol_tag = "🟡 Sıkışma"
    elif konsol >= 20: konsol_tag = "⚪ Zayıf"
    else: konsol_tag = "-"

    durumlar = []
    if is_solid_bottom: durumlar.append("🚨 DİPTEN DÖNÜŞ (40+PUAN)")
    if is_overextended: durumlar.extend(overextend_reasons)
    ozel_durum_str = " | ".join(durumlar) if durumlar else "-"

    return {
        "Kalite":        round(kalite, 1),
        "Günlük %":      f"%{round(daily_return, 2)}",
        "Skor":          round(general, 1),
        "Smart Money Skor": round(smart_money, 1),
        "Kurumsal Giriş": "🟢 Güçlü" if smart_money >= 70 else ("🟡 İzlenir" if smart_money >= 45 else "Zayıf"),
        "Trend Skor":    round(trend, 1),
        "Dip Skor":      round(dip, 1),
        "Breakout Skor": round(breakout, 1),
        "Momentum Skor": round(momentum, 1),
        "Konsol Skor":   round(konsol, 1),
        "Konsol Durumu": konsol_tag,
        "Konsol Sinyal": konsol_signal_str,
        "Dusus Riski":   round(risk, 1),
        "Guven":         round(confidence, 1),
        "Decision":      decision,
        "Engine":        engine_type,
        "Sinyal":        signal,
        "Aksiyon":       action,
        "Fiyat":         close_val,
        "Stop Loss":     round(stop, 4),
        "Hedef 1":       round(tp1, 4),
        "Hedef 2":       round(tp2, 4),
        "Hedef 3":       round(tp3, 4),
        "Hedef 1 %":     round(((tp1 - close_val) / close_val) * 100, 1) if tp1 > close_val else 0,
        "Hedef 2 %":     round(((tp2 - close_val) / close_val) * 100, 1) if tp2 > close_val else 0,
        "Hedef 3 %":     round(((tp3 - close_val) / close_val) * 100, 1) if tp3 > close_val else 0,
        "Stop %":        round(((close_val - stop) / close_val) * 100, 1) if stop < close_val else 0,
        "R/R":           round(rr, 2),
        "Likidite":      "✅ Uygun" if is_liquid else "🚫 Çok Sığ",
        "UT Bot":        "🟢 YESİL" if ut_pos == 1 else "🔴 KIRMIZI",
        "MACD Durumu":   "🔥 Taze Kesti" if macd_cross_up else "-",
        "Bollinger":     "🟢 Dipten Zıpladı" if bb_lower_cross else "-",
        "Kurumsal SMA200": "Üstünde" if (sma200_val > 0 and close_val > sma200_val) else ("Altında" if sma200_val > 0 else "N/A"),
        "Gap":           f"%{round(gap_pct_val, 2)}",
        "Teyit":         "Evet" if mtf_ok else "Hayir",
        "Özel Durum":    ozel_durum_str,
        "Dip Sinyalleri": dip_signal_str,
        "BB %":          round(bb_pct * 100, 1),
        "Para Akışı (MFI)": round(float(_safe_get(last, "mfi", 50.0)), 1),
        "OBV Durumu":     "📈 Artıyor" if _safe_get(last, "obv", 0) > _safe_get(prev, "obv", 0) else "📉 Azalıyor",
    }
