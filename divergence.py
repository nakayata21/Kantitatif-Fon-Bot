class DivergenceEngine:
    def __init__(self):
        self.pivot_period = 5
        self.max_pivots_to_check = 10
        self.max_bars_to_check = 100
        self.min_divergence_count = 2
        self.source_mode = "high_low"   # "close" or "high_low"
        self.require_confirmation = True

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

        all_signals = []

        for indicator_name in indicators:
            series = indicators[indicator_name]

            bullish_signals = self.scan_low_side_divergences(
                candles=candles,
                indicator_name=indicator_name,
                indicator_values=series,
                pivot_lows=pivots["pivot_lows"]
            )

            bearish_signals = self.scan_high_side_divergences(
                candles=candles,
                indicator_name=indicator_name,
                indicator_values=series,
                pivot_highs=pivots["pivot_highs"]
            )

            for s in bullish_signals:
                all_signals.append(s)

            for s in bearish_signals:
                all_signals.append(s)

        grouped = {}
        for signal in all_signals:
            idx = signal["current_index"]
            if idx not in grouped:
                grouped[idx] = []
            grouped[idx].append(signal)

        filtered_signals = []
        for idx in grouped:
            if len(grouped[idx]) >= self.min_divergence_count:
                for s in grouped[idx]:
                    filtered_signals.append(s)

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

    def scan_low_side_divergences(self, candles, indicator_name, indicator_values, pivot_lows):
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
        indicator_pivot
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

        price_strength = self.absolute_percent_change(price_pivot, price_current)
        indicator_strength = self.absolute_percent_change(indicator_pivot, indicator_current)

        score = base
        score += min(10, bars_distance / 8)
        score += min(10, price_strength / 2)
        score += min(10, indicator_strength / 2)

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

            if dtype in ["positive_regular", "positive_hidden"]:
                bullish += 1
            else:
                bearish += 1

            if ind not in by_indicator:
                by_indicator[ind] = 0
            by_indicator[ind] += 1

            if dtype not in by_type:
                by_type[dtype] = 0
            by_type[dtype] += 1

        bias = "neutral"
        if bullish > bearish:
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
            return "No strong divergence cluster detected."

        strongest = top_signals[0]
        return (
            "Bias is " + bias +
            ". Strongest signal: " + strongest["divergence_type"] +
            " on " + strongest["indicator"] +
            " with score " + str(strongest["score"]) +
            ". Use divergence as context, not standalone trade trigger."
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
