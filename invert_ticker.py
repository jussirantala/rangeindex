#!/usr/bin/env python3
"""
TradingView Ticker Inverter

Inverts a TradingView math ticker by flipping all position signs:
- Long positions (BUY) become short positions (SELL)
- Short positions (SELL) become long positions (BUY)

This is useful for creating inverse/contrarian indices or hedging strategies.

Examples:
    # Interactive mode
    python invert_ticker.py

    # Command line mode
    python invert_ticker.py "NASDAQ:AAPL*0.4+NYSE:MSFT*0.3-NASDAQ:TSLA*0.2"

    # Function usage
    from invert_ticker import invert_tradingview_ticker
    inverted = invert_tradingview_ticker("NASDAQ:AAPL*0.5-NASDAQ:TSLA*0.5")
    # Result: "NASDAQ:AAPL*-0.5+NASDAQ:TSLA*0.5"
"""

import re
import sys


def invert_tradingview_ticker(ticker_string):
    """
    Invert a TradingView ticker string by flipping all signs

    Args:
        ticker_string (str): TradingView ticker format like "NASDAQ:AAPL*0.4+NYSE:MSFT*0.3-NASDAQ:TSLA*0.2"

    Returns:
        str: Inverted ticker string with all signs flipped
    """
    if not ticker_string.strip():
        return ""

    # Split by + and - while preserving the signs using regex
    # Pattern matches: optional sign, exchange, symbol, weight
    pattern = r'([+-]?)([A-Z]+):([A-Z]+)\*([0-9]+\.?[0-9]*)'
    matches = re.findall(pattern, ticker_string)

    if not matches:
        print("ERROR: No valid ticker format found")
        return ""

    inverted_parts = []

    for sign, exchange, symbol, weight in matches:
        # Flip the sign and apply it to the weight multiplier
        if sign == "-":
            # Short becomes long (positive weight)
            inverted_parts.append(f"{exchange}:{symbol}*{weight}")
        else:
            # Long becomes short (negative weight)
            inverted_parts.append(f"{exchange}:{symbol}*-{weight}")

    # Join parts with + separator
    inverted_ticker = "+".join(inverted_parts)

    # Remove leading + if present
    if inverted_ticker.startswith("+"):
        inverted_ticker = inverted_ticker[1:]

    return inverted_ticker


def analyze_inversion(original, inverted):
    """Analyze and display the inversion results"""
    print(f"\n=== TICKER INVERSION ANALYSIS ===")
    print(f"Original: {original}")
    print(f"Inverted: {inverted}")

    # Parse both to show the changes
    # Updated pattern to handle negative weights: EXCHANGE:SYMBOL*-weight
    original_pattern = r'([+-]?)([A-Z]+):([A-Z]+)\*([0-9]+\.?[0-9]*)'
    inverted_pattern = r'([+-]?)([A-Z]+):([A-Z]+)\*(-?[0-9]+\.?[0-9]*)'

    original_matches = re.findall(original_pattern, original)
    inverted_matches = re.findall(inverted_pattern, inverted)

    print(f"\n=== POSITION CHANGES ===")
    for i, ((orig_sign, exchange, symbol, weight), (inv_sign, _, _, inv_weight)) in enumerate(zip(original_matches, inverted_matches)):
        orig_action = "SHORT" if orig_sign == "-" else "LONG"
        # For inverted, check if weight is negative
        inv_action = "SHORT" if inv_weight.startswith("-") else "LONG"

        print(f"{symbol}: {orig_action} -> {inv_action} ({weight}% weight)")

    print(f"\n=== SUMMARY ===")
    orig_longs = sum(1 for sign, _, _, _ in original_matches if sign != "-")
    orig_shorts = len(original_matches) - orig_longs

    # Count inverted positions based on weight sign
    inv_longs = sum(1 for _, _, _, weight in inverted_matches if not weight.startswith("-"))
    inv_shorts = sum(1 for _, _, _, weight in inverted_matches if weight.startswith("-"))

    print(f"Original: {orig_longs} long, {orig_shorts} short")
    print(f"Inverted: {inv_longs} long, {inv_shorts} short")


def main():
    """Main function for interactive ticker inversion"""
    print("=== TradingView Ticker Inverter ===")
    print("Flips all position signs to create inverse/contrarian indices")

    # Get ticker string from command line or user input
    if len(sys.argv) > 1:
        ticker_string = sys.argv[1]
        print(f"\nUsing ticker from command line:")
        interactive_mode = False
    else:
        print(f"\nEnter TradingView ticker string to invert:")
        print("Example: NASDAQ:AAPL*0.4+NYSE:MSFT*0.3-NASDAQ:TSLA*0.2")
        ticker_string = input("Ticker: ").strip()
        interactive_mode = True

    if not ticker_string:
        print("No ticker string provided")
        return

    # Perform the inversion
    inverted_ticker = invert_tradingview_ticker(ticker_string)

    if not inverted_ticker:
        print("Failed to invert ticker")
        return

    # Show analysis
    analyze_inversion(ticker_string, inverted_ticker)

    # Ask if user wants to generate TWS basket (only in interactive mode)
    if interactive_mode:
        print(f"\n=== TWS BASKET GENERATION ===")
        generate_basket = input("Generate TWS basket for inverted ticker? (y/n): ").strip().lower()
    else:
        generate_basket = "n"  # Default to no in non-interactive mode

    if generate_basket in ['y', 'yes']:
        try:
            from tws_basket_converter import convert_to_tws_basket
            import os

            account_id = os.getenv("IBKR_ACCOUNT", "U16418165")
            print(f"\nGenerating TWS basket for account: {account_id}")

            # Let convert_to_tws_basket generate the filename with correct path
            result = convert_to_tws_basket(inverted_ticker, account_id)

            if result:
                print(f"Inverted TWS basket created: {result}")
                print("Import this file into TWS Basket Trader to execute trades")
            else:
                print("ERROR: Failed to create TWS basket file")

        except ImportError:
            print("ERROR: TWS converter not available - check tws_basket_converter.py")
        except Exception as e:
            print(f"ERROR: Error generating TWS basket: {e}")

    print(f"\n=== COPY-PASTE READY ===")
    print(f"Inverted ticker: {inverted_ticker}")


if __name__ == "__main__":
    main()