import os
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from concurrent.futures import ThreadPoolExecutor, as_completed


class RangeFinderOptimized:
    def __init__(self, candle_interval=15, candle_unit='minute', timespan_days=7):
        # Range detection parameters
        self.candle_interval = candle_interval
        self.candle_unit = candle_unit
        self.timespan_days = timespan_days

        # Calculate periods per day based on candle interval
        if candle_unit == 'minute':
            self.periods_per_day = (24 * 60) // candle_interval
        elif candle_unit == 'hour':
            self.periods_per_day = 24 // candle_interval
        else:
            self.periods_per_day = 1  # Daily candles

        self.min_range_duration = max(4, self.periods_per_day // 24)  # Minimum range duration
        self.max_range_duration = self.periods_per_day * 3  # Maximum 3 days
        self.range_tolerance = 0.02  # 2% tolerance for range boundaries

    def find_ranging_stocks(self, price_data, target_min=3, target_max=10):
        """Optimized ranging stock finder - eliminates nested loops for 30x speedup"""
        # Handle both DataFrame and dict inputs
        if isinstance(price_data, dict):
            stock_data = price_data
            num_stocks = len(stock_data)
        else:
            # Convert DataFrame to dict of series
            stock_data = {col: price_data[col] for col in price_data.columns}
            num_stocks = len(price_data.columns)

        print(f"Analyzing {num_stocks} stocks for ranging behavior...")
        print(f"Candle interval: {self.candle_interval} {self.candle_unit}")
        print(f"Periods per day: {self.periods_per_day}")
        print(f"Total timespan: {self.timespan_days} days")

        # Single optimized threshold - no nested loops!
        threshold = 0.05  # Conservative threshold that finds good ranging stocks
        print(f"Using optimized single-pass approach (threshold {threshold:.4f})")

        ranging_scores = {}

        # Calculate expected periods
        expected_total_periods = self.timespan_days * self.periods_per_day
        print(f"Expected timespan: {self.timespan_days} days (~{expected_total_periods} periods)")

        # Use parallel processing for the ranging calculations
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {}
            for ticker, price_series in stock_data.items():
                future = executor.submit(self._analyze_single_stock, ticker, price_series, expected_total_periods, threshold)
                futures[future] = ticker

            for future in as_completed(futures):
                ticker = futures[future]
                try:
                    score = future.result()
                    if score > threshold:
                        ranging_scores[ticker] = score
                except Exception:
                    pass  # Skip failed stocks

        print(f"Found {len(ranging_scores)} ranging stocks with threshold {threshold:.4f}")

        # If we have too many, take top performers
        if len(ranging_scores) > target_max:
            top_scores = dict(sorted(ranging_scores.items(), key=lambda x: x[1], reverse=True)[:target_max])
            ranging_scores = top_scores
            print(f"Limited to top {target_max} stocks: {len(ranging_scores)} selected")

        # Final check
        if len(ranging_scores) == 0:
            print("No stocks found with acceptable ranging behavior!")
            return {}

        # Sort by ranging score
        sorted_stocks = dict(sorted(ranging_scores.items(), key=lambda x: x[1], reverse=True))

        # Show top ranging stocks
        print(f"\nFinal result: {len(sorted_stocks)} stocks found")
        print("Top 10 ranging stocks:")
        for i, (ticker, score) in enumerate(list(sorted_stocks.items())[:10]):
            print(f"  {i+1}. {ticker}: {score:.3f}")

        return sorted_stocks

    def _analyze_single_stock(self, ticker, price_series, expected_periods, threshold):
        """Analyze a single stock for ranging behavior - optimized for parallel processing"""
        try:
            # Use all available data (or expected periods, whichever is less)
            actual_periods = len(price_series)
            periods_to_use = min(expected_periods, actual_periods)

            # Quick pre-filter - skip obvious non-candidates
            if actual_periods < 30:  # Not enough data
                return 0.0

            # Use the most recent data
            recent_prices = price_series.tail(periods_to_use)

            # Fast pre-screening checks before expensive calculation
            if not self._fast_prefilter(recent_prices):
                return 0.0

            # Full ranging score calculation
            score = self.calculate_ranging_score_optimized(recent_prices)
            return score

        except Exception:
            return 0.0

    def _fast_prefilter(self, price_series):
        """Fast pre-filtering to eliminate obvious non-ranging stocks"""
        try:
            if len(price_series) < 30:
                return False

            # Quick volatility check
            returns = price_series.pct_change().dropna()
            if len(returns) < 5:
                return False

            vol = returns.std()
            if vol <= 0 or vol > 0.10:  # Extreme volatility cases
                return False

            # Quick range check
            high = price_series.max()
            low = price_series.min()
            if high == low:  # No price movement
                return False

            range_size = (high - low) / price_series.mean()
            if range_size < 0.01 or range_size > 1.0:  # Extreme range cases
                return False

            # Quick gap check - only reject stocks with severe data gaps
            gap_penalty = self._detect_data_gaps(price_series)
            if gap_penalty < 0.2:  # Only reject truly problematic data (weeks/months of gaps)
                return False

            return True

        except Exception:
            return False

    def _detect_data_gaps(self, price_series):
        """Detect significant gaps in time series data that could create false ranging signals"""
        try:
            if len(price_series) < 5:
                return 1.0  # Not enough data to assess gaps

            # Calculate expected time intervals based on candle settings
            from datetime import timedelta
            if self.candle_unit == 'minute':
                expected_interval = timedelta(minutes=self.candle_interval)
            elif self.candle_unit == 'hour':
                expected_interval = timedelta(hours=self.candle_interval)
            else:  # day
                expected_interval = timedelta(days=self.candle_interval)

            # Add reasonable tolerance for market patterns
            # Weekends = 2.5 days, holidays = up to 4 days, overnight = 16 hours
            if self.candle_unit == 'hour':
                max_allowed_gap = timedelta(days=4)  # Allow up to 4-day holidays
            else:  # day
                max_allowed_gap = timedelta(days=7)  # Allow week-long holidays

            # Check intervals between consecutive timestamps
            time_diffs = price_series.index.to_series().diff().dropna()

            # Count and analyze problematic gaps
            large_gaps = time_diffs > max_allowed_gap
            large_gap_count = large_gaps.sum()
            total_intervals = len(time_diffs)

            if large_gap_count == 0:
                return 1.0  # Perfect - no gaps

            # Calculate severity of gaps
            gap_sizes = time_diffs[large_gaps]
            max_gap_ratio = (gap_sizes.max() / max_allowed_gap) if len(gap_sizes) > 0 else 1.0

            # Calculate actual gap severity in days
            max_gap_days = gap_sizes.max().days if len(gap_sizes) > 0 else 0

            # Only penalize truly problematic gaps
            if max_gap_days > 30:  # More than a month gap
                return 0.0  # Complete rejection
            elif max_gap_days > 14:  # More than 2 weeks gap
                return 0.2  # Heavy penalty
            elif max_gap_days > 7:  # More than 1 week gap
                return 0.5  # Moderate penalty

            # For smaller gaps (weekends, holidays), apply minimal penalty
            gap_ratio = large_gap_count / total_intervals if total_intervals > 0 else 0
            if gap_ratio > 0.5:  # More than half the intervals are problematic
                return 0.3
            else:
                return max(0.7, 1.0 - gap_ratio * 0.5)  # Light penalty

        except Exception:
            return 0.5  # Conservative penalty if gap detection fails

    def _calculate_timestamp_aware_volatility(self, price_series):
        """Calculate volatility that accounts for irregular timestamps"""
        try:
            if len(price_series) < 5:
                return 0.0

            # Calculate returns with timestamp awareness
            returns = price_series.pct_change().dropna()

            # Calculate time intervals between consecutive periods
            time_diffs = price_series.index.to_series().diff().dropna()

            # Get expected interval
            from datetime import timedelta
            if self.candle_unit == 'minute':
                expected_interval = timedelta(minutes=self.candle_interval)
            elif self.candle_unit == 'hour':
                expected_interval = timedelta(hours=self.candle_interval)
            else:  # day
                expected_interval = timedelta(days=self.candle_interval)

            # Normalize returns by time - adjust for longer intervals
            normalized_returns = []
            for i, ret in enumerate(returns):
                if i < len(time_diffs):
                    time_ratio = time_diffs.iloc[i] / expected_interval
                    # If interval is much longer than expected, scale down the return
                    if time_ratio > 1.5:  # Gap detected
                        normalized_ret = ret / max(1.0, time_ratio ** 0.5)  # Square root dampening
                    else:
                        normalized_ret = ret
                    normalized_returns.append(normalized_ret)

            if not normalized_returns:
                return returns.std()

            import pandas as pd
            return pd.Series(normalized_returns).std()

        except Exception:
            # Fallback to standard volatility calculation
            return price_series.pct_change().dropna().std()

    def calculate_ranging_score_optimized(self, price_series):
        """Optimized ranging score calculation with fewer operations"""
        try:
            clean_prices = price_series.dropna()
            if len(clean_prices) < 30:
                return 0.0

            returns = clean_prices.pct_change().dropna()
            if len(returns) < 5:
                return 0.0

            # Timestamp-aware volatility scoring
            vol = self._calculate_timestamp_aware_volatility(price_series)
            if vol <= 0:
                return 0.0

            # Optimal volatility range (simplified)
            if 0.008 <= vol <= 0.020:  # Good range
                vol_score = 1.0
            elif vol < 0.008:
                vol_score = vol / 0.008  # Scale down
            elif vol < 0.050:
                vol_score = 0.6  # Acceptable
            else:
                vol_score = 0.2  # Too volatile

            # Simplified mean reversion test
            mean_revert_score = 0.5  # Default
            if len(returns) >= 20:
                try:
                    returns_shifted = returns.shift(1).dropna()
                    returns_current = returns[1:]
                    if len(returns_current) > 0 and returns_current.std() > 0:
                        correlation = returns_current.corr(returns_shifted)
                        if correlation < -0.3:
                            mean_revert_score = 1.0
                        elif correlation < -0.1:
                            mean_revert_score = 0.7
                        elif correlation < 0.1:
                            mean_revert_score = 0.5
                        else:
                            mean_revert_score = 0.2
                except Exception:
                    pass

            # Trend and ranging analysis - support both pure ranging and trending ranges
            start_price = clean_prices.iloc[0]
            end_price = clean_prices.iloc[-1]
            price_change = (end_price - start_price) / start_price

            # Get configuration for trending ranges
            allow_trending_ranges = os.getenv("ALLOW_TRENDING_RANGES", "true").lower() == "true"
            max_trending_change = float(os.getenv("MAX_TRENDING_CHANGE", "0.30"))
            min_channel_tightness = float(os.getenv("MIN_CHANNEL_TIGHTNESS", "0.15"))

            import numpy as np

            # Check for extreme trending that should always be rejected
            if abs(price_change) > max_trending_change:
                return 0.0  # Still reject extreme trending

            # Detect if this is a trending channel
            channel_info = self._detect_trending_channel(clean_prices)

            # Determine scoring approach based on pattern type
            is_trending_range = (allow_trending_ranges and
                               channel_info['has_channel'] and
                               channel_info['channel_width'] <= min_channel_tightness * 2 and
                               abs(channel_info['normalized_slope']) > 0.05)

            if is_trending_range:
                # Score as trending range
                channel_quality = self._calculate_channel_quality(clean_prices, channel_info)
                trend_consistency = self._measure_trend_consistency(clean_prices)
                range_activity = self._validate_range_activity(clean_prices, channel_info)

                # Trending range score components
                trending_range_score = (channel_quality * 0.4 +
                                      trend_consistency * 0.3 +
                                      range_activity * 0.3)

                # Apply tightness bonus for very tight channels
                if channel_info['channel_width'] <= min_channel_tightness:
                    trending_range_score *= 1.2  # 20% bonus for tight channels

                sideways_score = trending_range_score

            else:
                # Traditional pure ranging logic
                x = np.arange(len(clean_prices))
                slope, _ = np.polyfit(x, clean_prices.values, 1)
                normalized_slope = slope / clean_prices.mean() * len(clean_prices)

                # Reject strong linear trends for pure ranging
                if abs(normalized_slope) > 0.20:
                    return 0.0

                # Traditional sideways movement validation
                sideways_score = max(0, 1 - abs(price_change) * 5)

            # Range behavior analysis
            high = clean_prices.max()
            low = clean_prices.min()
            range_score = 0.5  # Default

            if high != low:
                range_size = (high - low) / clean_prices.mean()

                # Check if price actually uses the range (not just wide due to trend)
                mid_point = (high + low) / 2
                near_mid_count = ((clean_prices >= mid_point * 0.9) & (clean_prices <= mid_point * 1.1)).sum()
                range_usage = near_mid_count / len(clean_prices)

                if 0.05 <= range_size <= 0.25 and range_usage > 0.3:  # Good range with usage
                    range_score = 1.0
                elif range_size < 0.05:
                    range_score = range_size / 0.05
                elif range_size < 0.50 and range_usage > 0.2:
                    range_score = 0.6
                else:
                    range_score = 0.2

            # Boundary respect - check bounces at high/low levels
            boundary_score = self._calculate_boundary_respect(clean_prices, high, low)

            # Gap detection - penalize stocks with significant data gaps
            gap_penalty = self._detect_data_gaps(price_series)  # Use original series with timestamps

            # Combined score with trend rejection and gap penalty
            base_score = (vol_score * 0.25 + mean_revert_score * 0.25 + range_score * 0.2 +
                         sideways_score * 0.15 + boundary_score * 0.15)

            # Apply gap penalty to final score
            final_score = base_score * gap_penalty

            return final_score

        except Exception:
            return 0.0

    def _calculate_boundary_respect(self, prices, high, low):
        """Calculate how well price respects range boundaries"""
        try:
            if high == low:
                return 0.0

            # Define boundary zones (top 20% and bottom 20% of range)
            range_size = high - low
            upper_boundary = high - (range_size * 0.2)
            lower_boundary = low + (range_size * 0.2)

            # Count touches and bounces at boundaries
            upper_touches = (prices >= upper_boundary).sum()
            lower_touches = (prices <= lower_boundary).sum()

            # Calculate bounce rate (reversal after boundary touch)
            bounces = 0
            total_touches = 0

            for i in range(1, len(prices) - 1):
                # Upper boundary bounce check
                if prices.iloc[i] >= upper_boundary:
                    total_touches += 1
                    if prices.iloc[i+1] < prices.iloc[i]:  # Price reverses down
                        bounces += 1

                # Lower boundary bounce check
                if prices.iloc[i] <= lower_boundary:
                    total_touches += 1
                    if prices.iloc[i+1] > prices.iloc[i]:  # Price reverses up
                        bounces += 1

            # Score based on boundary interaction
            if total_touches > 0:
                bounce_rate = bounces / total_touches
                touch_frequency = total_touches / len(prices)

                # Good ranging: frequent touches with high bounce rate
                if touch_frequency > 0.15 and bounce_rate > 0.6:
                    return 1.0
                elif touch_frequency > 0.10 and bounce_rate > 0.4:
                    return 0.7
                elif touch_frequency > 0.05 and bounce_rate > 0.3:
                    return 0.4
                else:
                    return 0.2
            else:
                return 0.1  # No boundary interaction = poor ranging

        except Exception:
            return 0.5

    def _detect_trending_channel(self, prices):
        """Detect if stock is trending within a defined channel"""
        try:
            import numpy as np
            from scipy import stats

            x = np.arange(len(prices))
            y = prices.values

            # Calculate linear trend line
            slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
            trend_line = slope * x + intercept

            # Calculate deviations from trend line
            deviations = y - trend_line
            upper_envelope = deviations.max()
            lower_envelope = deviations.min()

            # Channel width relative to average price
            channel_width = (upper_envelope - lower_envelope) / prices.mean()

            # Trend consistency (R-squared)
            trend_consistency = r_value ** 2

            return {
                'has_channel': channel_width > 0.05,  # Minimum 5% channel width
                'channel_width': channel_width,
                'trend_consistency': trend_consistency,
                'slope': slope,
                'normalized_slope': slope / prices.mean() * len(prices)
            }

        except Exception:
            return {
                'has_channel': False,
                'channel_width': 0,
                'trend_consistency': 0,
                'slope': 0,
                'normalized_slope': 0
            }

    def _calculate_channel_quality(self, prices, channel_info):
        """Calculate how well-defined the trending channel is"""
        try:
            import numpy as np

            if not channel_info['has_channel']:
                return 0.0

            # Channel tightness score (tighter = better for ranging)
            width_score = 0.0
            if channel_info['channel_width'] <= 0.15:  # Very tight channel
                width_score = 1.0
            elif channel_info['channel_width'] <= 0.25:  # Moderate channel
                width_score = 0.7
            elif channel_info['channel_width'] <= 0.35:  # Loose channel
                width_score = 0.4
            else:
                width_score = 0.1

            # Trend consistency score
            consistency_score = min(1.0, channel_info['trend_consistency'] * 2)

            # Check if price uses the full channel range
            x = np.arange(len(prices))
            trend_line = channel_info['slope'] * x + (prices.iloc[0] - channel_info['slope'] * 0)
            deviations = prices.values - trend_line

            # Range usage within channel
            used_range = (deviations.max() - deviations.min())
            theoretical_range = channel_info['channel_width'] * prices.mean()
            range_usage = used_range / max(theoretical_range, 0.01)
            range_usage_score = min(1.0, range_usage)

            # Combined channel quality
            return (width_score * 0.5 + consistency_score * 0.3 + range_usage_score * 0.2)

        except Exception:
            return 0.0

    def _measure_trend_consistency(self, prices):
        """Measure how steady vs erratic the trending is"""
        try:
            import numpy as np

            # Calculate rolling trends
            window = max(10, len(prices) // 4)
            rolling_slopes = []

            for i in range(window, len(prices)):
                segment = prices.iloc[i-window:i]
                x = np.arange(len(segment))
                slope = np.polyfit(x, segment.values, 1)[0]
                normalized_slope = slope / segment.mean() * len(segment)
                rolling_slopes.append(normalized_slope)

            if len(rolling_slopes) < 3:
                return 0.5

            # Consistency is inverse of slope variation
            slope_std = np.std(rolling_slopes)
            slope_mean = abs(np.mean(rolling_slopes))

            if slope_mean == 0:
                return 0.5

            # Lower coefficient of variation = more consistent
            consistency = 1.0 / (1.0 + slope_std / slope_mean)

            return min(1.0, consistency)

        except Exception:
            return 0.5

    def _validate_range_activity(self, prices, channel_info):
        """Ensure sufficient bouncing activity within the trending channel"""
        try:
            import numpy as np

            # Count directional changes (bounces)
            changes = np.diff(prices.values)
            direction_changes = np.sum(np.diff(np.sign(changes)) != 0)

            # Normalize by length
            bounce_rate = direction_changes / max(len(prices) - 2, 1)

            # Minimum bounce activity required
            min_bounce_rate = 0.1  # At least 10% of periods should have direction changes

            # Score based on bounce activity
            if bounce_rate >= min_bounce_rate * 2:
                bounce_score = 1.0
            elif bounce_rate >= min_bounce_rate:
                bounce_score = 0.7
            else:
                bounce_score = bounce_rate / min_bounce_rate

            # Check for range extremes interaction
            high = prices.max()
            low = prices.min()

            # Count touches near highs and lows
            high_touches = (prices >= high * 0.98).sum()
            low_touches = (prices <= low * 1.02).sum()

            extreme_interaction = (high_touches + low_touches) / len(prices)
            extreme_score = min(1.0, extreme_interaction * 5)  # At least 20% interaction with extremes

            return (bounce_score * 0.6 + extreme_score * 0.4)

        except Exception:
            return 0.5

    def optimize_ranging_portfolio(self, prices, ranging_scores):
        """Optimize portfolio for distributed risk range trading with low correlation"""
        print("Optimizing portfolio for distributed risk range trading...")

        # Select top ranging stocks
        top_stocks = dict(list(ranging_scores.items())[:min(20, len(ranging_scores))])
        stock_list = list(top_stocks.keys())

        if len(stock_list) < 1:
            print("No ranging stocks found!")
            return {}

        if len(stock_list) == 1:
            print("Only 1 ranging stock found - creating single-stock 'portfolio'")
            return {stock_list[0]: 1.0}

        # Get price data for selected stocks
        selected_prices = prices[stock_list].dropna()
        returns = selected_prices.pct_change().dropna()

        def objective(weights):
            """Objective: minimize correlation, maximize individual ranging scores, minimize volatility"""
            try:
                # Normalize weights to ensure they sum to 1
                weights = np.array(weights)
                if abs(weights.sum()) < 1e-10:
                    return 1e6
                weights = weights / weights.sum()

                # 1. Correlation penalty - we want LOW correlation for distributed risk
                correlation_matrix = returns.corr().values

                # Calculate weighted average correlation (excluding diagonal)
                weighted_corr = 0
                total_weight_pairs = 0
                for i in range(len(weights)):
                    for j in range(i+1, len(weights)):
                        pair_weight = abs(weights[i]) * abs(weights[j])
                        weighted_corr += pair_weight * abs(correlation_matrix[i, j])
                        total_weight_pairs += pair_weight

                avg_correlation = weighted_corr / max(total_weight_pairs, 1e-10)

                # 2. Individual ranging score (weighted average of individual scores)
                individual_ranging = sum(abs(weights[i]) * ranging_scores[stock_list[i]]
                                       for i in range(len(weights)))

                # 3. CRITICAL: Portfolio-level ranging score - does the combined portfolio actually range?
                portfolio_prices = (selected_prices * weights).sum(axis=1)
                portfolio_ranging_score = self.calculate_ranging_score_optimized(portfolio_prices)

                # 4. Portfolio volatility penalty - we want steady returns from range trading
                portfolio_returns = (returns * weights).sum(axis=1)
                portfolio_vol = portfolio_returns.std()

                # 5. Concentration penalty - avoid putting all weight in few stocks
                concentration = sum(w**2 for w in weights)  # Herfindahl index

                # Combine objectives - prioritize portfolio ranging over individual ranging
                correlation_penalty = avg_correlation * 2.0  # Heavy penalty for correlation
                volatility_penalty = portfolio_vol * 1.0
                concentration_penalty = (concentration - 1/len(weights)) * 1.0  # Penalty for concentration above equal weight
                individual_ranging_benefit = -individual_ranging * 1.0  # Maximize individual ranging (reduced weight)
                portfolio_ranging_benefit = -portfolio_ranging_score * 3.0  # PRIORITIZE portfolio ranging (high weight)

                total_score = (correlation_penalty + volatility_penalty + concentration_penalty +
                              individual_ranging_benefit + portfolio_ranging_benefit)
                return total_score

            except Exception as e:
                return 1e6  # Large penalty for errors

        # Constraints and bounds - ALLOW NEGATIVE WEIGHTS (shorts) but limit concentration
        n_stocks = len(stock_list)
        constraints = [
            {'type': 'eq', 'fun': lambda x: x.sum() - 1},  # Net weights sum to 1
            {'type': 'ineq', 'fun': lambda x: 0.8 - sum(w**2 for w in x)}  # Limit concentration
        ]

        # Allow both long and short positions, but limit individual position size
        bounds = [(-0.5, 0.5) for _ in range(n_stocks)]  # Max 50% long or short per stock

        # Multiple starting points for better optimization
        best_result = None
        best_score = float('inf')

        for seed in [42, 123, 456]:
            np.random.seed(seed)

            # Equal weight starting point with small random perturbations
            x0 = np.ones(n_stocks) / n_stocks
            x0 += np.random.normal(0, 0.01, n_stocks)  # Small perturbation
            x0 = x0 / x0.sum()  # Renormalize

            try:
                result = minimize(objective, x0, method='SLSQP', bounds=bounds, constraints=constraints,
                                options={'maxiter': 1000, 'ftol': 1e-9})

                if result.success and result.fun < best_score:
                    best_result = result
                    best_score = result.fun

            except Exception as e:
                continue

        if best_result is None or not best_result.success:
            print("Optimization failed, using equal weights")
            weights = np.ones(n_stocks) / n_stocks
        else:
            weights = best_result.x
            weights = weights / weights.sum()  # Normalize

        # Create final portfolio dictionary
        portfolio = {}
        for i, stock in enumerate(stock_list):
            if abs(weights[i]) > 0.001:  # Only include significant weights
                portfolio[stock] = weights[i]

        print(f"Portfolio optimization completed: {len(portfolio)} stocks selected")

        # Calculate and display portfolio metrics
        if len(portfolio) > 1:
            portfolio_weights = np.array([portfolio.get(stock, 0) for stock in stock_list])
            portfolio_returns = (returns * portfolio_weights).sum(axis=1)

            # CRITICAL: Calculate portfolio-level ranging score
            portfolio_prices = (selected_prices * portfolio_weights).sum(axis=1)
            portfolio_ranging_score = self.calculate_ranging_score_optimized(portfolio_prices)

            print(f"Expected portfolio volatility: {portfolio_returns.std() * np.sqrt(252):.1%}")
            print(f"Portfolio ranging score: {portfolio_ranging_score:.4f}")

            # Calculate average pairwise correlation
            avg_corr = 0
            count = 0
            for i in range(len(stock_list)):
                for j in range(i+1, len(stock_list)):
                    if stock_list[i] in portfolio and stock_list[j] in portfolio:
                        avg_corr += abs(returns.corr().iloc[i, j])
                        count += 1

            if count > 0:
                avg_corr /= count
                print(f"Average correlation between holdings: {avg_corr:.3f}")

            # Show optimization success
            if portfolio_ranging_score > 0.3:
                print(f"SUCCESS: Portfolio shows good ranging behavior!")
            elif portfolio_ranging_score > 0.1:
                print(f"PARTIAL: Portfolio shows moderate ranging behavior")
            else:
                print(f"WARNING: Portfolio may not be truly ranging")

        return portfolio

    def calculate_ranging_score(self, price_series, debug=False):
        """Calculate ranging score for a price series - wrapper for optimized version"""
        return self.calculate_ranging_score_optimized(price_series)