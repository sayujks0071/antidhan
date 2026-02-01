"""
Simple Backtest Engine for OpenAlgo Strategies
----------------------------------------------
A lightweight backtesting framework that uses OpenAlgo API historical data
to test MCX commodity strategies.
"""
import os
import sys
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from pathlib import Path

# Add utils to path
utils_path = Path(__file__).parent
if str(utils_path) not in sys.path:
    sys.path.insert(0, str(utils_path))

# Add project root to path for data validator
project_root = utils_path.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from trading_utils import APIClient
try:
    from openalgo.utils.data_validator import DataValidator
except ImportError:
    # Fallback if package import fails
    sys.path.append(str(project_root / "openalgo" / "utils"))
    try:
        from data_validator import DataValidator
    except ImportError:
        DataValidator = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BacktestEngine")

# Backtest parameters
SLIPPAGE_BPS = 5  # 5 basis points slippage
TRANSACTION_COST_BPS = 3  # 3 basis points transaction cost
TOTAL_COST_BPS = SLIPPAGE_BPS + TRANSACTION_COST_BPS

@dataclass
class Trade:
    """Represents a single trade"""
    entry_time: datetime
    exit_time: Optional[datetime]
    entry_price: float
    exit_price: Optional[float]
    quantity: int
    side: str  # 'BUY' or 'SELL'
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    exit_reason: Optional[str] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

@dataclass
class Position:
    """Represents an open position"""
    entry_time: datetime
    entry_price: float
    quantity: int
    side: str
    stop_loss: float
    take_profit: float
    atr: float

