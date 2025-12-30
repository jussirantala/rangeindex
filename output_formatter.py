class OutputFormatter:
    def __init__(self, config, client=None):
        self.decimals = config.math_ticker_decimals
        self.client = client
        self.exchange_map = self._build_exchange_map()
        self.exchange_cache = {}  # Cache API results

    def _build_exchange_map(self):
        """Build comprehensive exchange mapping for common stocks"""
        # Start with major stocks by exchange
        exchange_map = {
            # Major NYSE stocks
            'XOM': 'NYSE', 'CVX': 'NYSE', 'FCX': 'NYSE', 'NEM': 'NYSE', 'CAT': 'NYSE',
            'DE': 'NYSE', 'JPM': 'NYSE', 'GS': 'NYSE', 'HD': 'NYSE', 'MCD': 'NYSE',
            'DUK': 'NYSE', 'SO': 'NYSE', 'PG': 'NYSE', 'KO': 'NYSE', 'F': 'NYSE',
            'DAL': 'NYSE', 'BA': 'NYSE', 'LUV': 'NYSE', 'NKE': 'NYSE', 'MMM': 'NYSE',
            'IBM': 'NYSE', 'WMT': 'NYSE', 'JNJ': 'NYSE', 'V': 'NYSE', 'MA': 'NYSE',
            'DIS': 'NYSE', 'T': 'NYSE', 'VZ': 'NYSE', 'ABT': 'NYSE', 'PFE': 'NYSE',
            'BAC': 'NYSE', 'WFC': 'NYSE', 'C': 'NYSE', 'MS': 'NYSE', 'USB': 'NYSE',

            # Major NASDAQ stocks
            'AMZN': 'NASDAQ', 'TSLA': 'NASDAQ', 'NVDA': 'NASDAQ', 'AAPL': 'NASDAQ',
            'SBUX': 'NASDAQ', 'MSFT': 'NASDAQ', 'GOOGL': 'NASDAQ', 'GOOG': 'NASDAQ',
            'META': 'NASDAQ', 'NFLX': 'NASDAQ', 'ADBE': 'NASDAQ', 'INTC': 'NASDAQ',
            'AMD': 'NASDAQ', 'ORCL': 'NASDAQ', 'CRM': 'NASDAQ', 'AVGO': 'NASDAQ',
            'PYPL': 'NASDAQ', 'CSCO': 'NASDAQ', 'QCOM': 'NASDAQ', 'COST': 'NASDAQ',
            'AMGN': 'NASDAQ', 'GILD': 'NASDAQ', 'BIIB': 'NASDAQ', 'MU': 'NASDAQ',

            # Add common small cap NASDAQ patterns - many small caps are on NASDAQ
            'LSAK': 'NASDAQ', 'CLGN': 'NASDAQ', 'BIAF': 'NASDAQ', 'BOLD': 'NASDAQ',
            'MRSN': 'NASDAQ', 'KSLV': 'NASDAQ', 'BBOT': 'NASDAQ', 'EVO': 'NASDAQ'
        }

        return exchange_map

    def _detect_exchange(self, ticker):
        """Detect exchange for a ticker using Polygon API data"""
        # Check cache first
        if ticker in self.exchange_cache:
            return self.exchange_cache[ticker]

        try:
            # Try to get accurate data from Polygon API
            if self.client:
                ticker_details = self.client.get_ticker_details(ticker)
                primary_exchange = getattr(ticker_details, 'primary_exchange', '').upper()

                # Map exchange codes to common names
                exchange_mapping = {
                    'XNYS': 'NYSE',     # NYSE
                    'XNAS': 'NASDAQ',   # NASDAQ
                    'ARCX': 'NYSE',     # NYSE Arca
                    'BATS': 'BATS',     # BATS Exchange
                    'EDGX': 'EDGX',     # EDGX Exchange
                    'EDGA': 'EDGA',     # EDGA Exchange
                    'IEX': 'IEX',       # IEX Exchange
                    'NYSE': 'NYSE',     # Direct NYSE
                    'NASDAQ': 'NASDAQ', # Direct NASDAQ
                }

                # Get the exchange name
                exchange = exchange_mapping.get(primary_exchange, primary_exchange or 'UNKNOWN')

                # Cache the result
                self.exchange_cache[ticker] = exchange
                return exchange

        except Exception:
            pass  # Fall back to heuristic method

        # Fallback to heuristic approach
        exchange = self._detect_exchange_heuristic(ticker)
        self.exchange_cache[ticker] = exchange
        return exchange

    def _detect_exchange_heuristic(self, ticker):
        """Fallback heuristic method for exchange detection"""
        # Check our mapping first
        if ticker in self.exchange_map:
            return self.exchange_map[ticker]

        # Apply heuristic rules for unknown tickers
        ticker_upper = ticker.upper()

        # 4-letter tickers are often NASDAQ (especially biotech/tech)
        if len(ticker_upper) == 4:
            # Check for common biotech/tech patterns
            if any(pattern in ticker_upper for pattern in ['BIO', 'GEN', 'TECH', 'SOFT', 'NET', 'SYS']):
                return 'NASDAQ'
            # 4-letter tickers starting with certain letters tend to be NASDAQ
            if ticker_upper[0] in ['A', 'B', 'C', 'I', 'M', 'Q', 'T', 'Z']:
                return 'NASDAQ'

        # 5+ letter tickers are often NASDAQ
        if len(ticker_upper) >= 5:
            return 'NASDAQ'

        # ETFs with certain patterns
        if any(pattern in ticker_upper for pattern in ['ETF', 'FUND', 'TR', 'IX']):
            return 'NASDAQ'

        # 1-3 letter tickers and traditional symbols often NYSE
        if len(ticker_upper) <= 3:
            return 'NYSE'

        # Default to NASDAQ for modern stocks (more likely for newer companies)
        return 'NASDAQ'

    def format_tradingview_outputs(self, opt_weights):
        """Generate various TradingView format outputs"""
        # Filter out very small weights (keep both positive and negative)
        filtered_weights = {tkr: w for tkr, w in opt_weights.items() if abs(w) > 0.001}

        # Create TradingView format with correct exchanges and proper sign handling
        tv_tickers = []
        for tkr, w in filtered_weights.items():
            exchange = self._detect_exchange(tkr)
            if w >= 0:
                tv_tickers.append(f"{exchange}:{tkr}*{w:.{self.decimals}f}")
            else:
                tv_tickers.append(f"{exchange}:{tkr}*-{abs(w):.{self.decimals}f}")

        math_ticker = "+".join(tv_tickers)

        print(f"\n**TRADINGVIEW MATH TICKER (with exchange - includes shorts):**")
        print(math_ticker)
