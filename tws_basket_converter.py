#!/usr/bin/env python3
"""
TWS Basket Converter

Converts TradingView ticker format to Interactive Brokers TWS basket CSV format.
Supports both manual conversion and automatic generation from portfolio optimization.
"""

import os
import csv
import re
from datetime import datetime
from config import Config


def parse_tradingview_ticker(ticker_string):
    """Parse TradingView ticker format into individual positions"""
    positions = []

    # Get accepted exchanges from environment
    accepted_exchanges = os.getenv("ACCEPTED_EXCHANGES", "NASDAQ,NYSE").split(",")
    accepted_exchanges = [ex.strip().upper() for ex in accepted_exchanges]

    # Split by + and - while preserving the signs
    # Use regex to find all patterns like EXCHANGE:SYMBOL*weight or EXCHANGE:SYMBOL*-weight
    pattern = r'([+-]?)([A-Z]+):([A-Z]+)\*(-?[0-9]+\.?[0-9]*)'
    matches = re.findall(pattern, ticker_string)

    filtered_count = 0
    for sign, exchange, symbol, weight in matches:
        # Filter out weird exchanges
        if exchange.upper() not in accepted_exchanges:
            print(f"WARNING: Filtered out {symbol} from {exchange} (not in accepted exchanges: {', '.join(accepted_exchanges)})")
            filtered_count += 1
            continue

        # Determine action based on both sign prefix and weight sign
        weight_value = float(weight)

        # Apply the leading sign to the weight
        if sign == "-":
            weight_value = -weight_value

        # Determine action (BUY for positive, SELL for negative weights)
        action = "SELL" if weight_value < 0 else "BUY"

        # Store the raw weight for ratio calculation (use absolute value)
        positions.append({
            'action': action,
            'symbol': symbol,
            'quantity': 0,  # Will be calculated after all weights are collected
            'exchange': exchange,
            'weight': abs(weight_value)  # Store absolute value for calculations
        })

    # Note: quantities will be calculated later based on investment amount and current prices

    if filtered_count > 0:
        print(f"Filtered out {filtered_count} positions from non-accepted exchanges")

    return positions


def get_current_prices(symbols, client):
    """Get current prices for symbols using Polygon API with fallbacks"""
    prices = {}
    for symbol in symbols:
        try:
            # Try to get last quote from Polygon API
            quote = client.get_last_quote(symbol)
            # Use bid-ask midpoint as current price
            if hasattr(quote, 'bid') and hasattr(quote, 'ask'):
                current_price = (quote.bid + quote.ask) / 2
            elif hasattr(quote, 'price'):
                current_price = quote.price
            else:
                raise Exception("No price data in quote response")

            prices[symbol] = round(current_price, 2)
            print(f"{symbol}: ${current_price:.2f}")

        except Exception as e:
            # If real-time quotes fail, try to get recent daily close price
            try:
                from datetime import datetime, timedelta
                # Get yesterday's close price as fallback
                yesterday = datetime.now() - timedelta(days=1)
                aggs = client.get_aggs(symbol, 1, "day", yesterday.strftime('%Y-%m-%d'), yesterday.strftime('%Y-%m-%d'))

                if aggs and len(aggs) > 0:
                    current_price = aggs[0].close
                    prices[symbol] = round(current_price, 2)
                    print(f"{symbol}: ${current_price:.2f} (using recent close)")
                else:
                    raise Exception("No recent price data available")

            except Exception as e2:
                # Ultimate fallback to estimated prices (updated Nov 2024)
                price_estimates = {
                    'AAPL': 230.0, 'MSFT': 420.0, 'GOOGL': 175.0, 'TSLA': 350.0,
                    'AHCO': 30.0, 'NHTC': 12.0, 'SABR': 200.0, 'HWBK': 75.0,
                    'BPRN': 54.0, 'NVT': 54.0, 'UBFO': 33.0, 'MCHX': 57.0,
                    'GAIN': 24.0, 'DIT': 27.0
                }
                fallback_price = price_estimates.get(symbol, 10.0)
                prices[symbol] = fallback_price
                print(f"{symbol}: ${fallback_price:.2f} (estimated - real-time data unavailable)")

    return prices


