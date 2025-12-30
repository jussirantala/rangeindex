#!/usr/bin/env python3
"""
Cache Population Utility

Run this once to pre-populate the ticker cache for massive speedup.
After running this, all subsequent analysis will be much faster.
"""

import os
import time
from polygon import RESTClient
from config import Config
from ticker_manager import TickerManager
from ticker_cache import TickerCache


def main():
    """Populate ticker cache for maximum speed"""
    print("=== TICKER CACHE POPULATION UTILITY ===")
    print("This will pre-populate the ticker cache for massive speedup.")
    print("Run this once, then all subsequent analysis will be much faster.\n")

    # Initialize configuration
    config = Config()
    print(f"Configuration loaded - will cache up to {config.ticker_limit} tickers")

    # Initialize Polygon client
    client = RESTClient(config.api_key)

    # Fetch tickers
    print("\n=== FETCHING TICKER LIST ===")
    ticker_cache_dir = os.path.join(config.data_dir, "ticker_cache")
    ticker_manager = TickerManager(client, cache_dir=ticker_cache_dir)
    all_tickers = ticker_manager.fetch_all_tickers()
    tickers = all_tickers[:config.ticker_limit]
    print(f"Fetched {len(tickers)} tickers for caching")

    # Initialize ticker cache
    print("\n=== INITIALIZING CACHE ===")
    ticker_cache_dir = os.path.join(config.data_dir, "ticker_cache")
    ticker_cache = TickerCache(client, cache_dir=ticker_cache_dir)

    # Show current cache stats
    ticker_cache.print_cache_stats()

    # Bulk populate cache
    print(f"\n=== POPULATING CACHE FOR {len(tickers)} TICKERS ===")
    print("This may take some time depending on how many new tickers need to be cached...")
    print("Progress will be shown every 50 tickers.")

    start_time = time.time()
    ticker_cache.bulk_populate_cache(tickers, max_workers=4, save_every=100)
    end_time = time.time()

    # Show final stats
    print(f"\n=== CACHE POPULATION COMPLETED ===")
    print(f"Total time: {end_time - start_time:.1f} seconds")
    ticker_cache.print_cache_stats()

    print(f"\n=== READY FOR HIGH-SPEED ANALYSIS ===")
    print("Cache is now populated! Run your main analysis for maximum speed.")
    print("The system will now use cached data instead of making API calls.")


if __name__ == "__main__":
    main()