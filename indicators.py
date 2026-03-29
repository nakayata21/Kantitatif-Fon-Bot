
import math
import numpy as np
import pandas as pd
import numba as nb
from typing import Tuple, Optional
import ta

def normalize(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).lower() for c in out.columns]
    for c in ["open", "high", "low", "close"]:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    if "volume" not in out.columns:
        out["volume"] = 0
    out["volume"] = pd.to_numeric(out["volume"], errors="coerce").fillna(0)
    return out.dropna(subset=["open", "high", "low", "close"])

@nb.njit
def _ut_bot_numba(close_arr: np.ndarray, loss_arr: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    n = len(close_arr)
    out_stop = np.zeros(n)
    out_pos = np.zeros(n, dtype=nb.int64)
    buy = np.zeros(n, dtype=nb.boolean)
    sell = np.zeros(n, dtype=nb.boolean)
    
    out_stop[0] = close_arr[0]
    out_pos[0] = 0
    
    for i in range(1, n):
        src = close_arr[i]
        src_1 = close_arr[i-1]
        loss = loss_arr[i] if not np.isnan(loss_arr[i]) else 0.0
        prev_stop = out_stop[i-1]
        
        if src > prev_stop and src_1 > prev_stop:
            out_stop[i] = max(prev_stop, src - loss)
        elif src < prev_stop and src_1 < prev_stop:
            out_stop[i] = min(prev_stop, src + loss)
        elif src > prev_stop:
            out_stop[i] = src - loss
        else:
            out_stop[i] = src + loss
            
        prev_pos = out_pos[i-1]
        if src_1 < prev_stop and src > prev_stop:
            out_pos[i] = 1
        elif src_1 > prev_stop and src < prev_stop:
            out_pos[i] = -1
        else:
            out_pos[i] = prev_pos
            
        if src > out_stop[i] and src_1 <= prev_stop:
            buy[i] = True
        elif src < out_stop[i] and src_1 >= prev_stop:
            sell[i] = True
            
    return buy, sell, out_pos

def compute_ut_bot(close: pd.Series, high: pd.Series, low: pd.Series, a: float = 1.0, c: int = 10) -> Tuple[pd.Series, pd.Series, pd.Series]:
    xATR = ta.volatility.AverageTrueRange(high=high, low=low, close=close, window=c, fillna=True).average_true_range()
    nLoss = a * xATR
    close_arr = close.to_numpy()
    loss_arr = nLoss.to_numpy()
    buy, sell, out_pos = _ut_bot_numba(close_arr, loss_arr)
    return pd.Series(buy, index=close.index), pd.Series(sell, index=close.index), pd.Series(out_pos, index=close.index)

def add_indicators(df: pd.DataFrame, index_df: pd.DataFrame = None) -> pd.DataFrame:
    out = normalize(df)
    
    out["ema20"] = ta.trend.EMAIndicator(close=out["close"], window=20, fillna=True).ema_indicator()
    out["ema50"] = ta.trend.EMAIndicator(close=out["close"], window=50, fillna=True).ema_indicator()
    out["sma20"] = ta.trend.SMAIndicator(close=out["close"], window=20, fillna=True).sma_indicator()
    out["sma50"] = ta.trend.SMAIndicator(close=out["close"], window=50, fillna=True).sma_indicator()
    out["sma200"] = ta.trend.SMAIndicator(close=out["close"], window=200, fillna=True).sma_indicator()
    out["gap_pct"] = ((out["open"] - out["close"].shift(1)) / out["close"].shift(1).replace(0, math.nan)) * 100
    
    out["rsi"] = ta.momentum.RSIIndicator(close=out["close"], window=14, fillna=True).rsi()
    
    macd_obj = ta.trend.MACD(close=out["close"], window_slow=26, window_fast=12, window_sign=9, fillna=True)
    out["macd"] = macd_obj.macd()
    out["macd_sig"] = macd_obj.macd_signal()
    out["macd_hist"] = macd_obj.macd_diff()
    
    atr_obj = ta.volatility.AverageTrueRange(high=out["high"], low=out["low"], close=out["close"], window=14, fillna=True)
    out["atr"] = atr_obj.average_true_range()
    out["atr_pct"] = (out["atr"] / out["close"].replace(0, math.nan)) * 100
    
    adx_obj = ta.trend.ADXIndicator(high=out["high"], low=out["low"], close=out["close"], window=14, fillna=True)
    out["adx"] = adx_obj.adx()
    out["plus_di"] = adx_obj.adx_pos()
    out["minus_di"] = adx_obj.adx_neg()
    
    out["vol_ma20"] = ta.trend.SMAIndicator(close=out["volume"], window=20, fillna=True).sma_indicator()
    out["vol_spike"] = out["volume"] / out["vol_ma20"].replace(0, math.nan)
    out["support_120"] = out["low"].rolling(120).min()
    out["res_20"]  = out["high"].shift(1).rolling(20).max()
    out["res_60"]  = out["high"].shift(1).rolling(60).max()
    out["res_260"] = out["high"].shift(1).rolling(260).max()
    out["breakout_up"]  = out["close"] > out["res_20"]
    out["breakout_60"]  = out["close"] > out["res_60"]
    out["breakout_52w"] = out["close"] > out["res_260"]
    
    bb_std = out["close"].rolling(20).std()
    out["bb_lower"] = out["sma20"] - 2 * bb_std
    out["bb_upper"] = out["sma20"] + 2 * bb_std
    out["bb_width"] = ((out["bb_upper"] - out["bb_lower"]) / out["sma20"].replace(0, math.nan)) * 100
    out["bb_pct"] = (
        (out["close"] - out["bb_lower"]) /
        (out["bb_upper"] - out["bb_lower"]).replace(0, math.nan)
    ).clip(0, 1)
    
    out["bb_squeeze"] = out["bb_width"] < out["bb_width"].rolling(50).quantile(0.2)
    out["ema20_slope"] = out["ema20"].pct_change(5) * 100
    out["roc20"] = out["close"].pct_change(20) * 100

    out["obv"] = ta.volume.OnBalanceVolumeIndicator(close=out["close"], volume=out["volume"], fillna=True).on_balance_volume()
    out["mfi"] = ta.volume.MFIIndicator(high=out["high"], low=out["low"], close=out["close"], volume=out["volume"], window=14, fillna=True).money_flow_index()
    
    # Anchored VWAP (Son dibin oluştuğu bardan itibaren)
    typical_price = (out["high"] + out["low"] + out["close"]) / 3
    tp_vol = typical_price * out["volume"]
    # Rolling 50-bar VWAP (kurumsal maliyet eğrisi)
    out["vwap"] = tp_vol.rolling(50).sum() / out["volume"].rolling(50).sum().replace(0, math.nan)
    out["above_vwap"] = out["close"] > out["vwap"]

    out["close_vs_sma50"] = ((out["close"] - out["sma50"]) / out["sma50"].replace(0, math.nan)) * 100
    out["close_vs_sma200"] = ((out["close"] - out["sma200"]) / out["sma200"].replace(0, math.nan)) * 100
    out["range_pct"] = ((out["high"] - out["low"]) / out["close"].replace(0, math.nan)) * 100
    out["avg_turnover_20"] = out["vol_ma20"] * out["close"]

    roll_high_20 = out["high"].rolling(20).max()
    roll_low_20  = out["low"].rolling(20).min()
    out["range_pct_20"] = (roll_high_20 - roll_low_20) / roll_low_20.replace(0, math.nan) * 100

    out["pos_in_20d_range"] = (
        (out["close"] - roll_low_20) /
        (roll_high_20 - roll_low_20).replace(0, math.nan)
    ).clip(0, 1)

    out["vol_ratio_5_20"] = out["volume"].rolling(5).mean() / out["volume"].rolling(20).mean().replace(0, math.nan)

    def _lr_slope(series: pd.Series) -> float:
        if series.isna().any() or len(series) < 2:
            return 0.0
        x = np.arange(len(series), dtype=float)
        y = series.values.astype(float)
        if np.std(y) < 1e-10:
            return 0.0
        try:
            slope = np.polyfit(x, y, 1)[0]
            return float(slope / (np.mean(y) + 1e-10) * 100)
        except Exception:
            return 0.0

    out["lr_slope_20"] = out["close"].rolling(20).apply(_lr_slope, raw=False)

    up_closes   = (out["close"] >= out["open"]).astype(float)
    up_vol_ser  = out["volume"] * up_closes
    total_vol_10 = out["volume"].rolling(10).sum().replace(0, math.nan)
    up_vol_10    = up_vol_ser.rolling(10).sum()
    down_vol_10  = total_vol_10 - up_vol_10
    
    out["ud_vol_ratio"] = (up_vol_10 / down_vol_10.replace(0, math.nan)).clip(0, 5)

    out["higher_lows_5"] = (
        (out["low"] > out["low"].shift(1)) &
        (out["low"].shift(1) > out["low"].shift(2)) &
        (out["low"].shift(2) > out["low"].shift(3)) &
        (out["low"].shift(3) > out["low"].shift(4))
    )

    out["inst_bar"] = (
        (out["gap_pct"] > 1.5) &
        (out["vol_spike"] >= 1.8) &
        (out["close"] > out["open"]) &
        (out["close"] > out["res_20"])
    )

    out["ut_buy"], out["ut_sell"], out["ut_pos"] = compute_ut_bot(out["close"], out["high"], out["low"], a=1.0, c=10)

    # --- Mark Minervini Trend Template (Stage 2 Uptrend) ---
    # Zaman dilimine göre pencere boyutlarını ayarla
    is_weekly = len(out) < 250 # Haftalık veride genellikle 200 bar çekiyoruz
    
    m_sma150_win = 30 if is_weekly else 150
    m_high_win = 52 if is_weekly else 252
    m_rising_win = 4 if is_weekly else 20
    
    out["sma150"] = ta.trend.SMAIndicator(close=out["close"], window=m_sma150_win, fillna=True).sma_indicator()
    out["low_52w"] = out["low"].rolling(window=m_high_win, min_periods=min(10, m_high_win)).min()
    out["high_52w"] = out["high"].rolling(window=m_high_win, min_periods=min(10, m_high_win)).max()
    
    # 200 Günlük MA'nın yükseliyor olması (Haftalıkta SMA30 veya SMA50'ye bakılabilir ama şablon gereği sma200'e bakıyoruz)
    # Eğer haftalık veriysek sma200 muhtemelen NaN'dır, o yüzden sma200_rising'i güvenli hesapla
    if "sma200" in out.columns and not out["sma200"].isnull().all():
        out["sma200_rising"] = out["sma200"] > out["sma200"].shift(m_rising_win)
    else:
        out["sma200_rising"] = True # Veri yoksa kısıtlama yapma
    
    # Minervini 8-Step Verification
    m1 = (out["close"] > out["sma150"])
    if "sma200" in out.columns and not out["sma200"].isnull().all():
        m1 &= (out["close"] > out["sma200"])
        m2 = out["sma150"] > out["sma200"]
    else:
        m2 = True # sma200 yoksa bu kuralı atla
        
    m3 = out["sma200_rising"]
    m4 = (out["sma50"] > out["sma150"])
    if "sma200" in out.columns and not out["sma200"].isnull().all():
        m4 &= (out["sma50"] > out["sma200"])
        
    m5 = out["close"] > out["sma50"]
    m6 = out["close"] > (out["low_52w"] * 1.25) # %30 yerine %25 yaparak esnettik
    m7 = out["close"] > (out["high_52w"] * 0.70) # %25 yerine %30 esnekliği
    
    out["minervini_template"] = m1 & m2 & m3 & m4 & m5 & m6 & m7

    # --- Uzun Süreli Düşüş (Ayı Piyasası) ve Dönüş Analizi ---
    # 1. Uzun Süreli Düşüş Durumu
    out["sma200_slope"] = out["sma200"].pct_change(20) * 100
    out["in_bear_market"] = (out["close"] < out["sma200"]) & (out["sma200_slope"] < 0)
    
    # Kaç bardır SMA200 altında (Düşüşün süresi)
    bear_count = (out["close"] < out["sma200"]).astype(int)
    out["bars_below_sma200"] = bear_count.groupby((bear_count != bear_count.shift()).cumsum()).cumsum()
    
    # Zirveden düşüş oranı
    out["drop_from_52w_high"] = ((out["high_52w"] - out["close"]) / out["high_52w"]) * 100
    
    # 2. Tükenme (Capitulation) Belirtileri
    out["is_capitulation"] = (out["rsi"] < 32) & (out["vol_spike"] > 1.5) & (out["in_bear_market"])
    
    # 3. Dönüş (Reversal) Sinyalleri
    # SMA50 üzerine hacimli çıkış
    out["reversal_breakout"] = (out["close"] > out["sma50"]) & (out["close"].shift(1) <= out["sma50"].shift(1)) & (out["vol_spike"] > 1.2)
    
    # Pozitif Uyumsuzluk Kontrolü (Basit RSI HL Kontrolü)
    out["rsi_higher_low"] = (out["rsi"] > out["rsi"].shift(1)) & (out["low"] <= out["low"].shift(1)) & (out["rsi"] < 40)

    # 4. Uzun Süreli Düşüş Bitiş Skoru (0-100)
    rev_score = (
        (out["reversal_breakout"].astype(int) * 40) +
        ((out["close"] > out["ema20"]).astype(int) * 20) +
        (out["rsi_higher_low"].astype(int) * 20) +
        ((out["drop_from_52w_high"] > 30).astype(int) * 20)
    )
    out["reversal_potential"] = rev_score.clip(0, 100)

    # --- Stan Weinstein Stage Analysis (Haftalık Bazda Daha Doğru Çalışır) ---
    out["sma30_w"] = ta.trend.SMAIndicator(close=out["close"], window=30, fillna=True).sma_indicator()
    out["sma30_w_slope"] = out["sma30_w"].pct_change(5)
    out["vol_ma4_w"] = out["volume"].rolling(4).mean()
    
    # Weinstein Stage identification (Haftalık veri olduğu varsayımıyla)
    def identify_weinstein_stage(row):
        close = row["close"]
        sma30 = row["sma30_w"]
        slope = row["sma30_w_slope"]
        
        if close > sma30:
            if slope > 0:
                return 2  # Stage 2: Advancing (Trend)
            else:
                return 1  # Stage 1: Basing (Accumulation)
        else:
            if slope < 0:
                return 4  # Stage 4: Declining (Meltdown)
            else:
                return 3  # Stage 3: Topping (Distribution)
                
    out["weinstein_stage"] = out.apply(identify_weinstein_stage, axis=1)

    # --- Mansfield Relative Strength (RS) ---
    if index_df is not None and not index_df.empty:
        try:
            # Sadece ortak tarihleri alarak RS Hesapla
            common_idx = out.index.intersection(index_df.index)
            if len(common_idx) > 20:
                rs_ratio = out.loc[common_idx, "close"] / index_df.loc[common_idx, "close"]
                rs_sma50 = rs_ratio.rolling(50).mean()
                out.loc[common_idx, "mansfield_rs"] = ((rs_ratio / rs_sma50) - 1) * 100
                out["mansfield_rs"] = out["mansfield_rs"].fillna(0.0)
            else:
                out["mansfield_rs"] = 0.0
        except:
            out["mansfield_rs"] = 0.0
    else:
        out["mansfield_rs"] = 0.0

    # --- AI DISCOVERED SYNTHETIC FEATURES (Phase 10) ---
    # Bu hibrit özellikler EvolvingFeatureFactory tarafından keşfedilmiştir.
    # RSI * Momentum (Fiyat hızı ve güç dengesi)
    out['feat_rsi_mom'] = out['rsi'] * (out['close'].pct_change(20).fillna(0) * 100)
    # Hacim Patlaması / ATR % (Oynaklığa oranlı gerçek hacim girişi)
    out['feat_vol_atr'] = out['vol_spike'] / (out['atr_pct'].replace(0, np.nan) + 0.1)
    # Trend Gücü (ADX ve EMA eğimi kombinasyonu)
    out['feat_trend_strength'] = out['adx'] * out['ema20_slope'].fillna(0)

    # --- ADVANCED ACCUMULATION (Wyckoff & VSA) ---
    # 1. Wyckoff Spring Detection (Düşüş sonrası ayı tuzağı)
    # Son 20 barın en düşüğünün altına sarkıp (fitil), kapanışı üzerinde yapma
    support_20 = out["low"].shift(1).rolling(20).min()
    out["is_spring"] = (out["low"] < support_20) & (out["close"] > support_20) & (out["in_bear_market"])
    
    # 2. VSA: Stopping Volume (Düşüşü durduran devasa hacim)
    # Fiyat düşerken (veya dipte) ortalamanın 2.5 katı hacim ve dar spread (kapanış yüksekte)
    out["stopping_volume"] = (out["vol_spike"] > 2.5) & (out["close"] > out["low"] + (out["high"] - out["low"]) * 0.5) & (out["drop_from_52w_high"] > 20)
    
    # 3. VSA: No Supply Test (Arzsızlık testi)
    # Fiyatın hafifçe yeni bir düşük yapması ama hacmin çok düşük (vol_spike < 0.7) olması
    out["no_supply_test"] = (out["low"] <= out["low"].shift(1)) & (out["vol_spike"] < 0.7) & (out["rsi"] < 45)
    
    # 4. Relative Strength vs Index (Dipten kopuş teyidi)
    if index_df is not None and not index_df.empty:
        # Endeks düşerken veya yatayken hissenin yükselmesi
        idx_ret = index_df["close"].pct_change(3)
        sym_ret = out["close"].pct_change(3)
        out["rs_vs_market"] = (sym_ret > idx_ret) & (idx_ret < 0)

    return out

def calculate_price_targets(base_df: pd.DataFrame) -> Optional[dict]:
    from utils import _safe_get
    if base_df is None or len(base_df) < 60:
        return None
    
    last = base_df.iloc[-1]
    close = float(last["close"])
    atr = float(_safe_get(last, "atr", 0.0))
    bb_upper = float(_safe_get(last, "bb_upper", close))
    sma50 = float(_safe_get(last, "sma50", 0.0))
    sma200 = float(_safe_get(last, "sma200", 0.0))
    
    if atr == 0 or close == 0:
        return None
    
    atr_t1 = close + (2.0 * atr)
    atr_t2 = close + (3.5 * atr)
    atr_t3 = close + (5.0 * atr)
    atr_stop = close - (1.5 * atr)
    
    lookback = min(120, len(base_df) - 1)
    recent = base_df.tail(lookback)
    swing_low = float(recent["low"].min())
    swing_high = float(recent["high"].max())
    swing_range = swing_high - swing_low
    
    fib_1272 = swing_low + (swing_range * 1.272)
    fib_1618 = swing_low + (swing_range * 1.618)
    fib_2000 = swing_low + (swing_range * 2.000)
    
    if close >= swing_high * 0.98:
        fib_targets = [fib_1272, fib_1618, fib_2000]
    else:
        fib_targets = [swing_high, fib_1272, fib_1618]
    
    res_20 = float(base_df.tail(20)["high"].max())
    res_60 = float(base_df.tail(60)["high"].max())
    res_120 = float(recent["high"].max())
    
    bb_target = bb_upper if bb_upper > close else close * 1.03
    ma_targets = []
    if sma50 > close: ma_targets.append(sma50)
    if sma200 > close: ma_targets.append(sma200)
    
    support_382 = swing_high - (swing_range * 0.382)
    # support_500 = swing_high - (swing_range * 0.500)
    # support_618 = swing_high - (swing_range * 0.618)
    
    all_targets = []
    all_targets.extend([(atr_t1, "ATR"), (atr_t2, "ATR"), (atr_t3, "ATR")])
    for ft in fib_targets:
        if ft > close * 1.005:
            all_targets.append((ft, "FIB"))
    for rv, lbl in [(res_20, "R20"), (res_60, "R60"), (res_120, "R120")]:
        if rv > close * 1.005:
            all_targets.append((rv, lbl))
    if bb_target > close * 1.005:
        all_targets.append((bb_target, "BB"))
    for mv in ma_targets:
        all_targets.append((mv, "MA"))
    
    all_targets.sort(key=lambda x: x[0])
    
    if len(all_targets) == 0:
        return None
    
    kisa_targets = [t for t in all_targets if t[0] <= close * 1.08]
    orta_targets = [t for t in all_targets if close * 1.05 < t[0] <= close * 1.18]
    uzun_targets = [t for t in all_targets if t[0] > close * 1.12]
    
    def weighted_avg(targets):
        if not targets: return None
        total = sum(t[0] for t in targets)
        return total / len(targets)
    
    t1 = weighted_avg(kisa_targets) if kisa_targets else (close + 1.5 * atr)
    t2 = weighted_avg(orta_targets) if orta_targets else (close + 3.0 * atr)
    t3 = weighted_avg(uzun_targets) if uzun_targets else (close + 5.0 * atr)
    
    if t2 <= t1: t2 = t1 * 1.03
    if t3 <= t2: t3 = t2 * 1.05
    
    fib_stop = support_382 if support_382 < close else atr_stop
    smart_stop = (atr_stop * 0.6 + fib_stop * 0.4)
    smart_stop = min(smart_stop, close * 0.96)
    
    t1_pct = ((t1 - close) / close) * 100
    t2_pct = ((t2 - close) / close) * 100
    t3_pct = ((t3 - close) / close) * 100
    stop_pct = ((smart_stop - close) / close) * 100
    
    return {
        "Hedef 1": round(t1, 2),
        "Hedef 1 %": round(t1_pct, 1),
        "Hedef 2": round(t2, 2),
        "Hedef 2 %": round(t2_pct, 1),
        "Hedef 3": round(t3, 2),
        "Hedef 3 %": round(t3_pct, 1),
        "Stop Loss": round(smart_stop, 2),
        "Stop %": round(stop_pct, 1),
        "Fiyat": round(close, 2),
    }
