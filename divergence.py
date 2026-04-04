class DivergenceEngine:
    def __init__(self):
        self.pivot_period = 5
        self.max_pivots_to_check = 10
        self.max_bars_to_check = 100
        self.min_divergence_count = 2
        self.source_mode = "high_low"   # "close" or "high_low"
        self.require_confirmation = True
        # RSI boğa uyumsuzluk / reversal: LL fiyat + HL RSI + direnç kırılımı + hacim
        self.rsi_reversal_vol_mult = 1.25
        self.rsi_reversal_min_pivot_gap = 5
        # Aynı barda 2+ gösterge şartı sağlanmasa bile yayımlanacak min. boğa uyumsuzluk skoru
        self.min_bullish_standalone_score = 72.0

    def analyze(self, candles):
        """
        candles format:
        [
            {
                "time": ...,
                "open": ...,
                "high": ...,
                "low": ...,
                "close": ...,
                "volume": ...
            }
        ]
        """

        if len(candles) < 60:
            return {
                "summary": {
                    "bias": "neutral",
                    "message": "Not enough candles for divergence analysis"
                },
                "signals": []
            }

        indicators = self.compute_indicators(candles)
        pivots = self.find_pivots(candles)

        # Boğa tarafı: gevşek çoklu gösterge yerine sıkı RSI reversal kuralı
        rsi_reversal = self.detect_rsi_bullish_reversal(
            candles, indicators["rsi"], pivots["pivot_lows"]
        )

        all_signals = []

        for indicator_name in indicators:
            series = indicators[indicator_name]

            for s in self.scan_high_side_divergences(
                candles=candles,
                indicator_name=indicator_name,
                indicator_values=series,
                pivot_highs=pivots["pivot_highs"],
            ):
                all_signals.append(s)

            for s in self.scan_low_side_divergences(
                candles=candles,
                indicator_name=indicator_name,
                indicator_values=series,
                pivot_lows=pivots["pivot_lows"],
            ):
                all_signals.append(s)

        grouped = {}
        for signal in all_signals:
            idx = signal["current_index"]
            if idx not in grouped:
                grouped[idx] = []
            grouped[idx].append(signal)

        filtered_signals = []
        seen = set()
        for idx in grouped:
            if len(grouped[idx]) >= self.min_divergence_count:
                for s in grouped[idx]:
                    filtered_signals.append(s)
                    seen.add((s["current_index"], s["indicator"], s["divergence_type"]))

        # Dip tarafı: tek gösterge (ör. RSI veya MACD) ile oluşan güçlü boğa uyumsuzluğu
        bullish_standalone_types = frozenset({"positive_regular", "positive_hidden"})
        for s in all_signals:
            if s["divergence_type"] not in bullish_standalone_types:
                continue
            key = (s["current_index"], s["indicator"], s["divergence_type"])
            if key in seen:
                continue
            if float(s.get("score", 0.0)) >= self.min_bullish_standalone_score:
                filtered_signals.append(s)
                seen.add(key)

        if rsi_reversal:
            key = (
                rsi_reversal["current_index"],
                rsi_reversal["indicator"],
                rsi_reversal["divergence_type"],
            )
            if key not in seen:
                filtered_signals.append(rsi_reversal)

        summary = self.build_summary(filtered_signals)

        return {
            "summary": summary,
            "signals": filtered_signals
        }

    def compute_indicators(self, candles):
        closes = [c["close"] for c in candles]
        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        volumes = [c["volume"] for c in candles]

        macd_line = self.compute_macd(closes, 12, 26)
        macd_signal = self.compute_ema(macd_line, 9)
        macd_hist = []

        for i in range(len(macd_line)):
            if macd_line[i] is None or macd_signal[i] is None:
                macd_hist.append(None)
            else:
                macd_hist.append(macd_line[i] - macd_signal[i])

        rsi = self.compute_rsi(closes, 14)
        stoch = self.compute_stoch(highs, lows, closes, 14)
        cci = self.compute_cci(highs, lows, closes, 20)
        momentum = self.compute_momentum(closes, 10)
        obv = self.compute_obv(closes, volumes)
        vwmacd = self.compute_vwmacd(closes, volumes, 12, 26)
        cmf = self.compute_cmf(highs, lows, closes, volumes, 21)
        mfi = self.compute_mfi(highs, lows, closes, volumes, 14)

        return {
            "macd": macd_line,
            "macd_hist": macd_hist,
            "rsi": rsi,
            "stoch": stoch,
            "cci": cci,
            "momentum": momentum,
            "obv": obv,
            "vwmacd": vwmacd,
            "cmf": cmf,
            "mfi": mfi
        }

    def find_pivots(self, candles):
        pivot_highs = []
        pivot_lows = []
        p = self.pivot_period

        for i in range(p, len(candles) - p):
            if self.source_mode == "close":
                center_high = candles[i]["close"]
                center_low = candles[i]["close"]
            else:
                center_high = candles[i]["high"]
                center_low = candles[i]["low"]

            is_pivot_high = True
            is_pivot_low = True

            for j in range(i - p, i + p + 1):
                if j == i:
                    continue

                if self.source_mode == "close":
                    compare_high = candles[j]["close"]
                    compare_low = candles[j]["close"]
                else:
                    compare_high = candles[j]["high"]
                    compare_low = candles[j]["low"]

                if center_high <= compare_high:
                    is_pivot_high = False

                if center_low >= compare_low:
                    is_pivot_low = False

            if is_pivot_high:
                pivot_highs.append({
                    "index": i,
                    "price": center_high
                })

            if is_pivot_low:
                pivot_lows.append({
                    "index": i,
                    "price": center_low
                })

        return {
            "pivot_highs": pivot_highs,
            "pivot_lows": pivot_lows
        }

    def _sma_volume(self, candles, period, end_index):
        if end_index < period - 1:
            return None
        s = 0.0
        for j in range(end_index - period + 1, end_index + 1):
            s += float(candles[j].get("volume") or 0)
        return s / period

    def detect_rsi_bullish_reversal(self, candles, rsi_values, pivot_lows):
        """
        Klasik RSI boğa reversal (AL):
        - Fiyat: ikinci dip bir önceki dipten daha düşük (lower low)
        - RSI: ikinci dipte RSI daha yüksek (higher low)
        - Kısa vadeli direnç: iki dip arasındaki tepe (max high) üzerinde kapanış
        - Hacim: onay mumunda ortalama üzeri (spike)
        """
        if len(pivot_lows) < 2 or len(candles) < 60:
            return None

        scan_index = len(candles) - 2 if self.require_confirmation else len(candles) - 1
        if scan_index <= 0:
            return None

        lows = [float(c["low"]) for c in candles]
        recent = pivot_lows[-self.max_pivots_to_check :]

        for p2_idx in range(len(recent) - 1, 0, -1):
            p2 = recent[p2_idx]
            i2 = p2["index"]
            for p1_idx in range(p2_idx - 1, -1, -1):
                p1 = recent[p1_idx]
                i1 = p1["index"]
                if i2 <= i1:
                    continue
                if i2 - i1 < self.rsi_reversal_min_pivot_gap:
                    continue

                lp1 = lows[i1]
                lp2 = lows[i2]
                if lp2 >= lp1:
                    continue

                r1 = rsi_values[i1]
                r2 = rsi_values[i2]
                if r1 is None or r2 is None:
                    continue
                if r2 <= r1:
                    continue

                highs_between = [float(candles[j]["high"]) for j in range(i1 + 1, i2)]
                if not highs_between:
                    continue
                resistance = max(highs_between)

                close_now = float(candles[scan_index]["close"])
                if close_now <= resistance:
                    continue

                vol_sma = self._sma_volume(candles, 20, scan_index)
                if vol_sma is None or vol_sma <= 0:
                    continue
                vol_now = float(candles[scan_index].get("volume") or 0)
                if vol_now < vol_sma * self.rsi_reversal_vol_mult:
                    continue

                # Kırılım ikinci dipten sonra gelmeli (aynı mumda genelde direnç altıdır)
                if scan_index <= i2:
                    continue

                return {
                    "indicator": "rsi",
                    "divergence_type": "rsi_bullish_reversal",
                    "current_index": scan_index,
                    "pivot_index": i1,
                    "bars_distance": scan_index - i1,
                    "price_current": close_now,
                    "price_pivot": lp2,
                    "indicator_current": r2,
                    "indicator_pivot": r1,
                    "score": self.score_divergence(
                        "rsi_bullish_reversal",
                        scan_index - i1,
                        close_now,
                        lp2,
                        r2,
                        r1,
                        resistance=resistance,
                    ),
                    "resistance": resistance,
                    "pivot_low_1": lp1,
                    "pivot_low_2": lp2,
                    "rsi_pivot_1": r1,
                    "rsi_pivot_2": r2,
                }

        return None

    def scan_low_side_divergences(self, candles, indicator_name, indicator_values, pivot_lows):
        """
        Klasik boğa (pozitif regular) uyumsuzluk: önceki dipten sonra fiyat daha aşağıda
        bir dip yaparken (LL) gösterge daha yukarıda bir dip yapar (HL). Sezgisel ifade:
        «RSI/MACD güçlenirken fiyat daha zayıf dip vurur» — burada karşılaştırma iki pivot
        dip arasındadır; her mumda ters yön aranmaz. MACD için hem macd çizgisi hem macd_hist taranır.
        """
        results = []
        current_index = len(candles) - 1

        if self.require_confirmation:
            scan_index = current_index - 1
        else:
            scan_index = current_index

        if scan_index <= 0:
            return results

        current_price = self.get_current_low_source(candles, scan_index)
        current_indicator = indicator_values[scan_index]

        if current_indicator is None:
            return results

        recent_pivots = pivot_lows[-self.max_pivots_to_check:]

        for pivot in reversed(recent_pivots):
            pivot_index = pivot["index"]
            pivot_price = pivot["price"]

            if pivot_index >= scan_index:
                continue

            bars_distance = scan_index - pivot_index
            if bars_distance <= 5:
                continue
            if bars_distance > self.max_bars_to_check:
                continue

            pivot_indicator = indicator_values[pivot_index]
            if pivot_indicator is None:
                continue

            # positive regular
            if current_price < pivot_price and current_indicator > pivot_indicator:
                valid = self.validate_divergence_path(
                    price_series=self.get_low_series(candles),
                    indicator_series=indicator_values,
                    start_index=pivot_index,
                    end_index=scan_index,
                    mode="low"
                )
                if valid:
                    results.append(
                        self.build_signal(
                            indicator_name,
                            "positive_regular",
                            scan_index,
                            pivot_index,
                            current_price,
                            pivot_price,
                            current_indicator,
                            pivot_indicator
                        )
                    )

            # positive hidden
            if current_price > pivot_price and current_indicator < pivot_indicator:
                valid = self.validate_divergence_path(
                    price_series=self.get_low_series(candles),
                    indicator_series=indicator_values,
                    start_index=pivot_index,
                    end_index=scan_index,
                    mode="low"
                )
                if valid:
                    results.append(
                        self.build_signal(
                            indicator_name,
                            "positive_hidden",
                            scan_index,
                            pivot_index,
                            current_price,
                            pivot_price,
                            current_indicator,
                            pivot_indicator
                        )
                    )

        return results

    def scan_high_side_divergences(self, candles, indicator_name, indicator_values, pivot_highs):
        results = []
        current_index = len(candles) - 1

        if self.require_confirmation:
            scan_index = current_index - 1
        else:
            scan_index = current_index

        if scan_index <= 0:
            return results

        current_price = self.get_current_high_source(candles, scan_index)
        current_indicator = indicator_values[scan_index]

        if current_indicator is None:
            return results

        recent_pivots = pivot_highs[-self.max_pivots_to_check:]

        for pivot in reversed(recent_pivots):
            pivot_index = pivot["index"]
            pivot_price = pivot["price"]

            if pivot_index >= scan_index:
                continue

            bars_distance = scan_index - pivot_index
            if bars_distance <= 5:
                continue
            if bars_distance > self.max_bars_to_check:
                continue

            pivot_indicator = indicator_values[pivot_index]
            if pivot_indicator is None:
                continue

            # negative regular
            if current_price > pivot_price and current_indicator < pivot_indicator:
                valid = self.validate_divergence_path(
                    price_series=self.get_high_series(candles),
                    indicator_series=indicator_values,
                    start_index=pivot_index,
                    end_index=scan_index,
                    mode="high"
                )
                if valid:
                    results.append(
                        self.build_signal(
                            indicator_name,
                            "negative_regular",
                            scan_index,
                            pivot_index,
                            current_price,
                            pivot_price,
                            current_indicator,
                            pivot_indicator
                        )
                    )

            # negative hidden
            if current_price < pivot_price and current_indicator > pivot_indicator:
                valid = self.validate_divergence_path(
                    price_series=self.get_high_series(candles),
                    indicator_series=indicator_values,
                    start_index=pivot_index,
                    end_index=scan_index,
                    mode="high"
                )
                if valid:
                    results.append(
                        self.build_signal(
                            indicator_name,
                            "negative_hidden",
                            scan_index,
                            pivot_index,
                            current_price,
                            pivot_price,
                            current_indicator,
                            pivot_indicator
                        )
                    )

        return results

    def validate_divergence_path(self, price_series, indicator_series, start_index, end_index, mode):
        if end_index <= start_index:
            return False

        p1 = price_series[start_index]
        p2 = price_series[end_index]
        i1 = indicator_series[start_index]
        i2 = indicator_series[end_index]

        if i1 is None or i2 is None:
            return False

        for i in range(start_index + 1, end_index):
            ratio = (i - start_index) / (end_index - start_index)

            projected_price = p1 + (p2 - p1) * ratio
            projected_indicator = i1 + (i2 - i1) * ratio

            actual_price = price_series[i]
            actual_indicator = indicator_series[i]

            if actual_indicator is None:
                return False

            if mode == "low":
                if actual_price < projected_price:
                    return False
                if actual_indicator < projected_indicator:
                    return False

            if mode == "high":
                if actual_price > projected_price:
                    return False
                if actual_indicator > projected_indicator:
                    return False

        return True

    def build_signal(
        self,
        indicator_name,
        divergence_type,
        current_index,
        pivot_index,
        price_current,
        price_pivot,
        indicator_current,
        indicator_pivot
    ):
        score = self.score_divergence(
            divergence_type,
            current_index - pivot_index,
            price_current,
            price_pivot,
            indicator_current,
            indicator_pivot
        )

        return {
            "indicator": indicator_name,
            "divergence_type": divergence_type,
            "current_index": current_index,
            "pivot_index": pivot_index,
            "bars_distance": current_index - pivot_index,
            "price_current": price_current,
            "price_pivot": price_pivot,
            "indicator_current": indicator_current,
            "indicator_pivot": indicator_pivot,
            "score": score
        }

    def score_divergence(
        self,
        divergence_type,
        bars_distance,
        price_current,
        price_pivot,
        indicator_current,
        indicator_pivot,
        resistance=None,
    ):
        base = 70

        if divergence_type == "positive_regular":
            base = 85
        elif divergence_type == "negative_regular":
            base = 85
        elif divergence_type == "positive_hidden":
            base = 75
        elif divergence_type == "negative_hidden":
            base = 75
        elif divergence_type == "rsi_bullish_reversal":
            base = 90

        price_strength = self.absolute_percent_change(price_pivot, price_current)
        indicator_strength = self.absolute_percent_change(indicator_pivot, indicator_current)

        score = base
        score += min(10, bars_distance / 8)
        score += min(10, price_strength / 2)
        score += min(10, indicator_strength / 2)

        if divergence_type == "rsi_bullish_reversal" and resistance and resistance > 0:
            # Kırılım mesafesi (direnç üstü ne kadar?)
            brk = ((price_current - resistance) / resistance) * 100
            score += min(5, max(0, brk))

        if score > 100:
            score = 100

        return round(score, 2)

    def build_summary(self, signals):
        bullish = 0
        bearish = 0
        by_indicator = {}
        by_type = {}

        for s in signals:
            dtype = s["divergence_type"]
            ind = s["indicator"]

            if dtype in ["positive_regular", "positive_hidden", "rsi_bullish_reversal"]:
                bullish += 1
            else:
                bearish += 1

            if ind not in by_indicator:
                by_indicator[ind] = 0
            by_indicator[ind] += 1

            if dtype not in by_type:
                by_type[dtype] = 0
            by_type[dtype] += 1

        has_rsi_rev = any(s.get("divergence_type") == "rsi_bullish_reversal" for s in signals)
        bias = "neutral"
        if has_rsi_rev:
            bias = "bullish"
        elif bullish > bearish:
            bias = "bullish"
        elif bearish > bullish:
            bias = "bearish"

        sorted_signals = sorted(signals, key=lambda x: x["score"], reverse=True)
        top_signals = sorted_signals[:5]

        return {
            "bias": bias,
            "total_signals": len(signals),
            "bullish_signals": bullish,
            "bearish_signals": bearish,
            "by_indicator": by_indicator,
            "by_type": by_type,
            "top_signals": top_signals,
            "ai_hint": self.build_ai_hint(bias, top_signals)
        }

    def build_ai_hint(self, bias, top_signals):
        if len(top_signals) == 0:
            return "Güçlü uyumsuzluk yok."

        strongest = top_signals[0]
        if strongest.get("divergence_type") == "rsi_bullish_reversal":
            return (
                "RSI boğa reversal: daha düşük dip + RSI’da daha yüksek dip, "
                "iki dip arası direnç kırıldı, hacim onayı var."
            )
        return (
            "Bias: " + bias +
            ". En güçlü: " + strongest["divergence_type"] +
            " (" + strongest["indicator"] + "), skor " + str(strongest["score"]) + "."
        )

    def get_low_series(self, candles):
        values = []
        for c in candles:
            if self.source_mode == "close":
                values.append(c["close"])
            else:
                values.append(c["low"])
        return values

    def get_high_series(self, candles):
        values = []
        for c in candles:
            if self.source_mode == "close":
                values.append(c["close"])
            else:
                values.append(c["high"])
        return values

    def get_current_low_source(self, candles, index):
        if self.source_mode == "close":
            return candles[index]["close"]
        return candles[index]["low"]

    def get_current_high_source(self, candles, index):
        if self.source_mode == "close":
            return candles[index]["close"]
        return candles[index]["high"]

    def absolute_percent_change(self, old_value, new_value):
        if old_value == 0 or old_value is None or new_value is None:
            return 0
        value = ((new_value - old_value) / abs(old_value)) * 100
        if value < 0:
            value = -value
        return value

    # --------------------
    # BASIC INDICATORS
    # --------------------

    def compute_ema(self, values, period):
        result = []
        multiplier = 2 / (period + 1)
        ema_prev = None

        for i in range(len(values)):
            v = values[i]

            if v is None:
                result.append(None)
                continue

            if ema_prev is None:
                ema_prev = v
            else:
                ema_prev = ((v - ema_prev) * multiplier) + ema_prev

            result.append(ema_prev)

        return result

    def compute_macd(self, closes, fast_period, slow_period):
        fast = self.compute_ema(closes, fast_period)
        slow = self.compute_ema(closes, slow_period)

        macd = []
        for i in range(len(closes)):
            if fast[i] is None or slow[i] is None:
                macd.append(None)
            else:
                macd.append(fast[i] - slow[i])

        return macd

    def compute_rsi(self, closes, period):
        result = [None] * len(closes)

        for i in range(period, len(closes)):
            gains = 0
            losses = 0

            for j in range(i - period + 1, i + 1):
                change = closes[j] - closes[j - 1]
                if change > 0:
                    gains += change
                else:
                    losses += -change

            if losses == 0:
                result[i] = 100
            else:
                rs = gains / losses
                result[i] = 100 - (100 / (1 + rs))

        return result

    def compute_stoch(self, highs, lows, closes, period):
        result = [None] * len(closes)

        for i in range(period - 1, len(closes)):
            hh = max(highs[i - period + 1:i + 1])
            ll = min(lows[i - period + 1:i + 1])

            if hh == ll:
                result[i] = 50
            else:
                result[i] = ((closes[i] - ll) / (hh - ll)) * 100

        return result

    def compute_cci(self, highs, lows, closes, period):
        result = [None] * len(closes)
        typical_prices = []

        for i in range(len(closes)):
            tp = (highs[i] + lows[i] + closes[i]) / 3
            typical_prices.append(tp)

        for i in range(period - 1, len(closes)):
            window = typical_prices[i - period + 1:i + 1]
            sma = sum(window) / period

            mean_dev_sum = 0
            for v in window:
                mean_dev_sum += abs(v - sma)

            mean_dev = mean_dev_sum / period

            if mean_dev == 0:
                result[i] = 0
            else:
                result[i] = (typical_prices[i] - sma) / (0.015 * mean_dev)

        return result

    def compute_momentum(self, closes, period):
        result = [None] * len(closes)

        for i in range(period, len(closes)):
            result[i] = closes[i] - closes[i - period]

        return result

    def compute_obv(self, closes, volumes):
        result = [0]

        for i in range(1, len(closes)):
            prev = result[-1]

            if closes[i] > closes[i - 1]:
                result.append(prev + volumes[i])
            elif closes[i] < closes[i - 1]:
                result.append(prev - volumes[i])
            else:
                result.append(prev)

        return result

    def compute_vwma(self, closes, volumes, period):
        result = [None] * len(closes)

        for i in range(period - 1, len(closes)):
            pv_sum = 0
            v_sum = 0

            for j in range(i - period + 1, i + 1):
                pv_sum += closes[j] * volumes[j]
                v_sum += volumes[j]

            if v_sum == 0:
                result[i] = None
            else:
                result[i] = pv_sum / v_sum

        return result

    def compute_vwmacd(self, closes, volumes, fast_period, slow_period):
        fast = self.compute_vwma(closes, volumes, fast_period)
        slow = self.compute_vwma(closes, volumes, slow_period)

        result = []
        for i in range(len(closes)):
            if fast[i] is None or slow[i] is None:
                result.append(None)
            else:
                result.append(fast[i] - slow[i])

        return result

    def compute_cmf(self, highs, lows, closes, volumes, period):
        result = [None] * len(closes)

        for i in range(period - 1, len(closes)):
            mfv_sum = 0
            vol_sum = 0

            for j in range(i - period + 1, i + 1):
                hl_range = highs[j] - lows[j]
                if hl_range == 0:
                    money_flow_multiplier = 0
                else:
                    money_flow_multiplier = ((closes[j] - lows[j]) - (highs[j] - closes[j])) / hl_range

                mfv_sum += money_flow_multiplier * volumes[j]
                vol_sum += volumes[j]

            if vol_sum == 0:
                result[i] = 0
            else:
                result[i] = mfv_sum / vol_sum

        return result

    def compute_mfi(self, highs, lows, closes, volumes, period):
        result = [None] * len(closes)
        tp = []

        for i in range(len(closes)):
            tp.append((highs[i] + lows[i] + closes[i]) / 3)

        for i in range(period, len(closes)):
            positive_flow = 0
            negative_flow = 0

            for j in range(i - period + 1, i + 1):
                raw_mf = tp[j] * volumes[j]

                if tp[j] > tp[j - 1]:
                    positive_flow += raw_mf
                elif tp[j] < tp[j - 1]:
                    negative_flow += raw_mf

            if negative_flow == 0:
                result[i] = 100
            else:
                money_ratio = positive_flow / negative_flow
                result[i] = 100 - (100 / (1 + money_ratio))

        return result
