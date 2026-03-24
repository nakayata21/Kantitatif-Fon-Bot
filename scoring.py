
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
        "piotroski_score": f_score
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

    dip = 0.0
    dip += 25 if is_rsi_oversold else 0
    dip += 15 if is_rsi_rising else 0
    dip += 20 if macd_cross_up else 0
    dip += 15 if _safe_get(last, "pos_div", False) else 0
    dip += 15 if is_price_above_ma20 else 0
    dip += 25 if is_near_bottom else 0
    dip += 5 if is_volume_up else 0
    if bb_pct > 0.85: dip -= 40 # Aşırı ısınmışsa dip puanı kır
    
    dip_signals = []
    if is_rsi_oversold: dip_signals.append("✓ RSI Aşırı Satım")
    if is_rsi_rising: dip_signals.append("✓ RSI Dönüşü")
    if macd_cross_up: dip_signals.append("✓ MACD Kesti")
    if is_price_above_ma20: dip_signals.append("✓ MA20 Kırıldı")
    if is_near_bottom: dip_signals.append("✓ Destek Bölgesi")
    if is_volume_up: dip_signals.append("✓ Alıcı Girişi")
    dip_signal_str = " | ".join(dip_signals) if dip_signals else "-"
    is_solid_bottom = dip >= 45

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

    # 9. STAN WEINSTEIN STAGE ANALYSIS
    w_score, w_msg, w_stage_tag = score_weinstein(last, conf_last)

    # VADE VE AĞIRLIKLANDIRMA (Weinstein eklendi)
    is_long_vade = bool(sma200_val > 0 and close_val > sma200_val * 1.02)
    is_mid_vade = bool(sma50_val > 0 and close_val > sma50_val * 1.01)
    
    if is_long_vade:
        vade = "Uzun"
        # Weinstein uzun vadide %25 etkili olsun
        w_trend, w_dip, w_breakout, w_momentum, w_sm, w_wein = 0.30, 0.05, 0.20, 0.10, 0.10, 0.25
    elif is_mid_vade:
        vade = "Orta"
        w_trend, w_dip, w_breakout, w_momentum, w_sm, w_wein = 0.20, 0.15, 0.20, 0.10, 0.15, 0.20
    else:
        vade = "Kısa"
        if adx_val >= 25: # Trend marketi
            w_trend, w_dip, w_breakout, w_momentum, w_sm, w_wein = 0.15, 0.05, 0.15, 0.30, 0.20, 0.15
        else: # Yatay market
            w_trend, w_dip, w_breakout, w_momentum, w_sm, w_wein = 0.05, 0.35, 0.10, 0.20, 0.20, 0.10

    general = clamp(
        (trend * w_trend) + (dip * w_dip) + (breakout * w_breakout) + 
        (momentum * w_momentum) + (smart_money * w_sm) + (w_score * w_wein)
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
        if breakout_up: action = "📈 DİRENÇ KIRILDI"
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
    if is_solid_bottom: durumlar.append("🚨 DİPTEN DÖNÜYOR")
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
    
    return {
        "Vade": vade, "Kalite": round(kalite,1), "Günlük %": f"%{round(daily_return,2)}",
        "Skor": round(general,1), "Smart Money Skor": round(smart_money,1),
        "Trend Skor": round(trend,1), "Dip Skor": round(dip,1), "Breakout Skor": round(breakout,1),
        "Momentum Skor": round(momentum,1), "Konsol Skor": round(konsol,1),
        "Dusus Riski": round(risk,1), "Guven": round(confidence,1),
        "Decision": decision, "Sinyal": signal, "Aksiyon": action,
        "Fiyat": close_val, "Stop Loss": round(stop,4), "Hedef 1": round(tp1,4), "Hedef 2": round(tp2,4), "Hedef 3": round(tp3,4),
        "R/R": round(rr,2), "Likidite": "✅ UYGUN" if is_liquid else "🚫 SIĞ",
        "Özel Durum": " | ".join(durumlar) if durumlar else "-",
        "Para Akışı (MFI)": round(mfi_val, 1),
        "OBV Durumu": "📈 Artıyor" if _safe_get(last, "obv", 0) > _safe_get(prev, "obv", 0) else "📉 Azalıyor",
        "Konsol Durumu": konsol_tag,
        "Weinstein": w_stage_tag,
        "Trend Sablonu": "✅ GÜÇLÜ (MINERVINI)" if is_minervini else "-",
        "UT_Bot_Al": is_ut_strong,
        "UT_Plus_Div": ut_plus_div
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
