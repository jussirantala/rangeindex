import os
import json
import pandas as pd
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import threading
import requests
from urllib.parse import quote


class TickerCache:
    def __init__(self, client, cache_dir="ticker_cache"):
        self.client = client
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

        self.cache_file = os.path.join(cache_dir, "ticker_details.json")
        self.cache_data = self._load_cache()
        self._lock = threading.Lock()  # Thread safety for concurrent access

    def _load_cache(self):
        """Load existing cache from disk"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r') as f:
                    data = json.load(f)
                print(f"Loaded ticker cache with {len(data)} entries")
                return data
            else:
                print("No existing ticker cache found")
                return {}
        except Exception as e:
            print(f"Error loading cache: {e}")
            return {}

    def _save_cache(self):
        """Save cache to disk with thread safety"""
        try:
            with self._lock:
                # Create a copy to avoid "dictionary changed size during iteration" error
                cache_copy = dict(self.cache_data)

            with open(self.cache_file, 'w') as f:
                json.dump(cache_copy, f, indent=2)
            print(f"Saved ticker cache with {len(cache_copy)} entries")
        except Exception as e:
            print(f"Error saving cache: {e}")

    def _check_tradingview_exists(self, ticker, exchange):
        """Check if ticker exists on TradingView using their API endpoint"""
        try:
            # Map exchange to TradingView format
            exchange_mapping = {
                'NYSE': 'NYSE',
                'NASDAQ': 'NASDAQ',
                'BATS': 'BATS',
                'XASE': 'AMEX',
                'AMEX': 'AMEX',
                'ARCX': 'ARCA'
            }

            tv_exchange = exchange_mapping.get(exchange, exchange)

            # Use TradingView's scanner API endpoint
            symbol = f"{tv_exchange}:{ticker}"
            url = f"https://scanner.tradingview.com/symbol"

            params = {
                'symbol': symbol,
                'fields': 'price_52_week_high,price_52_week_low',
                'no_404': 'true'
            }

            # Make API request with timeout
            response = requests.get(url, params=params, timeout=5)

            # Check if the API returns valid data
            if response.status_code == 200:
                try:
                    data = response.json()
                    # If we get valid JSON data back, the ticker exists
                    if isinstance(data, dict) and len(data) > 0:
                        return True
                    else:
                        return False
                except ValueError:
                    # If JSON parsing fails, assume it doesn't exist
                    return False
            else:
                # For non-200 status codes, assume it doesn't exist
                return False

        except Exception as e:
            # For network errors, be conservative but log
            print(f"TradingView API check failed for {ticker}: {e}, assuming exists")
            return True

    def get_ticker_details(self, ticker):
        """Get ticker details with caching"""
        ticker_upper = ticker.upper()

        # Check cache first
        if ticker_upper in self.cache_data:
            cached_entry = self.cache_data[ticker_upper]

            # Check if cache entry is recent (less than 30 days old)
            cache_date = datetime.fromisoformat(cached_entry.get('cache_date', '2020-01-01'))
            if datetime.now() - cache_date < timedelta(days=30):
                # Check if TradingView validation is missing from older cache entries
                if 'tradingview_exists' not in cached_entry and cached_entry.get('is_stock', False):
                    print(f"Adding TradingView validation to cached ticker {ticker}...")
                    cached_entry['tradingview_exists'] = self._check_tradingview_exists(
                        ticker_upper, cached_entry.get('exchange_mapped', 'NASDAQ')
                    )
                    # Update cache with new field
                    with self._lock:
                        self.cache_data[ticker_upper] = cached_entry
                    self._save_cache()

                return cached_entry

        # Cache miss - fetch from API
        try:
            print(f"Fetching ticker details for {ticker}...")
            ticker_details = self.client.get_ticker_details(ticker)

            # Extract relevant information
            cache_entry = {
                'ticker': ticker_upper,
                'name': getattr(ticker_details, 'name', ''),
                'type': getattr(ticker_details, 'type', '').upper(),
                'primary_exchange': getattr(ticker_details, 'primary_exchange', '').upper(),
                'market': getattr(ticker_details, 'market', ''),
                'currency': getattr(ticker_details, 'currency_name', ''),
                'cache_date': datetime.now().isoformat(),
                'is_stock': None,  # Will be determined by analysis
                'exchange_mapped': None  # Will be mapped later
            }

            # Determine if it's a stock based on type and name
            cache_entry['is_stock'] = self._determine_if_stock(cache_entry)

            # Map exchange code to common name
            cache_entry['exchange_mapped'] = self._map_exchange(cache_entry['primary_exchange'])

            # Check if ticker exists on TradingView (for all instruments)
            cache_entry['tradingview_exists'] = self._check_tradingview_exists(
                ticker_upper, cache_entry['exchange_mapped']
            )

            # Cache the result with thread safety
            with self._lock:
                self.cache_data[ticker_upper] = cache_entry

            # Save cache after adding new ticker (important for individual fetches)
            self._save_cache()

            return cache_entry

        except Exception as e:
            print(f"Error fetching ticker details for {ticker}: {e}")

            # Create minimal cache entry to avoid repeated failures
            cache_entry = {
                'ticker': ticker_upper,
                'name': '',
                'type': 'UNKNOWN',
                'primary_exchange': 'UNKNOWN',
                'market': '',
                'currency': '',
                'cache_date': datetime.now().isoformat(),
                'is_stock': True,  # Default to stock if unknown
                'exchange_mapped': 'NASDAQ',  # Default exchange
                'tradingview_exists': False  # If Polygon API fails, likely doesn't exist on TradingView either
            }

            with self._lock:
                self.cache_data[ticker_upper] = cache_entry

            # Save cache after adding fallback entry
            self._save_cache()

            return cache_entry

    def _determine_if_stock(self, cache_entry):
        """Determine if ticker is a stock based on cached data"""
        ticker_type = cache_entry.get('type', '').upper()
        name = cache_entry.get('name', '').upper()

        # Check type first
        if ticker_type in ['ETF', 'ETN', 'FUND', 'REIT', 'TRUST', 'INDEX', 'MUTUAL_FUND']:
            return False

        # Check name for fund/ETF indicators
        if any(indicator in name for indicator in ['ETF', 'ETN', 'FUND', 'TRUST', 'INDEX', 'REIT']):
            return False

        # Default to stock if no clear indicators
        return True

    def _map_exchange(self, primary_exchange):
        """Map exchange code to common name"""
        exchange_mapping = {
            'XNYS': 'NYSE',     # NYSE
            'XNAS': 'NASDAQ',   # NASDAQ
            'XASE': 'NYSE',     # NYSE American (formerly AMEX)
            'ARCX': 'NYSE',     # NYSE Arca
            'AMEX': 'NYSE',     # AMEX (legacy name)
            'BATS': 'BATS',     # BATS Exchange
            'EDGX': 'EDGX',     # EDGX Exchange
            'EDGA': 'EDGA',     # EDGA Exchange
            'IEX': 'IEX',       # IEX Exchange
            'NYSE': 'NYSE',     # Direct NYSE
            'NASDAQ': 'NASDAQ', # Direct NASDAQ
            'NYSEAMERICAN': 'NYSE',  # NYSE American full name
        }

        return exchange_mapping.get(primary_exchange, primary_exchange or 'NASDAQ')

    def is_stock_instrument(self, ticker):
        """Fast stock/ETF determination using cache"""
        details = self.get_ticker_details(ticker)
        return details.get('is_stock', True)

    def is_tradingview_available(self, ticker):
        """Check if ticker is available on TradingView"""
        details = self.get_ticker_details(ticker)
        return details.get('tradingview_exists', True)

    def is_valid_stock_for_trading(self, ticker):
        """Check if ticker is both a stock AND available on TradingView"""
        details = self.get_ticker_details(ticker)
        return (details.get('is_stock', True) and
                details.get('tradingview_exists', True))

    def get_exchange(self, ticker):
        """Fast exchange lookup using cache"""
        details = self.get_ticker_details(ticker)
        return details.get('exchange_mapped', 'NASDAQ')

    def bulk_populate_cache(self, tickers, max_workers=8, save_every=100):
        """Populate cache for multiple tickers in parallel"""
        print(f"Bulk populating cache for {len(tickers)} tickers...")

        # Filter out already cached tickers
        uncached_tickers = []
        for ticker in tickers:
            ticker_upper = ticker.upper()
            if ticker_upper not in self.cache_data:
                uncached_tickers.append(ticker)

        print(f"Need to fetch {len(uncached_tickers)} new tickers")

        if not uncached_tickers:
            print("All tickers already cached!")
            return

        # Process in parallel with rate limiting
        processed = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all futures
            futures = {executor.submit(self.get_ticker_details, ticker): ticker
                      for ticker in uncached_tickers}

            for future in as_completed(futures):
                ticker = futures[future]
                try:
                    future.result()  # Process the result
                    processed += 1

                    if processed % 50 == 0:
                        print(f"Processed {processed}/{len(uncached_tickers)} tickers...")

                    # Save cache periodically
                    if processed % save_every == 0:
                        self._save_cache()

                    # Rate limiting - small delay to avoid overwhelming API
                    time.sleep(0.1)

                except Exception as e:
                    print(f"Error processing {ticker}: {e}")

        # Final save
        self._save_cache()
        print(f"Bulk cache population completed: {processed} tickers processed")

    def get_cache_stats(self):
        """Get cache statistics"""
        total_entries = len(self.cache_data)
        stocks = sum(1 for entry in self.cache_data.values() if entry.get('is_stock', True))
        non_stocks = total_entries - stocks

        # Count by exchange
        exchanges = {}
        for entry in self.cache_data.values():
            exchange = entry.get('exchange_mapped', 'UNKNOWN')
            exchanges[exchange] = exchanges.get(exchange, 0) + 1

        return {
            'total_entries': total_entries,
            'stocks': stocks,
            'non_stocks': non_stocks,
            'exchanges': exchanges
        }

    def print_cache_stats(self):
        """Print cache statistics"""
        stats = self.get_cache_stats()
        print(f"\n=== TICKER CACHE STATISTICS ===")
        print(f"Total cached tickers: {stats['total_entries']}")
        print(f"Stocks: {stats['stocks']}")
        print(f"Non-stocks (ETFs/funds): {stats['non_stocks']}")
        print(f"Exchanges:")
        for exchange, count in sorted(stats['exchanges'].items()):
            print(f"  {exchange}: {count}")