def convert_to_tws_basket(ticker_string, account_id="", output_file=None, total_investment=None):
    """Convert TradingView ticker to TWS basket CSV format"""

    positions = parse_tradingview_ticker(ticker_string)

    if not positions:
        print("No valid positions found in ticker string")
        return None

    # Ask for total investment amount if not provided
    if total_investment is None:
        try:
            total_investment = float(input("\nEnter total investment amount (USD): $"))
            if total_investment <= 0:
                print("Investment amount must be positive")
                return None
        except ValueError:
            print("Invalid investment amount")
            return None

    print(f"\nCalculating position sizes for ${total_investment:,.2f} total investment...")

    # Get current prices from Polygon API
    from polygon import RESTClient
    from config import Config

    config = Config()
    client = RESTClient(config.api_key)

    symbols = [pos['symbol'] for pos in positions]
    print(f"\nFetching current prices for {len(symbols)} stocks...")
    current_prices = get_current_prices(symbols, client)

    # Calculate position sizes based on weights and total investment
    for pos in positions:
        symbol = pos['symbol']
        weight = pos['weight']
        price = current_prices[symbol]

        # Calculate dollar amount for this position
        position_value = abs(weight) * total_investment

        # Calculate fractional shares (up to 2 decimals)
        shares = position_value / price
        pos['quantity'] = round(shares, 2)  # IBKR supports up to 2 decimal places

        print(f"{symbol}: {weight:.1%} = ${position_value:,.2f} ÷ ${price:.2f} = {pos['quantity']} shares")

    # Generate filename if not provided
    if output_file is None:
        symbols = [pos['symbol'] for pos in positions]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Create baskets directory if it doesn't exist
        baskets_dir = "baskets"
        os.makedirs(baskets_dir, exist_ok=True)
        output_file = os.path.join(baskets_dir, f"basket_{'_'.join(symbols)}_{timestamp}.csv")

    # Create CSV content
    csv_data = []

    # Header row (based on sample format)
    header = [
        'Action', 'Quantity', 'Symbol', 'SecType', 'Exchange', 'Currency',
        'TimeInForce', 'OrderType', 'BasketTag', 'Account', 'OrderRef'
    ]
    csv_data.append(header)

    # Add position rows
    for pos in positions:
        row = [
            pos['action'],                 # Action (BUY/SELL)
            pos['quantity'],               # Quantity
            pos['symbol'],                 # Symbol
            'STK',                         # SecType (Stock)
            'SMART/AMEX',                  # Exchange (Smart routing)
            'USD',                         # Currency
            'GTC',                         # TimeInForce (Good Till Cancelled)
            'MKT',                         # OrderType (Market order)
            'Basket',                      # BasketTag
            account_id,                    # Account
            'Basket'                       # OrderRef
        ]
        csv_data.append(row)

    # Write CSV file
    try:
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerows(csv_data)

        print(f"\nTWS Basket CSV created: {output_file}")
        print(f"Positions: {len(positions)} stocks")
        print(f"Account: {account_id}")

        # Show position summary
        print(f"\nPosition Summary:")
        long_positions = [p for p in positions if p['action'] == 'BUY']
        short_positions = [p for p in positions if p['action'] == 'SELL']

        if long_positions:
            print(f"  LONG ({len(long_positions)}): {', '.join([p['symbol'] for p in long_positions])}")
        if short_positions:
            print(f"  SHORT ({len(short_positions)}): {', '.join([p['symbol'] for p in short_positions])}")

        return output_file

    except Exception as e:
        print(f"ERROR: Error creating CSV file: {e}")
        return None


def convert_portfolio_weights(portfolio_weights, account_id="", output_file=None, total_investment=None):
    """Convert portfolio weights dictionary to TWS basket CSV"""
    if not portfolio_weights:
        print("No portfolio weights provided")
        return None

    # Initialize ticker cache for exchange detection
    from polygon import RESTClient
    from config import Config
    from ticker_cache import TickerCache

    config = Config()
    client = RESTClient(config.api_key)
    ticker_cache = TickerCache(client)

    # Build TradingView-style ticker string from portfolio weights
    ticker_parts = []
    for symbol, weight in portfolio_weights.items():
        # Get actual exchange from ticker cache
        exchange = ticker_cache.get_exchange(symbol)

        if weight >= 0:
            ticker_parts.append(f"{exchange}:{symbol}*{abs(weight):.3f}")
        else:
            ticker_parts.append(f"-{exchange}:{symbol}*{abs(weight):.3f}")

    ticker_string = "+".join(ticker_parts).replace("+-", "-")

    # Generate filename from symbols
    if output_file is None:
        symbols = list(portfolio_weights.keys())
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Create baskets directory if it doesn't exist
        baskets_dir = "baskets"
        os.makedirs(baskets_dir, exist_ok=True)
        output_file = os.path.join(baskets_dir, f"basket_{'_'.join(symbols)}_{timestamp}.csv")

    print(f"\nConverting portfolio to TWS basket...")
    print(f"TradingView format: {ticker_string}")

    return convert_to_tws_basket(ticker_string, account_id, output_file, total_investment)


def main():
    """Main function for manual conversion"""
    print("=== TWS Basket Converter ===")

    # Load configuration for account ID
    config = Config()
    account_id = ""  # Leave empty for user to fill in TWS

    print("Account field will be left empty for you to fill in TWS")

    # Get TradingView ticker string from user
    print("\nEnter TradingView ticker string:")
    print("Example: NASDAQ:AHCO*0.317+NASDAQ:NHTC*0.313-NYSE:NVT*0.223")

    ticker_string = input("Ticker: ").strip()

    if not ticker_string:
        print("No ticker string provided")
        return

    # Convert to TWS basket
    output_file = convert_to_tws_basket(ticker_string, account_id)

    if output_file:
        print(f"\nConversion completed successfully!")
        print(f"File saved: {output_file}")
        print(f"\nNext steps:")
        print(f"1. Open Interactive Brokers TWS")
        print(f"2. Go to Trade → Basket Trader")
        print(f"3. Import the CSV file: {output_file}")
        print(f"4. Review and submit orders")


if __name__ == "__main__":
    main()