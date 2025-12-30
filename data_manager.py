import os
import gc
import pandas as pd
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils import update_line
from ticker_cache import TickerCache

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
    PARQUET_AVAILABLE = True
except ImportError:
    PARQUET_AVAILABLE = False
    raise ImportError("PyArrow is required for the new weekly Parquet system")


class DataManager:
    def __init__(self, client, config):
        self.client = client
        self.config = config
        self.candles_dir = os.path.join(config.data_dir, "candles")
        os.makedirs(self.candles_dir, exist_ok=True)
        self.non_stock_instruments = self._build_non_stock_list()

        # Initialize ticker cache for massive API speedup
        ticker_cache_dir = os.path.join(config.data_dir, "ticker_cache")
        self.ticker_cache = TickerCache(client, cache_dir=ticker_cache_dir)

    def _build_non_stock_list(self):
        """Get non-stock instrument patterns from config"""
        return {
            'etf_patterns': self.config.etf_patterns,
            'reit_patterns': self.config.reit_patterns,
            'known_funds': self.config.known_funds
        }

    def is_stock_instrument(self, ticker):
        """Check if ticker represents a stock using cached API data - super fast!"""
        return self.ticker_cache.is_stock_instrument(ticker)

    def is_valid_for_trading(self, ticker):
        """Check if ticker is valid for trading (stock + TradingView available)"""
        return self.ticker_cache.is_valid_stock_for_trading(ticker)

    def _is_stock_heuristic(self, ticker):
        """Fallback heuristic method for checking if ticker is a stock"""
        ticker_upper = ticker.upper()

        # Check against known funds/ETFs
        if ticker_upper in self.non_stock_instruments['known_funds']:
            return False

        # Check for ETF patterns
        for pattern in self.non_stock_instruments['etf_patterns']:
            if pattern in ticker_upper:
                return False

        # Check for REIT patterns
        for pattern in self.non_stock_instruments['reit_patterns']:
            if pattern in ticker_upper:
                return False

        # Additional heuristics for ETFs/funds
        # Many ETFs have 3-letter tickers that are all uppercase common words
        if len(ticker_upper) == 3 and ticker_upper in self.config.three_letter_non_stocks:
            return False

        # Check for fund-like naming patterns
        if any(suffix in ticker_upper for suffix in self.config.fund_like_suffixes):
            return False

        # If ticker has numbers (often funds/ETFs)
        if any(char.isdigit() for char in ticker_upper):
            return False

        # Default to assuming it's a stock
        return True

    def _get_week_number(self, date_str):
        """Get ISO week number for a date string"""
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        return date_obj.isocalendar()[1]

    def _get_year(self, date_str):
        """Get year for a date string"""
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        return date_obj.year

    def _get_weekly_filename(self, ticker, exchange, interval, year, week_number):
        """Generate weekly Parquet filename (no ETH suffix - always store complete data)"""
        return f"{ticker}_{exchange}_{interval}_{year}_{week_number:02d}.pqt"

    def _get_weeks_for_timespan(self, start_date, end_date):
        """Get list of (year, week_number) tuples for the given date range"""
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        weeks = set()
        current_dt = start_dt
        while current_dt <= end_dt:
            year, week, _ = current_dt.isocalendar()
            weeks.add((year, week))
            current_dt += timedelta(days=1)

        return sorted(weeks)

    def load_candle_data(self, ticker, start_date, end_date, interval, _retry_download=True):
        """Load candle data from weekly Parquet files with improved cache validation"""
        # Get exchange from cache - much faster than API calls
        exchange = self.ticker_cache.get_exchange(ticker)

        # Get all weeks needed for the timespan
        weeks_needed = self._get_weeks_for_timespan(start_date, end_date)

        all_data = []
        missing_weeks = []

        for year, week_number in weeks_needed:
            filename = self._get_weekly_filename(ticker, exchange, interval, year, week_number)
            filepath = os.path.join(self.candles_dir, filename)

            try:
                if os.path.exists(filepath) and os.path.getsize(filepath) > 100:  # Basic validation
                    df = pd.read_parquet(filepath)
                    if len(df) > 0:  # Ensure data is not empty
                        all_data.append(df)
                    else:
                        missing_weeks.append((year, week_number))
                else:
                    missing_weeks.append((year, week_number))
            except Exception:
                missing_weeks.append((year, week_number))

        # Check data completeness - if too many weeks are missing, try to redownload
        total_weeks_needed = len(weeks_needed)
        weeks_with_data = len(all_data)
        data_coverage = weeks_with_data / total_weeks_needed if total_weeks_needed > 0 else 0

        # If coverage is poor, try to redownload missing data once
        if data_coverage < 0.6 and missing_weeks and _retry_download:
            print(f"Missing {len(missing_weeks)} weeks for {ticker}, attempting redownload...")
            try:
                # Download fresh data for this ticker
                fresh_data = self.download_ticker_data(ticker)
                if fresh_data is not None:
                    print(f"Successfully downloaded {len(fresh_data)} data points for {ticker}")
                    # Retry loading after download (but prevent infinite recursion)
                    return self.load_candle_data(ticker, start_date, end_date, interval, _retry_download=False)
                else:
                    print(f"Download returned no data for {ticker}")
            except Exception as e:
                print(f"Redownload failed for {ticker}: {e}")
                import traceback
                traceback.print_exc()
            return None

        # If we have no data at all, return None
        if not all_data:
            return None

        # Combine all weekly data
        combined_df = pd.concat(all_data, ignore_index=False)
        combined_df = combined_df.sort_index()

        # Filter to exact date range
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)  # Include end date

        mask = (combined_df.index >= start_dt) & (combined_df.index < end_dt)
        filtered_df = combined_df[mask]

        if len(filtered_df) == 0:
            return None

        # Additional check: ensure data spans a reasonable time range
        # Reject if all data is clustered in the beginning (like "first week only")
        time_span = (filtered_df.index.max() - filtered_df.index.min()).days
        total_time_span = (end_dt - start_dt).days
        time_coverage = time_span / total_time_span if total_time_span > 0 else 0

        # Require at least 40% time coverage to avoid concentrated data
        if time_coverage < 0.4:
            return None

        close_data = filtered_df['close'].astype('float32')

        # Apply session filtering based on current config
        return self._apply_session_filter(close_data, ticker)

    def load_candle_data_ohlc(self, ticker, start_date, end_date, interval):
        """Load full OHLC candle data from weekly Parquet files"""
        # Get exchange from cache - much faster than API calls
        exchange = self.ticker_cache.get_exchange(ticker)
        # Get all weeks needed for the timespan
        weeks_needed = self._get_weeks_for_timespan(start_date, end_date)
        all_data = []
        missing_weeks = []

        for year, week_number in weeks_needed:
            filename = self._get_weekly_filename(ticker, exchange, interval, year, week_number)
            filepath = os.path.join(self.candles_dir, filename)
            try:
                if os.path.exists(filepath) and os.path.getsize(filepath) > 100:  # Basic validation
                    df = pd.read_parquet(filepath)
                    if len(df) > 0:  # Ensure data is not empty
                        all_data.append(df)
                    else:
                        missing_weeks.append((year, week_number))
                else:
                    missing_weeks.append((year, week_number))
            except Exception:
                missing_weeks.append((year, week_number))

        if not all_data:
            return None

        # Combine all data
        combined_df = pd.concat(all_data)
        combined_df = combined_df.sort_index()
        combined_df = combined_df[~combined_df.index.duplicated(keep='first')]

        # Filter by date range
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        filtered_df = combined_df[(combined_df.index >= start_dt) & (combined_df.index <= end_dt)]

        if len(filtered_df) == 0:
            return None

        # Ensure we have all required OHLC columns
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        for col in required_columns:
            if col not in filtered_df.columns:
                return None

        # Additional validation: ensure OHLC data makes sense
        if (filtered_df['high'] < filtered_df['low']).any():
            return None
        if (filtered_df['high'] < filtered_df['open']).any() or (filtered_df['high'] < filtered_df['close']).any():
            return None
        if (filtered_df['low'] > filtered_df['open']).any() or (filtered_df['low'] > filtered_df['close']).any():
            return None

        # Additional check: ensure data spans a reasonable time range
        time_span = (filtered_df.index.max() - filtered_df.index.min()).days
        total_time_span = (end_dt - start_dt).days
        time_coverage = time_span / total_time_span if total_time_span > 0 else 0

        # Require at least 40% time coverage to avoid concentrated data
        if time_coverage < 0.4:
            return None

        return filtered_df[required_columns].astype('float32')

    def save_candle_data(self, ticker, start_date, end_date, interval, bars):
        """Save candle data to weekly Parquet files"""
        # Get exchange from cache - much faster than API calls
        exchange = self.ticker_cache.get_exchange(ticker)

        # Convert bars to DataFrame
        df = pd.DataFrame([b.__dict__ for b in bars])
        if 'timestamp' not in df.columns:
            return

        df['t'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df.set_index('t')
        df = df.sort_index()

        # Group data by week and save separately
        weeks_data = {}
        for timestamp, row in df.iterrows():
            year, week, _ = timestamp.isocalendar()
            week_key = (year, week)

            if week_key not in weeks_data:
                weeks_data[week_key] = []
            weeks_data[week_key].append(row)

        # Save each week's data with incremental updates
        for (year, week_number), week_rows in weeks_data.items():
            new_week_df = pd.DataFrame(week_rows)

            # Keep only essential columns for space efficiency
            new_week_df = new_week_df[['open', 'high', 'low', 'close', 'volume']].astype('float32')

            filename = self._get_weekly_filename(ticker, exchange, interval, year, week_number)
            filepath = os.path.join(self.candles_dir, filename)

            try:
                # Check if file already exists
                if os.path.exists(filepath) and os.path.getsize(filepath) > 100:
                    # Load existing data
                    existing_df = pd.read_parquet(filepath)

                    # Merge new data with existing data
                    combined_df = pd.concat([existing_df, new_week_df])

                    # Remove duplicates (keep latest) and sort
                    combined_df = combined_df[~combined_df.index.duplicated(keep='last')]
                    combined_df = combined_df.sort_index()

                    # Save merged data
                    combined_df.to_parquet(filepath, compression='snappy')
                    print(f"Updated {filename} with {len(new_week_df)} new periods (total: {len(combined_df)})")
                else:
                    # No existing file, save new data
                    new_week_df.to_parquet(filepath, compression='snappy')
                    print(f"Created {filename} with {len(new_week_df)} periods")

            except Exception as e:
                print(f"Warning: Failed to save {filename}: {e}")
                continue

    def download_ticker_data(self, ticker):
        """Download complete data for a single ticker (all trading sessions)"""
        try:
            bars = self.client.get_aggs(
                ticker,
                self.config.candle_interval,
                self.config.candle_unit,
                from_=self.config.start_date,
                to=self.config.end_date,
                adjusted=True,
                sort="asc"
            )
            bars_list = list(bars)

            if not bars_list:
                return None

            # Return processed data for immediate use and validate quality
            df = pd.DataFrame(b.__dict__ for b in bars_list)
            if 'timestamp' not in df.columns:
                return None

            df['t'] = pd.to_datetime(df.timestamp, unit='ms')
            close_data = df.set_index('t')['close'].astype('float32')
            del df

            # Validate data quality before saving to cache
            if not self._validate_data_quality(close_data):
                return None

            if self.config.verbose:
                print(f"Downloaded complete data: {len(close_data)} periods for {ticker}")

            # Always save complete data to cache (no session filtering at storage level)
            self.save_candle_data(ticker, self.config.start_date, self.config.end_date, self.config.interval, bars_list)

            # Apply session filtering for immediate return (processing level)
            return self._apply_session_filter(close_data, ticker)

        except Exception as e:
            return None

    def _apply_session_filter(self, close_data, ticker):
        """Apply trading session filter during processing (not storage)"""
        if self.config.include_extended_hours:
            # ETH: Return all data
            if self.config.verbose:
                print(f"Using complete data (ETH): {len(close_data)} periods for {ticker}")
            return close_data
        else:
            # RTH: Filter to regular hours only
            filtered_data = self._filter_regular_hours_series(close_data)
            if self.config.verbose:
                print(f"Filtered to RTH: {len(filtered_data)} periods for {ticker}")
            return filtered_data

    def _filter_regular_hours_series(self, close_data):
        """Filter Series to regular trading hours only (9:30 AM - 4:00 PM ET)"""
        if len(close_data) == 0:
            return close_data

        # Convert to Eastern Time for proper filtering
        timestamps_et = close_data.index.tz_localize('UTC').tz_convert('US/Eastern')

        # Filter to weekdays only (Monday=0, Friday=4)
        weekdays = timestamps_et.weekday < 5

        # Filter to regular market hours (9:30 AM - 4:00 PM ET)
        market_hours = (timestamps_et.time >= pd.Timestamp('09:30:00').time()) & \
                      (timestamps_et.time <= pd.Timestamp('16:00:00').time())

        # Apply both filters
        mask = weekdays & market_hours
        filtered_data = close_data[mask]

        return filtered_data

    def _filter_regular_hours(self, df):
        """Filter DataFrame to regular trading hours only (9:30 AM - 4:00 PM ET)"""
        # Convert to Eastern Time for proper filtering
        df_et = df.copy()
        df_et.index = df_et.index.tz_localize('UTC').tz_convert('US/Eastern')

        # Filter to weekdays only (Monday=0, Friday=4)
        weekdays = df_et.index.weekday < 5

        # Filter to regular market hours (9:30 AM - 4:00 PM ET)
        market_hours = (df_et.index.time >= pd.Timestamp('09:30:00').time()) & \
                      (df_et.index.time <= pd.Timestamp('16:00:00').time())

        # Apply both filters
        filtered_df = df_et[weekdays & market_hours]

        # Convert back to UTC for consistency
        filtered_df.index = filtered_df.index.tz_convert('UTC').tz_localize(None)

        return filtered_df

    def _dataframe_to_bars_list(self, df):
        """Convert filtered DataFrame back to bars list format for saving"""
        bars_list = []
        for timestamp, row in df.iterrows():
            # Create a simple object that mimics the original bar structure
            bar = type('Bar', (), {})()
            bar.timestamp = int(timestamp.timestamp() * 1000)  # Convert to milliseconds
            bar.open = float(row.get('open', row['close']))
            bar.high = float(row.get('high', row['close']))
            bar.low = float(row.get('low', row['close']))
            bar.close = float(row['close'])
            bar.volume = int(row.get('volume', 0))
            bars_list.append(bar)
        return bars_list

    def _validate_trading_session_data(self, close_data, ticker):
        """Validate that data matches expected trading session (ETH vs RTH)"""
        if len(close_data) == 0:
            return True

        # Convert timestamps to Eastern Time for validation
        timestamps_et = close_data.index.tz_localize('UTC').tz_convert('US/Eastern')

        # Count data points by session
        pre_market = 0
        regular_hours = 0
        after_hours = 0

        for ts in timestamps_et:
            hour = ts.hour
            minute = ts.minute
            time_decimal = hour + minute / 60.0

            if time_decimal < 9.5:  # Before 9:30 AM
                pre_market += 1
            elif time_decimal > 16.0:  # After 4:00 PM
                after_hours += 1
            else:  # 9:30 AM - 4:00 PM
                regular_hours += 1

        total_points = len(close_data)
        extended_hours_points = pre_market + after_hours
        extended_hours_pct = extended_hours_points / total_points * 100 if total_points > 0 else 0

        # Log session breakdown
        session_type = "ETH" if self.config.include_extended_hours else "RTH"
        print(f"{ticker} {session_type} validation:")
        print(f"  Pre-market: {pre_market} points")
        print(f"  Regular hours: {regular_hours} points")
        print(f"  After-hours: {after_hours} points")
        print(f"  Extended hours: {extended_hours_pct:.1f}% of data")

        # Validation logic
        if self.config.include_extended_hours:
            # ETH should have some extended hours data (unless market was closed)
            if extended_hours_points == 0 and total_points > 10:
                print(f"WARNING: ETH file for {ticker} has no extended hours data")
        else:
            # RTH should have NO extended hours data
            if extended_hours_points > 0:
                print(f"WARNING: RTH file for {ticker} contains {extended_hours_points} extended hours data points")
                return False

        return True

    def _load_ticker_batch_fast(self, ticker_batch):
        """Load a batch of tickers using the new weekly Parquet system with aggressive parallelization"""
        batch_data = {}

        # Use maximum parallelization for data loading (IO-bound operations)
        max_workers = min(64, len(ticker_batch))  # Increased to 64 threads for maximum throughput
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self._load_single_ticker, ticker): ticker for ticker in ticker_batch}

            for future in as_completed(futures):
                ticker = futures[future]
                try:
                    data = future.result()
                    if data is not None:
                        batch_data[ticker] = data
                except Exception:
                    pass  # Skip failed tickers

        return batch_data

    def _load_single_ticker(self, ticker):
        """Load a single ticker with basic caching and pre-filtering"""
        # Try cache first
        cached_data = self.load_candle_data(ticker, self.config.start_date, self.config.end_date, self.config.interval)
        if cached_data is not None:
            # Quick pre-filter to skip obviously bad data
            if self._quick_prefilter(cached_data):
                return cached_data
            else:
                return None  # Skip this ticker

        # Download if not cached
        return self.download_ticker_data(ticker)

    def _quick_prefilter(self, price_series):
        """Quick pre-filter to eliminate obviously unsuitable stocks"""
        try:
            if len(price_series) < 10:
                return False

            # Basic price range check
            mean_price = price_series.mean()
            if mean_price < 0.10 or mean_price > 50000:
                return False

            # Data completeness check
            if price_series.isna().sum() / len(price_series) > 0.6:
                return False

            # Basic volatility check
            returns = price_series.pct_change().dropna()
            if len(returns) < 5:
                return True

            volatility = returns.std()
            if volatility < 0.0005 or volatility > 0.50:
                return False

            # Price variation check
            if price_series.max() == price_series.min():
                return False

            return True

        except Exception:
            return True

    def _validate_data_quality(self, price_series):
        """Validate data quality to avoid saving incomplete data with gaps"""
        try:
            if len(price_series) < 10:
                return False

            # Check time coverage - ensure data spans reasonable time range
            start_dt = datetime.strptime(self.config.start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(self.config.end_date, "%Y-%m-%d")
            total_time_span = (end_dt - start_dt).days

            if len(price_series) > 0:
                actual_time_span = (price_series.index.max() - price_series.index.min()).days
                time_coverage = actual_time_span / total_time_span if total_time_span > 0 else 0

                # Require at least 40% time coverage to avoid "first week only" data
                if time_coverage < 0.4:
                    return False

            # Check for reasonable data density based on candle unit
            business_days = total_time_span * (5 / 7)  # 5 trading days per week

            if self.config.candle_unit == 'day':
                # For daily data: expect 1 period per trading day
                expected_periods = business_days / self.config.candle_interval
            else:
                # For intraday data: expect periods based on market hours
                market_hours_per_day = 6.5  # NYSE: 9:30 AM - 4:00 PM = 6.5 hours
                expected_periods = business_days * (market_hours_per_day / self.config.candle_interval)

            actual_periods = len(price_series)
            density = actual_periods / expected_periods if expected_periods > 0 else 0

            # Require at least 30% data density (much more reasonable for trading hours)
            if density < 0.3:
                return False

            return True

        except Exception:
            return False