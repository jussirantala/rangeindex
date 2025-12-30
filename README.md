# rangeIndex

> **AI Generated**

## Overview

Sine wave-based stock index optimization tool that identifies ranging (oscillating) stocks and creates optimized long/short portfolios. Uses mathematical sine wave fitting to detect stocks that exhibit strong cyclical patterns and phase alignment. Generates TradingView-compatible formulas and Interactive Brokers TWS basket files for automated execution.

## Technology Stack

- **Language**: Python 3.x
- **Data Source**: Polygon.io API
- **Analysis**: pandas, numpy, scipy, scikit-learn
- **Visualization**: matplotlib, seaborn, plotly, mplfinance
- **Optimization**: Portfolio weight optimization using covariance

## Main Files

- `app.py` - Main application entry point
- `range_finder_optimized.py` - Core sine wave fitting and ranging detection algorithm
- `portfolio_optimizer.py` - Portfolio weight optimization for long/short positions
- `data_manager.py` - Data loading and caching from Polygon API
- `ticker_manager.py` - Ticker filtering and management
- `ticker_cache.py` - Caching layer for ticker data
- `output_formatter.py` - TradingView math ticker formula generation
- `tws_basket_converter.py` - Interactive Brokers basket file generation
- `chart_visualizer_financial.py` - Financial chart visualization
- `invert_ticker.py` - Short position ticker inversion utility
- `config.py` - Configuration management

## Functionality

### 1. Data Collection
- Fetches historical price data from Polygon.io
- Caches data locally for faster reprocessing
- Filters stocks by market cap, volume, and exchange

### 2. Sine Wave Analysis
- Fits sine waves to price movements using scipy optimization
- Detects ranging behavior (high R² values indicate strong oscillation)
- Calculates phase, amplitude, and frequency for each stock

### 3. Phase Clustering
- Groups stocks by phase alignment
- Identifies stocks that move together cyclically
- Creates clusters for long and short positions

### 4. Portfolio Optimization
- Optimizes position weights using covariance matrices
- Balances long and short exposure
- Minimizes portfolio variance while maximizing ranging characteristics

### 5. Output Generation
- **TradingView Formulas**: Generates math ticker formulas for TradingView charting
  ```
  (SPY * 0.25) + (QQQ * 0.30) + (-VIX * 0.15) + ...
  ```
- **TWS Basket Files**: Creates CSV files for Interactive Brokers basket execution
  ```csv
  Symbol,Quantity,Action
  SPY,100,BUY
  QQQ,50,BUY
  VIX,25,SELL
  ```

## Communication with Other Services

### Outbound Connections
- **Polygon.io REST API**: Fetches historical bar data via `polygon-api-client`
  - Endpoint: `/v2/aggs/ticker/{symbol}/range`
  - Authentication: API key in environment variable

### Output Files
- **TradingView Formulas**: Console output or file export for charting
- **TWS Basket Files**: CSV files that can be imported into Interactive Brokers TWS
- **Cache Files**: Local storage of ticker data for offline analysis

### No Server/API
This is a **command-line tool**, not a service. It does not expose any REST API or WebSocket connections.


## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set up environment variables
cp .env.example .env
# Edit .env with your Polygon API key and desired settings

# 3. (Optional but recommended) Pre-populate cache for speed
python populate_cache.py

# 4. Run the main analysis
python app.py
```

## Detailed Usage

### Environment Configuration

Copy `.env.example` to `.env` and configure:

```bash
# Required
POLYGON_API_KEY=your_polygon_api_key_here

# Analysis Configuration
TICKER_LIMIT=20000                    # Maximum tickers to analyze
TIMESPAN_DAYS=14                      # Historical data period
CANDLE_INTERVAL=1                     # Candle interval (1, 5, 15, etc.)
CANDLE_UNIT=hour                      # Unit: minute, hour, day
TARGET_MAX_STOCKS=10                  # Maximum stocks in final output

# Performance Settings
BATCH_SIZE=1000                       # Processing batch size
MAX_WORKERS=12                        # CPU threads for processing
DATA_DIR=.                           # Data storage directory

# Filtering Options
ACCEPTED_EXCHANGES=NASDAQ,NYSE        # Allowed exchanges
ALLOW_TRENDING_RANGES=true            # Include trending ranges
MAX_TRENDING_CHANGE=0.30              # Max allowed trending change
MIN_CHANNEL_TIGHTNESS=0.15           # Minimum channel tightness

# Display Options
SHOW_CHARTS=true                      # Show visualization charts
INCLUDE_EXTENDED_HOURS=true           # Include pre/post market data
VERBOSE=false                         # Enable detailed logging
MATH_TICKER_DECIMALS=3               # Decimal places in output formulas
```

### Performance Optimization

For faster processing, run the cache population utility once:

```bash
python populate_cache.py
```

This pre-caches ticker metadata and significantly speeds up subsequent analysis runs.

### Command-Line Utilities

#### Ticker Inversion (for short positions)
```bash
python invert_ticker.py "SPY*0.25 + QQQ*0.30"
# Outputs: SPY*-0.25 + QQQ*-0.30
```

#### TWS Basket Conversion

The basket converter transforms TradingView ticker formulas into Interactive Brokers TWS-compatible CSV files for automated trading execution.

**Manual Conversion:**
```bash
python tws_basket_converter.py
# Interactive prompt for TradingView ticker input
# Example input: NASDAQ:AHCO*0.317+NASDAQ:NHTC*0.313-NYSE:NVT*0.223
```

**Features:**
- **Real-time Pricing**: Fetches current market prices via Polygon API
- **Position Sizing**: Calculates exact share quantities based on total investment
- **Exchange Filtering**: Only includes stocks from accepted exchanges (NASDAQ/NYSE)
- **Long/Short Support**: Handles both BUY and SELL positions automatically
- **Fractional Shares**: Supports up to 2 decimal places (IBKR standard)

**Example Conversion Process:**
```
Enter TradingView ticker string:
NASDAQ:AHCO*0.317+NASDAQ:NHTC*0.313-NYSE:NVT*0.223

