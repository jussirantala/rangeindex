import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import numpy as np
from datetime import datetime
import mplfinance as mpf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import seaborn as sns


class RangeIndexFinancialVisualizer:
    def __init__(self, use_plotly=True, dark_theme=True):
        """Initialize the financial chart visualizer with TradingView-style appearance"""
        self.use_plotly = use_plotly
        self.dark_theme = dark_theme

        if dark_theme:
            # TradingView dark theme colors
            self.bg_color = '#1e222d'
            self.paper_color = '#131722'
            self.text_color = '#d1d4dc'
            self.grid_color = '#363a45'
            self.accent_color = '#2962ff'
            self.positive_color = '#26a69a'
            self.negative_color = '#ef5350'
            self.neutral_color = '#787b86'
            self.volume_color = '#434651'
        else:
            # TradingView light theme colors
            self.bg_color = '#ffffff'
            self.paper_color = '#ffffff'
            self.text_color = '#2e3856'
            self.grid_color = '#e1ecf4'
            self.accent_color = '#2962ff'
            self.positive_color = '#26a69a'
            self.negative_color = '#ef5350'
            self.neutral_color = '#787b86'
            self.volume_color = '#e8eaed'

    def create_index_chart(self, prices_df, weights, ranging_scores, portfolio_stats, ohlc_data=None):
        """Create a comprehensive TradingView-style chart showing the ranging index performance"""
        try:
            # Calculate the weighted index values
            index_values = self._calculate_index_values(prices_df, weights)

            if self.use_plotly and ohlc_data is not None:
                return self._create_plotly_chart(index_values, prices_df, weights, ranging_scores, portfolio_stats, ohlc_data)
            else:
                return self._create_mplfinance_chart(index_values, prices_df, weights, ranging_scores, portfolio_stats)

        except Exception as e:
            print(f"Error creating financial chart: {e}")
            return False

    def _create_plotly_chart(self, index_values, prices_df, weights, ranging_scores, portfolio_stats, ohlc_data):
        """Create interactive TradingView-style chart using Plotly"""

        # Note: Using line chart instead of OHLC for easier debugging
        valid_data = index_values.dropna()

        # Create subplots: main chart, portfolio weights, individual stocks
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=('Range Index (Line Chart)', 'Portfolio Weights & Ranging Scores',
                          'Individual Stock Performance', ''),
            specs=[[{"secondary_y": False}, {"secondary_y": False}],
                   [{"colspan": 2}, None]],
            vertical_spacing=0.12,
            horizontal_spacing=0.15,
            row_heights=[0.6, 0.4]
        )

        # 1. Main Line Chart for Index (simplified for debugging)
        if len(valid_data) > 0:
            fig.add_trace(
                go.Scatter(
                    x=valid_data.index,
                    y=valid_data.values,
                    mode='lines',
                    name="Range Index",
                    line=dict(color=self.accent_color, width=2),
                    hovertemplate='%{x}<br>Value: %{y:.2f}<extra></extra>'
                ),
                row=1, col=1
            )

            # Add moving averages if enough data
            if len(valid_data) >= 20:
                ma20 = valid_data.rolling(20).mean()
                fig.add_trace(
                    go.Scatter(
                        x=valid_data.index,
                        y=ma20,
                        mode='lines',
                        name='MA 20',
                        line=dict(color=self.positive_color, width=1, dash='dash'),
                        opacity=0.7
                    ),
                    row=1, col=1
                )

        # 2. Portfolio Weights
        sorted_weights = sorted(weights.items(), key=lambda x: abs(x[1]), reverse=True)
        tickers = [item[0] for item in sorted_weights[:15]]  # Top 15 positions
        weights_values = [item[1] * 100 for item in sorted_weights[:15]]  # Convert to percentage
        scores = [ranging_scores.get(ticker, 0) for ticker in tickers]

        # Color based on long/short
        colors = [self.positive_color if w > 0 else self.negative_color for w in weights_values]

        fig.add_trace(
            go.Bar(
                y=tickers,
                x=[abs(w) for w in weights_values],
                orientation='h',
                name='Weights',
                marker_color=colors,
                text=[f'{score:.3f}' for score in scores],
                textposition='outside',
                hovertemplate='%{y}: %{x:.1f}%<br>Score: %{text}<extra></extra>'
            ),
            row=1, col=2
        )

        # 3. Individual Stock Performance (normalized)
        sorted_weights_top = sorted_weights[:8]  # Top 8 for clarity
        for ticker, weight in sorted_weights_top:
            if ticker in prices_df.columns:
                stock_data = prices_df[ticker].dropna()
                if len(stock_data) > 0:
                    normalized_stock = (stock_data / stock_data.iloc[0] - 1) * 100

                    color = self.positive_color if weight > 0 else self.negative_color
                    linestyle = 'solid' if weight > 0 else 'dash'

                    fig.add_trace(
                        go.Scatter(
                            x=normalized_stock.index,
                            y=normalized_stock.values,
                            mode='lines',
                            name=f'{ticker} ({weight:+.1%})',
                            line=dict(color=color, dash=linestyle, width=1),
                            opacity=min(1.0, abs(weight) * 3),
                            hovertemplate='%{y:.2f}%<extra></extra>'
                        ),
                        row=2, col=1
                    )

        # Update layout with TradingView styling
        fig.update_layout(
            title=dict(
                text='Range Index Analysis - TradingView Style',
                font=dict(size=16, color=self.text_color)
            ),
            template='plotly_dark' if self.dark_theme else 'plotly_white',
            paper_bgcolor=self.paper_color,
            plot_bgcolor=self.bg_color,
            font=dict(color=self.text_color),
            showlegend=True,
            height=700,
            margin=dict(l=50, r=50, t=80, b=50)
        )

        # Update axes styling with market-aware time formatting
        for i in range(1, 3):  # 2 rows
            for j in range(1, 3):
                try:
                    # Determine appropriate tick spacing based on data timeframe
                    if len(valid_data) > 0:
                        time_span = (valid_data.index[-1] - valid_data.index[0]).total_seconds()

                        if time_span <= 86400:  # Less than 1 day
                            tick_interval = 4 * 3600 * 1000  # 4 hour intervals
                            tick_format = '%H:%M'
                        elif time_span <= 7 * 86400:  # Less than 1 week
                            tick_interval = 24 * 3600 * 1000  # Daily intervals
                            tick_format = '%m/%d'
                        else:  # More than 1 week
                            tick_interval = 7 * 24 * 3600 * 1000  # Weekly intervals
                            tick_format = '%m/%d'
                    else:
                        tick_interval = 4 * 3600 * 1000  # Default 4 hour intervals
                        tick_format = '%m/%d %H:%M'

                    fig.update_xaxes(
                        gridcolor=self.grid_color,
                        gridwidth=1,
                        showgrid=True,
                        tickformat=tick_format,
                        tickangle=45,
                        dtick=tick_interval,
                        nticks=8,  # Limit to maximum 8 ticks
                        row=i, col=j
                    )
                    fig.update_yaxes(
                        gridcolor=self.grid_color,
                        gridwidth=1,
                        showgrid=True,
                        tickformat='.2f',
                        row=i, col=j
                    )
                except:
                    pass  # Skip if subplot doesn't exist

        # Add performance metrics as annotation
        if len(valid_data) > 0:
            total_return = (valid_data.iloc[-1] / valid_data.iloc[0] - 1) * 100
            max_drawdown = ((valid_data.cummax() - valid_data) / valid_data.cummax()).max() * 100

            metrics_text = f"""
            <b>Performance Metrics:</b><br>
            Total Return: {total_return:.1f}%<br>
            Max Drawdown: {max_drawdown:.1f}%<br>
            Portfolio Score: {portfolio_stats.get('ranging_score', 0):.3f}<br>
            Volatility: {portfolio_stats.get('volatility', 0)*100:.1f}%
            """

            fig.add_annotation(
                text=metrics_text,
                xref="paper", yref="paper",
                x=0.02, y=0.98,
                showarrow=False,
                align="left",
                bgcolor=self.bg_color,
                bordercolor=self.grid_color,
                borderwidth=1,
                font=dict(size=10, color=self.text_color)
            )

        # Show the chart with explicit browser opening
        print("Opening TradingView-style Plotly chart in browser...")
        try:
            # Always save HTML file for viewing
            html_filename = "tradingview_style_chart.html"
            fig.write_html(html_filename)
            print(f"SUCCESS: Chart saved as {html_filename}")

            # Try to show in browser
            fig.show()
            print("SUCCESS: Plotly chart should now be visible in your browser!")
        except Exception as e:
            print(f"ERROR: Error displaying Plotly chart: {e}")
            # Try alternative display methods
            try:
                import webbrowser
                html_filename = "tradingview_style_chart_backup.html"
                fig.write_html(html_filename)
                webbrowser.open(html_filename)
                print(f"SUCCESS: Chart saved as {html_filename} and opened in browser")
            except Exception as e2:
                print(f"ERROR: Alternative display method failed: {e2}")
        return True

    def _create_mplfinance_chart(self, index_values, prices_df, weights, ranging_scores, portfolio_stats):
        """Create financial chart using mplfinance as fallback"""
        try:
            # Create a simple OHLC representation of the index
            # For demonstration, use index values as close and create synthetic OHLC
            valid_data = index_values.dropna()
            if len(valid_data) < 2:
                print("Not enough data for OHLC chart")
                return False

            # Create synthetic OHLC data from index values
            ohlc_data = pd.DataFrame(index=valid_data.index)
            ohlc_data['close'] = valid_data.values

            # Create simple synthetic OHLC (this is just for demonstration)
            # In real implementation, you'd want actual OHLC data
            ohlc_data['open'] = ohlc_data['close'].shift(1).fillna(ohlc_data['close'].iloc[0])
            ohlc_data['high'] = ohlc_data[['open', 'close']].max(axis=1) * 1.001
            ohlc_data['low'] = ohlc_data[['open', 'close']].min(axis=1) * 0.999
            ohlc_data['volume'] = 1000000  # Synthetic volume

            # TradingView-style configuration
            mc = mpf.make_marketcolors(
                up=self.positive_color,
                down=self.negative_color,
                edge='inherit',
                wick={'up': self.positive_color, 'down': self.negative_color},
                volume={'up': self.positive_color, 'down': self.negative_color}
            )

            s = mpf.make_mpf_style(
                marketcolors=mc,
                gridstyle='-',
                gridcolor=self.grid_color,
                facecolor=self.bg_color,
                figcolor=self.paper_color,
                edgecolor=self.text_color
            )

            # Determine appropriate tick frequency for x-axis
            time_span = (ohlc_data.index[-1] - ohlc_data.index[0]).total_seconds()
            num_points = len(ohlc_data)

            # Calculate reasonable tick frequency
            if num_points > 100:
                tick_freq = max(1, num_points // 8)  # Show ~8 ticks maximum
            else:
                tick_freq = max(1, num_points // 5)  # Show ~5 ticks for smaller datasets

            # Create the plot with custom formatting
            fig, axes = mpf.plot(
                ohlc_data,
                type='candle',
                style=s,
                title='Range Index - OHLC Chart',
                ylabel='Index Value',
                volume=True,
                mav=(20,) if len(ohlc_data) >= 20 else None,
                figsize=(14, 10),
                tight_layout=True,
                returnfig=True,
                datetime_format='%m/%d %H:%M' if time_span <= 7*86400 else '%m/%d',
                xrotation=45
            )

            # Further customize x-axis labels
            if axes:
                for ax in axes:
                    if hasattr(ax, 'xaxis'):
                        # Reduce number of x-axis labels
                        ax.locator_params(axis='x', nbins=6)
                        # Rotate labels for better readability
                        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')

            plt.tight_layout()
            print("Opening mplfinance chart window...")
            plt.show(block=False)  # Non-blocking to allow script to continue
            print("SUCCESS: mplfinance chart window should now be visible!")

            return True

        except Exception as e:
            print(f"Error creating mplfinance chart: {e}")
            return False

    def _calculate_index_values(self, prices_df, weights):
        """Calculate index values exactly like TradingView math ticker: weighted sum of absolute prices"""
        # Get common tickers that exist in both weights and price data
        common_tickers = [ticker for ticker in weights.keys() if ticker in prices_df.columns]

        if not common_tickers:
            return pd.Series(dtype=float)

        # TradingView math ticker: simply multiply each price by its weight and sum
        # This is exactly how TradingView's AAPL*0.5+MSFT*0.3 formula works
        price_data = prices_df[common_tickers].copy()

        # Apply weights directly to prices (TradingView style)
        weighted_prices = price_data.multiply(pd.Series(weights), axis=1)

        # Sum to get index value, handling missing data properly
        index_values = weighted_prices.sum(axis=1, min_count=1)  # min_count=1 ensures NaN if all values are NaN

        return index_values

    def _create_index_ohlc(self, ohlc_data, weights):
        """Create OHLC data exactly like TradingView math ticker: simply weighted sum of prices"""
        try:
            if not ohlc_data or not weights:
                return None

            # Get common tickers that exist in both weights and OHLC data
            common_tickers = [ticker for ticker in weights.keys() if ticker in ohlc_data and ohlc_data[ticker] is not None]

            if not common_tickers:
                return None

            # Find union of all timestamps (TradingView uses all available data points)
            all_timestamps = set()
            for ticker in common_tickers:
                all_timestamps.update(ohlc_data[ticker].index)

            if not all_timestamps:
                return None

            common_timestamps = sorted(all_timestamps)

            # Initialize index OHLC DataFrame
            index_ohlc = pd.DataFrame(index=common_timestamps, columns=['open', 'high', 'low', 'close', 'volume'])

            # Calculate index OHLC for each timestamp - TradingView style (simple weighted sum)
            for timestamp in common_timestamps:
                weighted_open = 0
                weighted_high = 0
                weighted_low = 0
                weighted_close = 0
                total_volume = 0
                has_data = False

                for ticker in common_tickers:
                    ticker_data = ohlc_data[ticker]
                    weight = weights[ticker]

                    if timestamp in ticker_data.index:
                        row = ticker_data.loc[timestamp]

                        # Skip if any OHLC value is missing for this timestamp
                        if pd.isna(row['open']) or pd.isna(row['high']) or pd.isna(row['low']) or pd.isna(row['close']):
                            continue

                        # TradingView math ticker: simply multiply price by weight and sum
                        # For shorts, the weight is negative, which naturally inverts the contribution
                        weighted_open += row['open'] * weight
                        weighted_high += row['high'] * weight
                        weighted_low += row['low'] * weight
                        weighted_close += row['close'] * weight
                        total_volume += row['volume'] * abs(weight)  # Volume is always positive
                        has_data = True

                # Only include timestamps where we have at least some data
                if has_data:
                    # For shorts, we need to handle OHLC relationships correctly
                    # When we have negative weights, high and low can get inverted
                    ohlc_values = [weighted_open, weighted_high, weighted_low, weighted_close]

                    index_ohlc.loc[timestamp, 'open'] = weighted_open
                    index_ohlc.loc[timestamp, 'close'] = weighted_close
                    index_ohlc.loc[timestamp, 'high'] = max(ohlc_values)  # Highest value
                    index_ohlc.loc[timestamp, 'low'] = min(ohlc_values)   # Lowest value
                    index_ohlc.loc[timestamp, 'volume'] = total_volume

            # Remove rows with all NaN values
            index_ohlc = index_ohlc.dropna(how='all')

            # Convert to numeric to handle any string/object dtypes
            for col in ['open', 'high', 'low', 'close', 'volume']:
                index_ohlc[col] = pd.to_numeric(index_ohlc[col], errors='coerce')

            # Final validation: ensure proper OHLC relationships
            for idx in index_ohlc.index:
                row = index_ohlc.loc[idx]
                if not pd.isna(row['open']) and not pd.isna(row['close']):
                    # Ensure high is at least as high as open and close
                    max_oc = max(row['open'], row['close'])
                    if pd.isna(row['high']) or row['high'] < max_oc:
                        index_ohlc.loc[idx, 'high'] = max_oc

                    # Ensure low is at least as low as open and close
                    min_oc = min(row['open'], row['close'])
                    if pd.isna(row['low']) or row['low'] > min_oc:
                        index_ohlc.loc[idx, 'low'] = min_oc

            return index_ohlc

        except Exception as e:
            print(f"Error creating index OHLC: {e}")
            import traceback
            traceback.print_exc()
            return None