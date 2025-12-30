import json
import os
from datetime import datetime, timedelta


class TickerManager:
    def __init__(self, client, cache_dir="ticker_cache"):
        self.client = client
        # Store ticker list cache in ticker_cache directory
        os.makedirs(cache_dir, exist_ok=True)
        self.cache_file = os.path.join(cache_dir, "tickers_cache.json")
        self.one_week_ago = datetime.now() - timedelta(weeks=1)

    def load_ticker_cache(self):
        """Load ticker cache from JSON file"""
        try:
            with open(self.cache_file, 'r') as f:
                cache = json.load(f)
            cache_time = datetime.fromisoformat(cache['timestamp'])
            return cache['tickers'], cache_time
        except (FileNotFoundError, KeyError, ValueError):
            return None, None

    def save_ticker_cache(self, tickers):
        """Save ticker cache to JSON file"""
        cache = {
            'timestamp': datetime.now().isoformat(),
            'tickers': tickers
        }
        with open(self.cache_file, 'w') as f:
            json.dump(cache, f, indent=2)

    def fetch_all_tickers(self):
        """Fetch all tickers with caching"""
        cached_tickers, cache_time = self.load_ticker_cache()

        if cached_tickers and cache_time and cache_time > self.one_week_ago:
            print(f"Using cached tickers from {cache_time.strftime('%Y-%m-%d %H:%M:%S')} ({len(cached_tickers)} tickers)")
            return cached_tickers

        print("Fetching all tickers from Polygon API...")
        all_tickers = []
        page = 1

        while page <= 100:  # Safety limit
            print(f"Fetching page {page}...")
            response = self.client.list_tickers(market="stocks", active=True, limit=1000)
            page_tickers = [ticker.ticker for ticker in response if ticker.ticker.isalpha() and len(ticker.ticker) <= 4]
            all_tickers.extend(page_tickers)

            if not hasattr(response, 'next_url') or not response.next_url:
                break
            page += 1

        print(f"Fetched {len(all_tickers)} tickers total")
        self.save_ticker_cache(all_tickers)
        print(f"Saved ticker cache to {self.cache_file}")
        return all_tickers

    def refresh_ticker_cache(self):
        """Force refresh ticker cache from API"""
        print("Force refreshing ticker list from Polygon API...")
        all_tickers = []
        page = 1

        while page <= 100:  # Safety limit
            print(f"Fetching page {page}...")
            response = self.client.list_tickers(market="stocks", active=True, limit=1000)
            page_tickers = [ticker.ticker for ticker in response if ticker.ticker.isalpha() and len(ticker.ticker) <= 4]
            all_tickers.extend(page_tickers)

            if not hasattr(response, 'next_url') or not response.next_url:
                break
            page += 1

        print(f"Refreshed {len(all_tickers)} tickers total")
        self.save_ticker_cache(all_tickers)
        print(f"Updated ticker cache at {self.cache_file}")
        return all_tickers