Enter total investment amount (USD): $10000

Fetching current prices for 3 stocks...
AHCO: $30.00
NHTC: $12.00
NVT: $54.00 (using recent close)

AHCO: 31.7% = $3,170.00 ÷ $30.00 = 10.57 shares
NHTC: 31.3% = $3,130.00 ÷ $12.00 = 26.08 shares
NVT: -22.3% = $2,230.00 ÷ $54.00 = 4.13 shares (SHORT)

TWS Basket CSV created: baskets/basket_AHCO_NHTC_NVT_20241230_143022.csv
```

**Generated CSV Format:**
```csv
Action,Quantity,Symbol,SecType,Exchange,Currency,TimeInForce,OrderType,BasketTag,Account,OrderRef
BUY,10.57,AHCO,STK,SMART/AMEX,USD,GTC,MKT,Basket,,Basket
BUY,26.08,NHTC,STK,SMART/AMEX,USD,GTC,MKT,Basket,,Basket
SELL,4.13,NVT,STK,SMART/AMEX,USD,GTC,MKT,Basket,,Basket
```

**TWS Import Instructions:**
1. Open Interactive Brokers Trader Workstation (TWS)
2. Navigate to **Trade → Basket Trader**
3. Click **Import** and select the generated CSV file
4. Fill in your account number in the Account column
5. Review all positions and prices
6. Submit the basket order for execution

**Price Fallback System:**
- **Primary**: Real-time bid/ask midpoint from Polygon API
- **Secondary**: Most recent daily close price
- **Tertiary**: Estimated prices for common stocks when API is unavailable

### Analysis Process

The tool executes these steps:
1. **Fetch Tickers**: Downloads ticker list from Polygon API
2. **Filter Data**: Removes ETFs, funds, and non-stock instruments
3. **Load Historical Data**: Fetches OHLC data for analysis period
4. **Sine Wave Fitting**: Fits mathematical sine waves to price movements
5. **Range Detection**: Identifies stocks with strong oscillating behavior
6. **Phase Clustering**: Groups stocks by cyclical phase alignment
7. **Portfolio Optimization**: Calculates optimal position weights
8. **Output Generation**: Creates TradingView formulas and TWS basket files

## Output Example

### TradingView Formula
```
(SPY*0.25) + (QQQ*0.30) + (IWM*0.15) + (-VIX*0.10) + (DIA*0.20)
```

### TWS Basket File
```csv
Symbol,Quantity,Action,OrderType,LimitPrice
SPY,100,BUY,LMT,450.00
QQQ,50,BUY,LMT,380.00
VIX,25,SELL,LMT,15.50
```

## Algorithm Details

### Sine Wave Fitting
Uses scipy.optimize.curve_fit to fit the function:
```python
y = A * sin(2π * f * t + φ) + offset
```

Where:
- A = amplitude
- f = frequency (cycles per day)
- φ = phase (offset in radians)
- offset = vertical shift

### Ranging Score
Stocks with high R² values (>0.7) indicate strong cyclical behavior suitable for range trading.

### Phase Clustering
Stocks are grouped into bins based on phase:
- Phase 0-60°: Early cycle (long positions)
- Phase 60-120°: Mid cycle
- Phase 120-180°: Late cycle (short positions)

## Dependencies

See `requirements.txt` for the complete list. Key packages include:

- `polygon-api-client` - Market data API integration
- `pandas` - Data manipulation and analysis
- `numpy` - Numerical computations
- `scipy` - Sine wave fitting and optimization
- `scikit-learn` - Clustering algorithms
- `python-dotenv` - Environment variable management
- `pyarrow` - Fast data serialization
- `matplotlib`, `seaborn`, `plotly` - Data visualization
- `mplfinance` - Financial chart plotting

Install all dependencies with:
```bash
pip install -r requirements.txt
```

## Use Cases

1. **Index Replication**: Create custom weighted indices
2. **Pair Trading**: Find correlated stocks for mean reversion
3. **Range Trading**: Identify oscillating stocks for cyclical strategies
4. **Portfolio Hedging**: Balance long and short exposure
5. **TradingView Charting**: Visualize custom composite indices

## Troubleshooting

### Common Issues

#### API Key Errors

```bash
# Error: Authentication failed
export POLYGON_API_KEY="your_actual_api_key"
# Or set in .env file
```

#### Performance Issues

```bash
# Speed up analysis with cache population
python populate_cache.py

# Reduce ticker limit for testing
# In .env: TICKER_LIMIT=100
```

#### Memory Issues

```bash
# Reduce batch size and worker count
# In .env:
BATCH_SIZE=100
MAX_WORKERS=2
```

#### No Results Found

- Check if `ACCEPTED_EXCHANGES` matches your target markets
- Verify `TARGET_MAX_STOCKS` is reasonable (try 5-10)
- Ensure `TIMESPAN_DAYS` provides sufficient data (14+ recommended)

### Data Quality

- The tool filters out ETFs, REITs, and non-stock instruments automatically
- Stocks must have sufficient trading volume and price history
- Analysis requires clean sine wave patterns (high R² values)

## Notes

- This tool does not execute trades automatically
- Generated basket files must be manually imported into TWS
- TradingView formulas are for visualization only
- Requires active Polygon.io subscription for market data
- Analysis is computationally intensive for large ticker universes
- Results are based on historical patterns and may not predict future performance
