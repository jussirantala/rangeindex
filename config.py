import os
from datetime import datetime, timedelta
from dotenv import load_dotenv


class Config:
    def __init__(self):
        load_dotenv()
        self.api_key = os.getenv("POLYGON_API_KEY")
        self.ticker_limit = int(os.getenv("TICKER_LIMIT", "500"))
        self.timespan_days = int(os.getenv("TIMESPAN_DAYS", "30"))
        self.candle_interval = int(os.getenv("CANDLE_INTERVAL", "5"))
        self.candle_unit = os.getenv("CANDLE_UNIT", "minute")
        self.math_ticker_decimals = int(os.getenv("MATH_TICKER_DECIMALS", "6"))
        self.batch_size = int(os.getenv("BATCH_SIZE", "100"))  # Process in batches
        self.max_workers = int(os.getenv("MAX_WORKERS", "4"))  # CPU threads
        self.target_max_stocks = int(os.getenv("TARGET_MAX_STOCKS", "5"))  # Maximum stocks to select
        self.show_charts = os.getenv("SHOW_CHARTS", "true").lower() == "true"  # Enable/disable chart display
        self.include_extended_hours = os.getenv("INCLUDE_EXTENDED_HOURS", "false").lower() == "true"  # Include pre/post market data
        self.data_dir = os.getenv("DATA_DIR", ".")  # Data directory for storing candles
        self.verbose = os.getenv("VERBOSE", "false").lower() == "true"  # Enable/disable verbose output

        # Derived properties - use 3 days back to ensure data availability
        end_datetime = datetime.now() - timedelta(days=3)
        self.end_date = end_datetime.strftime("%Y-%m-%d")
        self.start_date = (end_datetime - timedelta(days=self.timespan_days)).strftime("%Y-%m-%d")
        self.interval = f"{self.candle_interval}{self.candle_unit[:3]}"

        # Non-stock instrument filtering patterns
        self.etf_patterns = [
            # ETF suffixes and patterns
            'ETF', 'FUND', 'TR', 'IX', 'LQD', 'GLD', 'SLV', 'USO', 'UNG',
            # Sector ETFs
            'XLF', 'XLE', 'XLK', 'XLV', 'XLI', 'XLP', 'XLU', 'XLB', 'XLRE', 'XLY',
            # Popular ETFs
            'SPY', 'QQQ', 'IWM', 'EFA', 'EEM', 'VTI', 'VEA', 'VWO', 'BND', 'AGG',
            'TLT', 'IEF', 'SHY', 'HYG', 'LQD', 'IEMG', 'ITOT', 'IXUS', 'IEFA',
            # Leveraged ETFs
            'TQQQ', 'SQQQ', 'SPXL', 'SPXS', 'TNA', 'TZA', 'FAS', 'FAZ', 'LABU', 'LABD',
            # Commodity ETFs
            'GLD', 'SLV', 'PDBC', 'DBA', 'USO', 'UNG', 'CORN', 'WEAT', 'SOYB',
            # Bond ETFs
            'TLT', 'IEF', 'SHY', 'BND', 'AGG', 'HYG', 'LQD', 'VCIT', 'VCSH', 'VGIT',
            # International ETFs
            'EFA', 'EEM', 'VEA', 'VWO', 'IEFA', 'IEMG', 'IXUS', 'ACWI', 'VXUS',
            # Currency ETFs
            'UUP', 'FXE', 'FXY', 'CYB', 'FXB', 'FXA', 'FXC',
            # Specific problematic ones
            'KSLV'  # KraneShares Global Carbon Strategy ETF
        ]

        self.reit_patterns = [
            'REIT', 'REALTY', 'PROPERTIES', 'TRUST'
        ]

        self.known_funds = {
            'KSLV', 'ARKK', 'ARKQ', 'ARKW', 'ARKG', 'ARKF', 'PRNT', 'IZRL', 'CTEC',
            'FINX', 'GNOM', 'DRIV', 'ROBO', 'SOXX', 'IGV', 'SMH', 'XBI', 'IBB',
            'ICLN', 'PBW', 'QCLN', 'SMOG', 'ACES', 'FAN', 'TAN', 'GRID', 'LIT',
            'BATT', 'COPX', 'PICK', 'REMX', 'RING', 'WOOD', 'MOO', 'GURU', 'HACK',
            'CIBR', 'BUG', 'SKYY', 'CLOU', 'WCLD', 'IGRO', 'MOON', 'UFO', 'ESPO',
            # Additional common ETFs/funds
            'VTI', 'VEA', 'VWO', 'VXUS', 'BND', 'BNDX', 'VNQ', 'VNQI', 'VTEB', 'VGIT',
            'MVRL', 'KSLV', 'TQQQ', 'SQQQ', 'SPXL', 'SPXS', 'UDOW', 'SDOW', 'UPRO', 'SPXU'
        }

        # Additional heuristic patterns for stock detection
        self.three_letter_non_stocks = [
            'SPY', 'QQQ', 'IWM', 'EFA', 'EEM', 'BND', 'AGG', 'TLT', 'IEF', 'SHY',
            'GLD', 'SLV', 'USO', 'UNG', 'DBA', 'UUP', 'FXE', 'FXY'
        ]

        self.fund_like_suffixes = ['ETF', 'FUND', 'TR', 'IX']