class SimpleBacktestEngine:
    """
    Simple backtesting engine for OpenAlgo strategies.
    """
    
    def __init__(
        self,
        initial_capital: float = 1000000.0,
        api_key: str = None,
        host: str = "http://127.0.0.1:5001"
    ):
        """
        Initialize backtest engine.
        
        Args:
            initial_capital: Starting capital in rupees
            api_key: OpenAlgo API key
            host: OpenAlgo API host
        """
        # #region agent log
        import json
        try:
            with open('/Users/mac/dyad-apps/probable-fiesta/.cursor/debug.log', 'a') as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"init","hypothesisId":"A","location":"simple_backtest_engine.py:__init__","message":"API key before env check","data":{"api_key_provided":api_key is not None,"api_key_length":len(api_key) if api_key else 0,"host":host},"timestamp":int(__import__('time').time()*1000)})+"\n")
        except: pass
        # #endregion
        
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        
        # Initialize API client
        if api_key is None:
            api_key = os.getenv('OPENALGO_APIKEY', 'demo_key')
        
        # #region agent log
        try:
            with open('/Users/mac/dyad-apps/probable-fiesta/.cursor/debug.log', 'a') as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"init","hypothesisId":"A","location":"simple_backtest_engine.py:__init__","message":"API key after env check","data":{"api_key_length":len(api_key) if api_key else 0,"api_key_prefix":api_key[:10] if api_key and len(api_key) > 10 else api_key,"host":host},"timestamp":int(__import__('time').time()*1000)})+"\n")
        except: pass
        # #endregion
        
        self.client = APIClient(api_key=api_key, host=host)
        
        # State
        self.positions: List[Position] = []
        self.closed_trades: List[Trade] = []
        self.equity_curve: List[Tuple[datetime, float]] = []
        
        # Performance metrics
        self.metrics: Dict[str, Any] = {}
    
    def load_historical_data(
        self,
        symbol: str,
        exchange: str,
        start_date: str,
        end_date: str,
        interval: str = "15m"
    ) -> pd.DataFrame:
        """
        Load historical data from OpenAlgo API.
        
        Args:
            symbol: Trading symbol
            exchange: Exchange name (e.g., 'MCX')
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            interval: Data interval (5m, 15m, 1h, etc.)
        
        Returns:
            DataFrame with OHLCV data
        """
        # #region agent log
        import json
        try:
            with open('/Users/mac/dyad-apps/probable-fiesta/.cursor/debug.log', 'a') as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"load_data","hypothesisId":"D","location":"simple_backtest_engine.py:load_historical_data","message":"Before API call","data":{"symbol":symbol,"exchange":exchange,"start_date":start_date,"end_date":end_date,"interval":interval,"api_key_set":hasattr(self.client,'api_key'),"host":self.client.host if hasattr(self.client,'host') else None},"timestamp":int(__import__('time').time()*1000)})+"\n")
        except: pass
        # #endregion
        
        logger.info(f"Loading historical data: {symbol} from {start_date} to {end_date} ({interval})")
        
        try:
            df = self.client.history(
                symbol=symbol,
                exchange=exchange,
                interval=interval,
                start_date=start_date,
                end_date=end_date
            )
            
            # #region agent log
            try:
                with open('/Users/mac/dyad-apps/probable-fiesta/.cursor/debug.log', 'a') as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"load_data","hypothesisId":"D","location":"simple_backtest_engine.py:load_historical_data","message":"After API call","data":{"df_type":type(df).__name__,"df_empty":df.empty if isinstance(df,pd.DataFrame) else True,"df_shape":list(df.shape) if isinstance(df,pd.DataFrame) else None,"df_columns":list(df.columns) if isinstance(df,pd.DataFrame) and hasattr(df,'columns') else None},"timestamp":int(__import__('time').time()*1000)})+"\n")
            except: pass
            # #endregion
            
            if not isinstance(df, pd.DataFrame) or df.empty:
                logger.warning(f"No data returned for {symbol}")
                return pd.DataFrame()
            
            # Ensure datetime index - handle both 'datetime' and 'timestamp' columns
            if 'datetime' in df.columns:
                df['datetime'] = pd.to_datetime(df['datetime'])
                df = df.set_index('datetime')
            elif 'timestamp' in df.columns:
                # API returns 'timestamp' column, convert to datetime index
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df = df.set_index('timestamp')
            elif not isinstance(df.index, pd.DatetimeIndex):
                # Try to convert index to datetime if it's numeric or string
                try:
                    df.index = pd.to_datetime(df.index)
                except (ValueError, TypeError):
                    logger.warning("Could not convert index to datetime, using as-is")
            
            # #region agent log
            try:
                with open('/Users/mac/dyad-apps/probable-fiesta/.cursor/debug.log', 'a') as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"load_data","hypothesisId":"G","location":"simple_backtest_engine.py:load_historical_data","message":"After datetime conversion","data":{"index_type":type(df.index).__name__,"is_datetime_index":isinstance(df.index,pd.DatetimeIndex),"df_shape":list(df.shape),"has_timestamp_col":"timestamp" in df.columns,"has_datetime_col":"datetime" in df.columns},"timestamp":int(__import__('time').time()*1000)})+"\n")
            except: pass
            # #endregion
            
            # Sort by datetime
            df = df.sort_index()
            
            logger.info(f"Loaded {len(df)} bars for {symbol}")
            return df
            
        except Exception as e:
            # #region agent log
            try:
                with open('/Users/mac/dyad-apps/probable-fiesta/.cursor/debug.log', 'a') as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"load_data","hypothesisId":"F","location":"simple_backtest_engine.py:load_historical_data","message":"Exception caught","data":{"error_type":type(e).__name__,"error_message":str(e),"symbol":symbol,"exchange":exchange},"timestamp":int(__import__('time').time()*1000)})+"\n")
            except: pass
            # #endregion
            logger.error(f"Error loading historical data: {e}")
            return pd.DataFrame()
    
    def apply_costs(self, price: float, quantity: int, side: str) -> float:
        """
        Apply slippage and transaction costs to a trade.
        
        Args:
            price: Base price
            quantity: Trade quantity
            side: 'BUY' or 'SELL'
        
        Returns:
            Effective price after costs
        """
        cost_factor = TOTAL_COST_BPS / 10000.0
        
        if side == 'BUY':
            # Pay more when buying
            return price * (1 + cost_factor)
        else:
            # Receive less when selling
            return price * (1 - cost_factor)
    
    def check_exits(self, current_bar: pd.Series, position: Position, current_time: datetime, strategy_module=None, interval="15m", historical_df=None) -> Tuple[bool, Optional[str], Optional[float]]:
        """
        Check if position should be exited based on SL/TP, Time Stop, Breakeven, or Custom Strategy Exit.
        """
        current_price = current_bar['close']
        high = current_bar['high']
        low = current_bar['low']

        # 0. Custom Strategy Exit
        if strategy_module and hasattr(strategy_module, 'check_exit'):
            try:
                should_exit, reason, price = strategy_module.check_exit(historical_df, position)
                if should_exit:
                    return True, reason, (price if price else current_price)
            except Exception as e:
                logger.error(f"Error in strategy check_exit: {e}")
        
        # 1. Time Stop
        if strategy_module and hasattr(strategy_module, 'TIME_STOP_BARS'):
            # Calculate duration limit based on interval
            try:
                # Convert interval string (e.g. '15m') to timedelta
                # pandas usually handles '15m' as 15 minutes in to_timedelta if we strictly parse,
                # but standard aliases might vary. '15min' is safe.
                # Simplistic mapping for common intervals
                if interval.endswith('m') and not interval.endswith('min'):
                    # Treat 'm' as minutes for backtest context
                    delta_str = interval.replace('m', 'min')
                else:
                    delta_str = interval

                bar_duration = pd.to_timedelta(delta_str)
            except:
                # Fallback to 15m default
                bar_duration = timedelta(minutes=15)

            time_diff = current_time - position.entry_time
            # Check if duration exceeds allowed bars
            if time_diff > (bar_duration * strategy_module.TIME_STOP_BARS):
                return True, 'TIME_STOP', current_price

        # 2. Breakeven Trigger
        if strategy_module and hasattr(strategy_module, 'BREAKEVEN_TRIGGER_R'):
            r_multiple = strategy_module.BREAKEVEN_TRIGGER_R
            risk = abs(position.entry_price - position.stop_loss)
            if risk > 0:
                if position.side == 'BUY':
                    if high >= position.entry_price + (r_multiple * risk):
                        # Move SL to Entry (plus cost buffer?)
                        position.stop_loss = max(position.stop_loss, position.entry_price * 1.0005)
                else:
                    if low <= position.entry_price - (r_multiple * risk):
                        position.stop_loss = min(position.stop_loss, position.entry_price * 0.9995)

        if position.side == 'BUY':
            # Long position
            # Check stop loss
            if low <= position.stop_loss:
                # Execution price is SL or Open if Gap
                exec_price = position.stop_loss if current_bar['open'] > position.stop_loss else current_bar['open']
                return True, 'STOP_LOSS', exec_price
            
            # Check take profit
            if high >= position.take_profit:
                exec_price = position.take_profit if current_bar['open'] < position.take_profit else current_bar['open']
                return True, 'TAKE_PROFIT', exec_price
        
        else:
            # Short position
            # Check stop loss
            if high >= position.stop_loss:
                exec_price = position.stop_loss if current_bar['open'] < position.stop_loss else current_bar['open']
                return True, 'STOP_LOSS', exec_price
            
            # Check take profit
            if low <= position.take_profit:
                exec_price = position.take_profit if current_bar['open'] > position.take_profit else current_bar['open']
                return True, 'TAKE_PROFIT', exec_price
        
        return False, None, None
    
    def run_backtest(
        self,
        strategy_module,
        symbol: str,
        exchange: str,
        start_date: str,
        end_date: str,
        interval: str = "15m"
    ) -> Dict[str, Any]:
        """
        Run backtest on a strategy.
        
        Args:
            strategy_module: Strategy module with generate_signal() function
            symbol: Trading symbol
            exchange: Exchange name
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            interval: Data interval
        
        Returns:
            Dictionary with backtest results
        """
        logger.info("=" * 70)
        logger.info("Starting Backtest")
        logger.info("=" * 70)
        logger.info(f"Symbol: {symbol}")
        logger.info(f"Date Range: {start_date} to {end_date}")
        logger.info(f"Interval: {interval}")
        logger.info(f"Initial Capital: ₹{self.initial_capital:,.2f}")
        logger.info("=" * 70)
        
        # Reset state
        self.current_capital = self.initial_capital
        self.positions = []
        self.closed_trades = []
        self.equity_curve = []
        
        # Load historical data
        df = self.load_historical_data(symbol, exchange, start_date, end_date, interval)
        
        if df.empty:
            logger.error("No data available for backtest")
            return {'error': 'No data available'}
        
        # Ensure required columns exist
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            logger.error(f"Missing required columns: {missing_cols}")
            return {'error': f'Missing columns: {missing_cols}'}
        
        # Validate Data
        if DataValidator:
            val_res = DataValidator.validate_ohlcv(df, symbol=symbol)
            if not val_res['is_valid']:
                logger.warning(f"Data Validation Failed: {val_res['issues']}")
                # We log warning but proceed, or return error?
                # For now, just warn loudly
            elif val_res['issues']:
                logger.warning(f"Data Quality Issues: {val_res['issues']}")
            else:
                logger.info("Data Validation Passed ✅")

        # Run backtest
        logger.info(f"Processing {len(df)} bars...")
        
        # Use a rolling window for signal generation
        window_size = 50  # Minimum bars needed for indicators
        
        for i in range(window_size, len(df)):
            current_bar = df.iloc[i]
            current_time = df.index[i]
            
            # Get historical data up to current bar
            historical_df = df.iloc[:i+1].copy()
            
            # Check for exits first
            for pos in self.positions[:]:  # Copy list to avoid modification during iteration
                should_exit, exit_reason, exit_price = self.check_exits(current_bar, pos, current_time, strategy_module, interval=interval, historical_df=historical_df)
                
                if should_exit:
                    # Close position
                    exit_price_with_costs = self.apply_costs(exit_price, pos.quantity, 'SELL' if pos.side == 'BUY' else 'BUY')
                    entry_price_with_costs = self.apply_costs(pos.entry_price, pos.quantity, pos.side)
                    
                    if pos.side == 'BUY':
                        pnl = (exit_price_with_costs - entry_price_with_costs) * pos.quantity
                    else:
                        pnl = (entry_price_with_costs - exit_price_with_costs) * pos.quantity
                    
                    pnl_pct = (pnl / (entry_price_with_costs * abs(pos.quantity))) * 100
                    
                    trade = Trade(
                        entry_time=pos.entry_time,
                        exit_time=current_time,
                        entry_price=pos.entry_price,
                        exit_price=exit_price,
                        quantity=pos.quantity,
                        side=pos.side,
                        pnl=pnl,
                        pnl_pct=pnl_pct,
                        exit_reason=exit_reason,
                        stop_loss=pos.stop_loss,
                        take_profit=pos.take_profit
                    )
                    
                    self.closed_trades.append(trade)
                    self.positions.remove(pos)
                    
                    # Update capital
                    self.current_capital += pnl
                    
                    logger.debug(f"Exit: {pos.side} @ {exit_price:.2f}, P&L: ₹{pnl:,.2f} ({pnl_pct:.2f}%)")
            
            # Generate signal if no position
            if len(self.positions) == 0:
                try:
                    # Call strategy's generate_signal function
                    action, score, details = strategy_module.generate_signal(
                        historical_df,
                        client=self.client,
                        symbol=symbol
                    )
                    
                    if action in ['BUY', 'SELL']:
                        # Calculate position size
                        # Support strategy returning size (as float or int)
                        if isinstance(score, (int, float)) and score > 0 and score != 1.0:
                             # Interpretation: score is size multiplier?
                             # In existing strategies, score is 1.0 usually.
                             # AI_Hybrid might set score based on logic?
                             pass
                        
                        # Check if strategy returned a specific quantity in details
                        quantity = details.get('quantity', 1)
                        if quantity <= 0: quantity = 1

                        # Calculate SL/TP based on ATR
                        atr = details.get('atr', 0)
                        current_price = current_bar['close']
                        
                        if atr > 0:
                            # Get strategy-specific multipliers
                            if hasattr(strategy_module, 'ATR_SL_MULTIPLIER'):
                                sl_mult = strategy_module.ATR_SL_MULTIPLIER
                            else:
                                sl_mult = 1.5
                            
                            if hasattr(strategy_module, 'ATR_TP_MULTIPLIER'):
                                tp_mult = strategy_module.ATR_TP_MULTIPLIER
                            else:
                                tp_mult = 2.5
                            
                            if action == 'BUY':
                                stop_loss = current_price - (sl_mult * atr)
                                take_profit = current_price + (tp_mult * atr)
                            else:
                                stop_loss = current_price + (sl_mult * atr)
                                take_profit = current_price - (tp_mult * atr)
                        else:
                            # Fallback: percentage-based
                            stop_loss = current_price * 0.98 if action == 'BUY' else current_price * 1.02
                            take_profit = current_price * 1.02 if action == 'BUY' else current_price * 0.98
                        
                        # Create position
                        entry_price_with_costs = self.apply_costs(current_price, quantity, action)
                        
                        position = Position(
                            entry_time=current_time,
                            entry_price=current_price,
                            quantity=quantity if action == 'BUY' else -quantity,
                            side=action,
                            stop_loss=stop_loss,
                            take_profit=take_profit,
                            atr=atr
                        )
                        
                        self.positions.append(position)
                        logger.debug(f"Entry: {action} @ {current_price:.2f}, SL: {stop_loss:.2f}, TP: {take_profit:.2f}")
                
                except Exception as e:
                    logger.debug(f"Error generating signal: {e}")
                    continue
            
            # Update equity curve
            current_equity = self.current_capital
            if self.positions:
                # Add unrealized P&L
                for pos in self.positions:
                    if pos.side == 'BUY':
                        unrealized_pnl = (current_bar['close'] - pos.entry_price) * pos.quantity
                    else:
                        unrealized_pnl = (pos.entry_price - current_bar['close']) * abs(pos.quantity)
                    current_equity += unrealized_pnl
            
            self.equity_curve.append((current_time, current_equity))
        
        # Close any remaining positions at end
        if self.positions and len(df) > 0:
            final_bar = df.iloc[-1]
            final_time = df.index[-1]
            final_price = final_bar['close']
            
            for pos in self.positions[:]:
                exit_price_with_costs = self.apply_costs(final_price, pos.quantity, 'SELL' if pos.side == 'BUY' else 'BUY')
                entry_price_with_costs = self.apply_costs(pos.entry_price, pos.quantity, pos.side)
                
                if pos.side == 'BUY':
                    pnl = (exit_price_with_costs - entry_price_with_costs) * pos.quantity
                else:
                    pnl = (entry_price_with_costs - exit_price_with_costs) * abs(pos.quantity)
                
                pnl_pct = (pnl / (entry_price_with_costs * abs(pos.quantity))) * 100
                
                trade = Trade(
                    entry_time=pos.entry_time,
                    exit_time=final_time,
                    entry_price=pos.entry_price,
                    exit_price=final_price,
                    quantity=pos.quantity,
                    side=pos.side,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    exit_reason='END_OF_DATA',
                    stop_loss=pos.stop_loss,
                    take_profit=pos.take_profit
                )
                
                self.closed_trades.append(trade)
                self.current_capital += pnl
        
        # Calculate metrics
        self.metrics = self.calculate_metrics()
        
        logger.info("=" * 70)
        logger.info("Backtest Complete")
        logger.info("=" * 70)
        logger.info(f"Total Trades: {len(self.closed_trades)}")
        logger.info(f"Final Capital: ₹{self.current_capital:,.2f}")
        logger.info(f"Total Return: ₹{self.current_capital - self.initial_capital:,.2f} ({self.metrics.get('total_return_pct', 0):.2f}%)")
        logger.info(f"Win Rate: {self.metrics.get('win_rate', 0):.2f}%")
        logger.info(f"Profit Factor: {self.metrics.get('profit_factor', 0):.2f}")
        logger.info("=" * 70)
        
        return {
            'initial_capital': self.initial_capital,
            'final_capital': self.current_capital,
            'total_trades': len(self.closed_trades),
            'closed_trades': [
                {
                    'entry_time': str(t.entry_time),
                    'exit_time': str(t.exit_time) if t.exit_time else None,
                    'entry_price': t.entry_price,
                    'exit_price': t.exit_price,
                    'quantity': t.quantity,
                    'side': t.side,
                    'pnl': t.pnl,
                    'pnl_pct': t.pnl_pct,
                    'exit_reason': t.exit_reason
                }
                for t in self.closed_trades
            ],
            'equity_curve': [(str(t), e) for t, e in self.equity_curve],
            'metrics': self.metrics
        }
    
    def calculate_metrics(self) -> Dict[str, Any]:
        """Calculate performance metrics"""
        if not self.closed_trades:
            return {
                'total_return_pct': 0.0,
                'win_rate': 0.0,
                'profit_factor': 0.0,
                'max_drawdown_pct': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'largest_win': 0.0,
                'largest_loss': 0.0,
                'sharpe_ratio': 0.0
            }
        
        # Total return
        total_return = self.current_capital - self.initial_capital
        total_return_pct = (total_return / self.initial_capital) * 100
        
        # Win rate
        winning_trades = [t for t in self.closed_trades if t.pnl and t.pnl > 0]
        losing_trades = [t for t in self.closed_trades if t.pnl and t.pnl < 0]
        win_rate = (len(winning_trades) / len(self.closed_trades)) * 100 if self.closed_trades else 0
        
        # Profit factor
        total_profit = sum(t.pnl for t in winning_trades) if winning_trades else 0
        total_loss = abs(sum(t.pnl for t in losing_trades)) if losing_trades else 1
        profit_factor = total_profit / total_loss if total_loss > 0 else 0
        
        # Average win/loss
        avg_win = total_profit / len(winning_trades) if winning_trades else 0
        avg_loss = sum(t.pnl for t in losing_trades) / len(losing_trades) if losing_trades else 0
        
        # Largest win/loss
        largest_win = max((t.pnl for t in winning_trades), default=0)
        largest_loss = min((t.pnl for t in losing_trades), default=0)
        
        # Max drawdown
        if self.equity_curve:
            equity_values = [e for _, e in self.equity_curve]
            peak = equity_values[0]
            max_drawdown = 0
            
            for equity in equity_values:
                if equity > peak:
                    peak = equity
                drawdown = ((peak - equity) / peak) * 100
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
        else:
            max_drawdown = 0
        
        # Sharpe ratio (simplified - using returns)
        if len(self.closed_trades) > 1:
            returns = [t.pnl_pct for t in self.closed_trades if t.pnl_pct is not None]
            if returns:
                mean_return = np.mean(returns)
                std_return = np.std(returns)
                sharpe_ratio = (mean_return / std_return) * np.sqrt(252) if std_return > 0 else 0
            else:
                sharpe_ratio = 0
        else:
            sharpe_ratio = 0
        
        return {
            'total_return_pct': total_return_pct,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'max_drawdown_pct': max_drawdown,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'largest_win': largest_win,
            'largest_loss': largest_loss,
            'sharpe_ratio': sharpe_ratio,
            'total_profit': total_profit,
            'total_loss': -total_loss
        }
