#!/usr/bin/env python3
"""
Range Index - Modular Version

A sine wave-based stock index optimization tool that:
1. Fetches stock data from Polygon API
2. Fits sine waves to price movements
3. Clusters stocks by phase alignment
4. Optimizes portfolio weights
5. Generates TradingView-compatible outputs
"""

import warnings
import pandas as pd
import numpy as np
import time
import os
from polygon import RESTClient

from config import Config
from ticker_manager import TickerManager
from data_manager import DataManager
from range_finder_optimized import RangeFinderOptimized
from output_formatter import OutputFormatter

warnings.filterwarnings('ignore')


def main():
    """Main application entry point"""
    # Initialize configuration
    config = Config()
    print(f"Initialized configuration with {config.ticker_limit} tickers")

    # Initialize Polygon client
    client = RESTClient(config.api_key)

    # Fetch tickers
    print("\n=== FETCHING TICKERS ===")
    ticker_cache_dir = os.path.join(config.data_dir, "ticker_cache")
    ticker_manager = TickerManager(client, cache_dir=ticker_cache_dir)
    all_tickers = ticker_manager.fetch_all_tickers()
    tickers = all_tickers[:config.ticker_limit]
    print(f"Using first {config.ticker_limit} tickers: {len(tickers)} stocks")

    # Initialize data manager and range finder
    data_manager = DataManager(client, config)
    range_finder = RangeFinderOptimized(
        candle_interval=config.candle_interval,
        candle_unit=config.candle_unit,
        timespan_days=config.timespan_days
    )

    # Show cache status for performance optimization info
    print("\n=== CACHE STATUS ===")
    data_manager.ticker_cache.print_cache_stats()
    cache_stats = data_manager.ticker_cache.get_cache_stats()
    if cache_stats['total_entries'] < 1000:
        print("\n⚡ PERFORMANCE TIP: Run 'python populate_cache.py' once for massive speedup!")
        print("   This will pre-cache ticker data and eliminate API bottlenecks.")

    # Progressive data loading and analysis
    print("\n=== PROGRESSIVE LOADING & ANALYSIS ===")
    ranging_scores = {}
    batch_size = 1000  # Even larger batches for maximum efficiency
    # Calculate max_batches to process ALL available tickers
    max_batches = (len(tickers) + batch_size - 1) // batch_size  # Ceiling division
    print(f"Will process ALL {len(tickers)} stocks in {max_batches} batches of {batch_size}")

    for batch_num in range(max_batches):
        start_idx = batch_num * batch_size
        end_idx = min(start_idx + batch_size, len(tickers))

        if start_idx >= len(tickers):
            break

        current_batch = tickers[start_idx:end_idx]
        progress_pct = ((batch_num + 1) / max_batches) * 100
        print(f"\n=== BATCH {batch_num + 1}/{max_batches} ({progress_pct:.1f}%): Processing stocks {start_idx+1}-{end_idx} ===")

        # Filter out ETFs, funds, and other non-stock instruments + wrong exchanges
        filter_start = time.time()

        # Get accepted exchanges from environment
        accepted_exchanges = os.getenv("ACCEPTED_EXCHANGES", "NASDAQ,NYSE").split(",")
        accepted_exchanges = [ex.strip().upper() for ex in accepted_exchanges]

        # Apply both filters: stock instrument AND accepted exchange
        filtered_batch = []
        instrument_filtered = 0
        exchange_filtered = 0

        for ticker in current_batch:
            # First check if it's a valid stock for trading (includes TradingView validation)
            if not data_manager.is_valid_for_trading(ticker):
                instrument_filtered += 1
                continue

            # Then check if it's on an accepted exchange
            exchange = data_manager.ticker_cache.get_exchange(ticker)
            if exchange.upper() not in accepted_exchanges:
                exchange_filtered += 1
                continue

            # Passed both filters
            filtered_batch.append(ticker)

        filter_time = time.time() - filter_start

        # Report filtering results
        total_filtered = len(current_batch) - len(filtered_batch)
        if total_filtered > 0:
            print(f"Filtered out {total_filtered} stocks in {filter_time:.1f}s:")
            if instrument_filtered > 0:
                print(f"  - {instrument_filtered} non-stock instruments or TradingView unavailable")
            if exchange_filtered > 0:
                print(f"  - {exchange_filtered} wrong exchanges (not in {', '.join(accepted_exchanges)})")

        stock_only_batch = filtered_batch

        # Load this batch (stocks only)
        load_start = time.time()
        batch_data = data_manager._load_ticker_batch_fast(stock_only_batch)
        load_time = time.time() - load_start
        if not batch_data:
            print("No usable data in this batch, continuing...")
            continue

        # For range analysis, we don't need aligned timestamps - analyze each stock separately
        # Convert to DataFrame but preserve individual stock data
        if not batch_data:
            print("No valid stocks in this batch, continuing...")
            continue

        print(f"Loaded {len(batch_data)} stocks in {load_time:.1f}s - analyzing for ranging behavior...")

        # Find ranging stocks in this batch using the raw data dict
        analysis_start = time.time()
        batch_ranging_scores = range_finder.find_ranging_stocks(batch_data, target_min=1, target_max=config.target_max_stocks)
        analysis_time = time.time() - analysis_start

        # Merge with existing results
        ranging_scores.update(batch_ranging_scores)

        # Continue processing to find the best possible stocks
        print(f"Analysis completed in {analysis_time:.1f}s - found {len(batch_ranging_scores)} ranging stocks")
        print(f"Current total: {len(ranging_scores)} ranging stocks found so far")

        # No early termination - process ALL stocks to find the absolute best

    if len(ranging_scores) == 0:
        print(f"\nNo ranging stocks found after analyzing ALL {len(tickers)} stocks")
        return

    print(f"\nFinal result: {len(ranging_scores)} ranging stocks found from ALL {len(tickers)} stocks analyzed")

    # Select the absolute best stocks from all analyzed
    if len(ranging_scores) > 10:  # If we have many candidates, be more selective
        top_candidates = dict(sorted(ranging_scores.items(), key=lambda x: x[1], reverse=True)[:10])
        print(f"Selected top 10 candidates from {len(ranging_scores)} qualifying stocks")
        ranging_scores = top_candidates

    # Load data for the selected ranging stocks for portfolio optimization
    print("\n=== LOADING DATA FOR SELECTED STOCKS ===")
    selected_tickers = list(ranging_scores.keys())
    selected_data = data_manager._load_ticker_batch_fast(selected_tickers)

    # For portfolio optimization, we do need aligned timestamps, but let's be more careful
    # Create DataFrame but handle the alignment more gracefully
    if selected_data:
        # Use TradingView-style alignment: intersection of timestamps (only times where ALL tickers have data)
        # This matches how TradingView math tickers work
        common_timestamps = None
        for ticker, ticker_data in selected_data.items():
            valid_timestamps = set(ticker_data.dropna().index)
            if common_timestamps is None:
                common_timestamps = valid_timestamps
            else:
                common_timestamps = common_timestamps.intersection(valid_timestamps)

        common_timestamps = sorted(common_timestamps)
        print(f"Using TradingView-style alignment: {len(common_timestamps)} common timestamps")

        # Reindex all series to the common timestamps - should have no gaps
        aligned_data = {}
        for ticker, data in selected_data.items():
            aligned_data[ticker] = data.reindex(common_timestamps)

        # Create aligned DataFrame - should have no missing values
        prices_with_gaps = pd.DataFrame(aligned_data, dtype='float32')
        prices = prices_with_gaps  # No need to dropna with intersection alignment
        print(f"Loaded optimization data for {len(prices.columns)} ranging stocks ({len(prices)} time points)")
    else:
        prices = pd.DataFrame()
        prices_with_gaps = pd.DataFrame()
        print("No data loaded for selected stocks")

    print("\n=== OPTIMIZING RANGING PORTFOLIO ===")
    opt_weights = range_finder.optimize_ranging_portfolio(prices, ranging_scores)

    # Check if portfolio has more short than long positions and auto-invert if needed
    long_positions = [w for w in opt_weights.values() if w > 0]
    short_positions = [w for w in opt_weights.values() if w < 0]
    auto_inverted = False

    if len(short_positions) > len(long_positions):
        print(f"\n=== AUTO-INVERTING INDEX ===")
        print(f"Portfolio has {len(short_positions)} short positions vs {len(long_positions)} long positions")
        print(f"Auto-inverting to make it predominantly long...")

        # Invert all weights
        opt_weights = {ticker: -weight for ticker, weight in opt_weights.items()}
        auto_inverted = True

        # Recalculate position counts after inversion
        long_positions_after = [w for w in opt_weights.values() if w > 0]
        short_positions_after = [w for w in opt_weights.values() if w < 0]
        print(f"After inversion: {len(long_positions_after)} long positions vs {len(short_positions_after)} short positions")

    # Display results before chart
    print("\n=== RESULTS ===")
    print("\n**FINAL RANGING INDEX WEIGHTS**:")

    # Show all weights, sorted by absolute value
    sorted_weights = sorted(opt_weights.items(), key=lambda x: abs(x[1]), reverse=True)

    print("\n** LONG POSITIONS (Buy) **:")
    long_positions = [(k, v) for k, v in sorted_weights if v > 0]
    for tkr, w in long_positions:
        print(f"{tkr}: +{w:.1%}")

    print("\n** SHORT POSITIONS (Sell/Short) **:")
    short_positions = [(k, v) for k, v in sorted_weights if v < 0]
    for tkr, w in short_positions:
        print(f"{tkr}: {w:.1%}")

    # Summary
    total_long = sum(w for _, w in long_positions)
    total_short = sum(w for _, w in short_positions)
    print(f"\nSUMMARY:")
    print(f"Total Long Exposure: {total_long:.1%}")
    print(f"Total Short Exposure: {total_short:.1%}")
    print(f"Net Exposure: {total_long + total_short:.1%}")
    print(f"Gross Exposure: {total_long - total_short:.1%}")
    if auto_inverted:
        print(f"INDEX AUTOMATICALLY INVERTED: Portfolio was predominantly short, inverted to be long-biased")

    # Calculate portfolio and ranging metrics
    if opt_weights:
        portfolio = (prices[list(opt_weights.keys())] * pd.Series(opt_weights)).sum(axis=1)
        portfolio_ranging_score = range_finder.calculate_ranging_score(portfolio)

        # Calculate some ranging statistics
        returns = portfolio.pct_change().dropna()
        volatility = returns.std() * np.sqrt(252)  # Annualized
        max_drawdown = ((portfolio / portfolio.cummax()) - 1).min()

        print(f"\nPortfolio Ranging Score: {portfolio_ranging_score:.3f}")
        print(f"Portfolio Volatility: {volatility:.1%}")
        print(f"Maximum Drawdown: {max_drawdown:.1%}")
    else:
        print("No suitable ranging portfolio found!")

    # Generate TradingView outputs
    print("\n=== TRADINGVIEW OUTPUTS ===")
    if auto_inverted:
        print("NOTE: Index was automatically inverted to be predominantly long")
    output_formatter = OutputFormatter(config, client)
    output_formatter.format_tradingview_outputs(opt_weights)

    # Create chart visualization
    if config.show_charts:
        print("\n=== GENERATING CHARTS ===")
        try:
            from chart_visualizer_financial import RangeIndexFinancialVisualizer

            print("Loading OHLC data for TradingView-style charts...")
            # Load OHLC data for selected stocks
            ohlc_data = {}
            for ticker in selected_tickers:
                try:
                    ticker_ohlc = data_manager.load_candle_data_ohlc(ticker, config.start_date, config.end_date, config.interval)
                    if ticker_ohlc is not None and len(ticker_ohlc) > 0:
                        ohlc_data[ticker] = ticker_ohlc
                except Exception:
                    pass  # Skip failed tickers

            print(f"Loaded OHLC data for {len(ohlc_data)} stocks")

            # Calculate portfolio statistics for charting
            returns = prices.pct_change().dropna()
            portfolio_returns = pd.Series(0, index=returns.index)

            for ticker, weight in opt_weights.items():
                if ticker in returns.columns:
                    portfolio_returns += returns[ticker] * weight

            portfolio_stats = {
                'ranging_score': sum(ranging_scores[ticker] * abs(opt_weights.get(ticker, 0))
                                   for ticker in ranging_scores.keys() if ticker in opt_weights) / sum(abs(w) for w in opt_weights.values()),
                'volatility': portfolio_returns.std() * (252 * 96) ** 0.5,  # Annualized volatility for 15-min data
                'max_drawdown': ((portfolio_returns.cumsum().cummax() - portfolio_returns.cumsum()) / (portfolio_returns.cumsum().cummax() + 1)).max()
            }

            # Create TradingView-style financial charts
            visualizer = RangeIndexFinancialVisualizer(use_plotly=True, dark_theme=True)
            chart_success = visualizer.create_index_chart(prices_with_gaps, opt_weights, ranging_scores, portfolio_stats, ohlc_data)

            if chart_success:
                print("TradingView-style financial chart displayed successfully!")
            else:
                print("Chart generation failed - continuing without visualization")

        except ImportError:
            print("Chart dependencies not available - install matplotlib, mplfinance, plotly and seaborn to enable charts")
        except Exception as e:
            print(f"Chart generation error: {e}")
            print("Continuing without visualization")
    else:
        print("\nChart display disabled (SHOW_CHARTS=false)")

    # Ask if user wants to generate TWS basket file
    print("\n=== TWS BASKET GENERATION ===")
    if opt_weights:
        try:
            generate_basket = input("Generate Interactive Brokers TWS basket file? (y/n): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            generate_basket = 'n'
            print("Skipping TWS basket generation...")

        if generate_basket in ['y', 'yes']:
            try:
                from tws_basket_converter import convert_portfolio_weights

                print(f"\nGenerating TWS basket...")

                # Let convert_portfolio_weights generate the filename with correct path
                result = convert_portfolio_weights(opt_weights, "")
                if result:
                    print(f"TWS basket created: {result}")
                    print("Import this file into TWS Basket Trader to execute trades")
                else:
                    print("ERROR: Failed to create TWS basket file")

            except ImportError:
                print("ERROR: TWS converter not available - check tws_basket_converter.py")
            except Exception as e:
                print(f"ERROR: Error generating TWS basket: {e}")


if __name__ == "__main__":
    main()