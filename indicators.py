
import math
import numpy as np
import pandas as pd
from typing import Tuple, Optional
import ta
from sentiment_service import SentimentFeatureEngine

# Global singleton engine to avoid reloading BERT model multiple times
_SENTIMENT_ENGINE = None

def get_sentiment_engine():
    global _SENTIMENT_ENGINE
    if _SENTIMENT_ENGINE is None:
        try:
            _SENTIMENT_ENGINE = SentimentFeatureEngine()
        except:
            pass # NLP model fail, fallback to neutral
    return _SENTIMENT_ENGINE

def normalize(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).lower() for c in out.columns]
    for c in ["open", "high", "low", "close"]:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    if "volume" not in out.columns:
        out["volume"] = 0
    out["volume"] = pd.to_numeric(out["volume"], errors="coerce").fillna(0)
    return out.dropna(subset=["open", "high", "low", "close"])

def _ut_bot_numpy(close_arr: np.ndarray, loss_arr: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """UT Bot trailing stop (Numba yok — NumPy/numpy–numba uyumsuzluğu önlenir)."""
    n = len(close_arr)
    out_stop = np.zeros(n)
    out_pos = np.zeros(n, dtype=np.int64)
    buy = np.zeros(n, dtype=bool)
    sell = np.zeros(n, dtype=bool)

    out_stop[0] = close_arr[0]
    out_pos[0] = 0

    for i in range(1, n):
        src = close_arr[i]
        src_1 = close_arr[i - 1]
        loss = loss_arr[i] if not np.isnan(loss_arr[i]) else 0.0
        prev_stop = out_stop[i - 1]

        if src > prev_stop and src_1 > prev_stop:
            out_stop[i] = max(prev_stop, src - loss)
        elif src < prev_stop and src_1 < prev_stop:
            out_stop[i] = min(prev_stop, src + loss)
        elif src > prev_stop:
            out_stop[i] = src - loss
        else:
            out_stop[i] = src + loss

        prev_pos = out_pos[i - 1]
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
    buy, sell, out_pos = _ut_bot_numpy(close_arr, loss_arr)
    return pd.Series(buy, index=close.index), pd.Series(sell, index=close.index), pd.Series(out_pos, index=close.index)

def add_indicators(df: pd.DataFrame, index_df: pd.DataFrame = None, symbol: str = None) -> pd.DataFrame:
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

    # --- Pullback Entry (uptrend retest + hacim + önceki bar yüksek kırılımı) ---
    # Koşullar: close>EMA50, EMA20>EMA50, RSI 40–55, |close-EMA20|/EMA20 < %2,
    #           volume > 1.5×vol_ma20, close > önceki mumun high
    _prev_high = out["high"].shift(1)
    out["ema20_dist_pct"] = (
        (out["close"] - out["ema20"]) / out["ema20"].replace(0, np.nan)
    ) * 100.0
    _near_ema20 = out["ema20_dist_pct"].abs() < 2.0
    _vol_pullback = out["volume"] > (out["vol_ma20"] * 1.5)
    _break_prev_high = out["close"] > _prev_high
    out["pullback_entry"] = (
        (out["close"] > out["ema50"])
        & (out["ema20"] > out["ema50"])
        & (out["rsi"] >= 40)
        & (out["rsi"] <= 55)
        & _near_ema20
        & _vol_pullback
        & _break_prev_high
    )

    # Stochastic RSI
    stoch_rsi = ta.momentum.StochRSIIndicator(close=out["close"], window=14, smooth1=3, smooth2=3, fillna=True)
    out["stoch_k"] = stoch_rsi.stochrsi_k() * 100
    out["stoch_d"] = stoch_rsi.stochrsi_d() * 100

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

    # --- Breakout Soon (sıkışma + enerji birikimi, kırılım öncesi) ---
    # BB dar + ATR% düşük + higher lows + dirence yakın (R20 altı %3) + hacim ölü değil (vol > 0.8×MA20)
    _bb_q25 = out["bb_width"].rolling(50, min_periods=20).quantile(0.25)
    _narrow_bb = out["bb_width"] < _bb_q25
    _low_atr = out["atr_pct"] < 3.0
    _dist_to_res20_pct = (
        (out["res_20"] - out["close"]) / out["res_20"].replace(0, np.nan)
    ) * 100.0
    out["dist_to_res20_pct"] = _dist_to_res20_pct.clip(lower=0.0)
    _near_res = (
        (out["res_20"] > 0)
        & (out["close"] < out["res_20"])
        & (_dist_to_res20_pct <= 3.0)
        & (_dist_to_res20_pct >= 0)
    )
    _vol_stable = out["vol_spike"] > 0.8
    hl = out["higher_lows_5"].fillna(False)
    out["breakout_soon"] = (
        _narrow_bb & _low_atr & hl & _near_res & _vol_stable
    )
    out["breakout_soon_score"] = (
        _narrow_bb.astype(int) * 20
        + _low_atr.astype(int) * 20
        + hl.astype(int) * 20
        + _near_res.astype(int) * 20
        + _vol_stable.astype(int) * 20
    )

    # --- Golden Cross + Konsolidasyon + Hacimli Kırılım ---
    # Hikaye: önce sıkışma, sonra EMA20/EMA50 yukarı kesişimi, ardından direnç üstü hacimli çıkış.
    out["ema_golden_cross"] = (
        (out["ema20"] > out["ema50"])
        & (out["ema20"].shift(1) <= out["ema50"].shift(1))
    )
    out["recent_ema_golden_cross"] = (
        out["ema_golden_cross"].rolling(5, min_periods=1).max().fillna(0).astype(bool)
    )
    out["consolidation_zone"] = (
        _narrow_bb
        & (out["range_pct_20"] <= 10.0)
        & (out["vol_ratio_5_20"] <= 0.95)
        & (out["lr_slope_20"].abs() <= 0.35)
    )
    out["recent_consolidation_zone"] = (
        out["consolidation_zone"].rolling(10, min_periods=1).max().fillna(0).astype(bool)
    )
    out["volume_breakout_confirm"] = (
        out["breakout_up"]
        & (out["vol_spike"] >= 1.6)
    )
    out["golden_cross_breakout"] = (
        out["recent_ema_golden_cross"]
        & out["recent_consolidation_zone"]
        & out["volume_breakout_confirm"]
    )
    out["golden_cross_breakout_score"] = (
        out["recent_ema_golden_cross"].astype(int) * 30
        + out["recent_consolidation_zone"].astype(int) * 30
        + out["volume_breakout_confirm"].astype(int) * 40
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
                
                # --- STATISTICAL ARBITRAGE (Pairs) SPREAD YAKALAYICI ---
                # Hissenin endekse göre anlık sapmasını Z-Skoru ile hesapla
                # Z > 2 ise aşırı değerli (Short/Hedge adayı), Z < -2 ise ucuzlamış (Alım adayı)
                rs_std50 = rs_ratio.rolling(50).std()
                out.loc[common_idx, "stat_arb_zscore"] = (rs_ratio - rs_sma50) / rs_std50.replace(0, np.nan)
                out["stat_arb_zscore"] = out["stat_arb_zscore"].fillna(0.0)
            else:
                out["mansfield_rs"] = 0.0
                out["stat_arb_zscore"] = 0.0

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
    
    # --- YENİ LFM ÖZELLİKLERİ ---
    # Emir Defteri Dengesizliği (Order Book Imbalance) Proxy'si
    # Grafiğe yansımadan önceki gizli alıcı/satıcı yığılmasını mum fitillerinden ve hacimden tahmin eder
    # Üst Fitil (Satış Baskısı) vs Alt Fitil (Alış Baskısı) 
    upper_wick = out['high'] - out[['open', 'close']].max(axis=1)
    lower_wick = out[['open', 'close']].min(axis=1) - out['low']
    wick_imbalance = (lower_wick - upper_wick) / (out['high'] - out['low']).replace(0, np.nan)
    # Hacimle çarparak "Ağırlıklı Emir Baskısı" bulma (pozitif = güçlü alıcı bekliyor)
    out['feat_order_imbalance_proxy'] = wick_imbalance.fillna(0) * out['vol_spike'].clip(0, 5)

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
        # REINDEX: Önemli - Endeks verisi hisse verisiyle aynı tarihlerde olmayabilir
        idx_ret_3 = index_df["close"].pct_change(3).reindex(out.index).fillna(0)
        sym_ret_3 = out["close"].pct_change(3).fillna(0)
        out["rs_vs_market"] = (sym_ret_3 > idx_ret_3) & (idx_ret_3 < 0) # Endeksten bağımsız yükseliş?

    # --- MARKET REJİM MOTORU (SOFT TREND) ---
    if index_df is not None and not index_df.empty:
        idx_ret_5 = index_df["close"].pct_change(5) * 100
        out["index_return_5d"] = idx_ret_5.reindex(out.index).fillna(0)
    else:
        out["index_return_5d"] = 0.0

    def _identify_regime(row):
        adx = row.get("adx", 0)
        idx_ret = row.get("index_return_5d", 0)
        if adx > 25 and idx_ret > 0.5: return "STRONG_BULL"
        elif adx > 25 and idx_ret < -0.5: return "STRONG_BEAR"
        elif adx < 20: return "CHOPPY"
        else: return "MILD_TREND"

    out["market_regime"] = out.apply(_identify_regime, axis=1)

    # === TOPARLANMA KATMANLARI (Recovery Layers) ===
    # Her katman: kapanışın o seviyenin ÜSTÜNE ilk kez geçmesi (fresh crossover)
    # Dipten toparlanıp birden fazla katmanı kıran hisseler güçlü sinyal verir.

    # Katman 1: BB Alt Bant Üstüne Çıkış (ilk dip çıkışı)
    out["layer_bb_lower_break"] = (
        (out["close"] > out["bb_lower"]) &
        (out["close"].shift(1) <= out["bb_lower"].shift(1).fillna(out["bb_lower"]))
    )
    # Katman 2: EMA20 Üstüne Çıkış (kısa vadeli momentum dönüşü)
    out["layer_ema20_break"] = (
        (out["close"] > out["ema20"]) &
        (out["close"].shift(1) <= out["ema20"].shift(1).fillna(out["ema20"]))
    )
    # Katman 3: SMA20 (BB Orta Bant) Üstüne Çıkış
    out["layer_sma20_break"] = (
        (out["close"] > out["sma20"]) &
        (out["close"].shift(1) <= out["sma20"].shift(1).fillna(out["sma20"]))
    )
    # Katman 4: MACD Histogramı Sıfır Çizgisi Kırılımı
    out["layer_macd_zero"] = (
        (out["macd_hist"] > 0) &
        (out["macd_hist"].shift(1) <= 0)
    )
    # Katman 5: RSI 50 Kırılımı (trende dönüş onayı)
    out["layer_rsi_50"] = (
        (out["rsi"] > 50) &
        (out["rsi"].shift(1) <= 50)
    )
    # Katman 6: SMA50 Üstüne Çıkış (orta vade dönüşü - kritik)
    out["layer_sma50_break"] = (
        (out["close"] > out["sma50"]) &
        (out["close"].shift(1) <= out["sma50"].shift(1).fillna(out["sma50"]))
    )
    # Katman 7: 20-Günlük Direnç Kırılımı (breakout)
    # breakout_up = close > res_20 zaten var, taze kırılımı izole et
    out["layer_res20_break"] = (
        out["breakout_up"] &
        (~out["breakout_up"].shift(1).fillna(False))
    )
    # Katman 8: SMA200 Üstüne Çıkış (uzun vade dönüşü - en güçlü)
    _sma200_valid = out["sma200"].notna() & (out["sma200"] > 0)
    out["layer_sma200_break"] = (
        _sma200_valid &
        (out["close"] > out["sma200"]) &
        (out["close"].shift(1) <= out["sma200"].shift(1).fillna(0))
    )

    _layer_cols = [
        "layer_bb_lower_break", "layer_ema20_break", "layer_sma20_break",
        "layer_macd_zero", "layer_rsi_50", "layer_sma50_break",
        "layer_res20_break", "layer_sma200_break",
    ]
    _layer_int = out[_layer_cols].astype(int)

    # Son 5 bar içinde kaç farklı katman geçildi (0-8)
    out["recovery_layer_count"] = (
        _layer_int.rolling(5, min_periods=1).max().sum(axis=1).fillna(0).astype(int)
    )
    # Bugün taze geçilen katman sayısı
    out["fresh_layer_count"] = _layer_int.sum(axis=1).fillna(0).astype(int)

    # --- 9. VOLUME PROFILE & POC (Point of Control) ---
    def _calculate_volume_profile(df, window=50):
        if len(df) < window: return pd.Series(index=df.index, data=0.0), pd.Series(index=df.index, data=0.0)
        
        poc_list = []
        va_high_list = []
        
        # Performance: vectorize where possible, but volume profile is inherently window-based
        for i in range(len(df)):
            if i < window:
                poc_list.append(0.0)
                va_high_list.append(0.0)
                continue
            
            sub = df.iloc[i-window+1:i+1]
            # Bins for volume distribution (approx 20 bins)
            price_min = sub["low"].min()
            price_max = sub["high"].max()
            if price_max == price_min:
                poc_list.append(price_min)
                va_high_list.append(price_max)
                continue
                
            bins = np.linspace(price_min, price_max, 21)
            # Assign volume to bins based on H-L range overlap
            bin_vol = np.zeros(20)
            for _, row in sub.iterrows():
                h, l, v = row["high"], row["low"], row["volume"]
                # Simplify: middle point assignment
                mid = (h + l) / 2
                idx = np.digitize(mid, bins) - 1
                if 0 <= idx < 20:
                    bin_vol[idx] += v
            
            # POC is the bin with max volume
            poc_idx = np.argmax(bin_vol)
            poc_price = (bins[poc_idx] + bins[poc_idx+1]) / 2
            poc_list.append(poc_price)
            
            # Value Area (Top 70% of volume)
            total_v = bin_vol.sum()
            if total_v > 0:
                sorted_indices = np.argsort(bin_vol)[::-1]
                cum_vol = 0
                va_prices = []
                for idx in sorted_indices:
                    cum_vol += bin_vol[idx]
                    va_prices.append((bins[idx] + bins[idx+1]) / 2)
                    if cum_vol >= total_v * 0.7: break
                va_high_list.append(max(va_prices) if va_prices else poc_price)
            else:
                va_high_list.append(poc_price)
                
        return pd.Series(poc_list, index=df.index), pd.Series(va_high_list, index=df.index)

    out["poc"], out["va_high"] = _calculate_volume_profile(out)
    out["dist_to_poc_pct"] = ((out["close"] - out["poc"]) / out["poc"].replace(0, np.nan)) * 100
    out["is_at_poc_support"] = (out["dist_to_poc_pct"].abs() < 1.5) & (out["close"] > out["poc"])

    # --- 10. TURKISH NLP SENTIMENT (BERT) FEATURE ---
    # Haber duygu analizini bir özellik olarak ekle
    out["feat_sentiment"] = 0.0 # Default
    if symbol:
        clean_sym = symbol.replace(".IS", "").split(":")[-1]
        engine = get_sentiment_engine()
        if engine:
            score = engine.get_sentiment_score(clean_sym)
            out["feat_sentiment"] = score

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
