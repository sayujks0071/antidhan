#!/usr/bin/env python3
"""
Silver Mini Position Monitor with Strict Stop Loss and Take Profit
Continuously monitors Silver Mini BUY position and executes exits when SL/TP hit
"""
import os
import sys
import time
import json
import subprocess
import logging
from pathlib import Path
from datetime import datetime, timedelta
import pytz
import pandas as pd

# Add utils to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'strategies' / 'utils'))
from trading_utils import APIClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Path(__file__).parent.parent / 'log' / 'silver_position_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("SilverPositionMonitor")

# Position Configuration
SYMBOL = "SILVERM27FEB26FUT"
EXCHANGE = "MCX"
ENTRY_PRICE = 364935.00
POSITION_SIDE = "BUY"  # Current position is BUY
QUANTITY = 1  # 1 lot

# Strict Risk Management Parameters
STOP_LOSS_PCT = 0.8  # 0.8% stop loss (strict)
TAKE_PROFIT_PCT = 1.6  # 1.6% take profit (2:1 R:R)
TRAILING_STOP_ENABLED = True
TRAILING_STOP_ATR_MULTIPLIER = 1.5  # Trailing stop at 1.5x ATR

# Calculate SL/TP levels
STOP_LOSS_PRICE = ENTRY_PRICE * (1 - STOP_LOSS_PCT / 100)
TAKE_PROFIT_PRICE = ENTRY_PRICE * (1 + TAKE_PROFIT_PCT / 100)

# Monitoring Configuration
CHECK_INTERVAL = 5  # Check every 5 seconds
ALERT_INTERVAL = 60  # Send status alert every 60 seconds

class PositionMonitor:
    def __init__(self):
        self.api_key = os.getenv("OPENALGO_APIKEY", "630db05e091812b4c23298ca2d018b62376ddd168860d21fcb4bd2dfc265e49f")
        self.client = APIClient(api_key=self.api_key, host="http://127.0.0.1:5001")
        self.entry_price = ENTRY_PRICE
        self.stop_loss = STOP_LOSS_PRICE
        self.take_profit = TAKE_PROFIT_PRICE
        self.position_active = True
        self.highest_price = ENTRY_PRICE  # Track highest price for trailing stop
        self.last_alert_time = datetime.now()
        self.ist = pytz.timezone('Asia/Kolkata')
        
        logger.info("=" * 60)
        logger.info("Silver Mini Position Monitor Started")
        logger.info("=" * 60)
        logger.info(f"Symbol: {SYMBOL}")
        logger.info(f"Position: {POSITION_SIDE} @ ₹{self.entry_price:,.2f}")
        logger.info(f"Stop Loss: ₹{self.stop_loss:,.2f} ({STOP_LOSS_PCT}%)")
        logger.info(f"Take Profit: ₹{self.take_profit:,.2f} ({TAKE_PROFIT_PCT}%)")
        logger.info(f"Risk/Reward: 1:{TAKE_PROFIT_PCT/STOP_LOSS_PCT:.2f}")
        logger.info(f"Check Interval: {CHECK_INTERVAL}s")
        logger.info("=" * 60)
    
    def get_current_price(self):
        """Get current market price"""
        try:
            end_date = datetime.now(self.ist)
            start_date = end_date - timedelta(days=1)
            
            df = self.client.history(
                symbol=SYMBOL,
                exchange=EXCHANGE,
                interval='1m',  # 1-minute for real-time monitoring
                start_date=start_date.strftime('%Y-%m-%d'),
                end_date=end_date.strftime('%Y-%m-%d')
            )
            
            if isinstance(df, pd.DataFrame) and not df.empty:
                return df.iloc[-1]['close'], df
            return None, None
        except Exception as e:
            logger.error(f"Error fetching price: {e}")
            return None, None
    
    def calculate_atr(self, df, period=14):
        """Calculate Average True Range"""
        try:
            high_low = df['high'] - df['low']
            high_close = abs(df['high'] - df['close'].shift())
            low_close = abs(df['low'] - df['close'].shift())
            true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr = true_range.rolling(period).mean().iloc[-1]
            return atr if not pd.isna(atr) else None
        except Exception as e:
            logger.debug(f"ATR calculation error: {e}")
            return None
    
    def update_trailing_stop(self, current_price, atr):
        """Update trailing stop loss"""
        if not TRAILING_STOP_ENABLED or atr is None:
            return
        
        # Update highest price
        if current_price > self.highest_price:
            self.highest_price = current_price
            # Update trailing stop: highest_price - (1.5 * ATR)
            new_trailing_stop = self.highest_price - (TRAILING_STOP_ATR_MULTIPLIER * atr)
            # Only move stop loss up, never down
            if new_trailing_stop > self.stop_loss:
                old_sl = self.stop_loss
                self.stop_loss = new_trailing_stop
                logger.info(f"📈 Trailing Stop Updated: ₹{old_sl:,.2f} → ₹{self.stop_loss:,.2f}")
                self.send_clawdbot_alert(f"Trailing stop updated: ₹{self.stop_loss:,.2f}")
    
    def check_exit_conditions(self, current_price):
        """Check if stop loss or take profit hit"""
        exit_reason = None
        exit_price = None
        
        # For BUY position:
        # - Stop Loss: price drops below stop_loss
        # - Take Profit: price rises above take_profit
        
        if current_price <= self.stop_loss:
            exit_reason = "STOP_LOSS"
            exit_price = self.stop_loss
        elif current_price >= self.take_profit:
            exit_reason = "TAKE_PROFIT"
            exit_price = self.take_profit
        
        return exit_reason, exit_price
    
    def exit_position(self, reason, exit_price):
        """Exit the position"""
        try:
            logger.warning("=" * 60)
            logger.warning(f"🚨 EXIT SIGNAL: {reason}")
            logger.warning("=" * 60)
            logger.warning(f"Entry: ₹{self.entry_price:,.2f}")
            logger.warning(f"Exit: ₹{exit_price:,.2f}")
            
            pnl = exit_price - self.entry_price
            pnl_pct = (pnl / self.entry_price) * 100
            
            logger.warning(f"P&L: ₹{pnl:,.2f} ({pnl_pct:+.2f}%)")
            logger.warning(f"Reason: {reason}")
            
            # Place exit order (SELL to exit BUY position)
            exit_action = "SELL"  # Sell to exit BUY
            logger.info(f"Placing exit order: {exit_action} {QUANTITY} {SYMBOL} @ MARKET")
            
            try:
                resp = self.client.placesmartorder(
                    strategy=f"Silver Mini Monitor - {reason}",
                    symbol=SYMBOL,
                    action=exit_action,
                    exchange=EXCHANGE,
                    price_type="MARKET",
                    product="MIS",
                    quantity=QUANTITY,
                    position_size=QUANTITY
                )
                
                if resp and (resp.get('status') == 'success' or resp.get('orderid')):
                    logger.info("=" * 60)
                    logger.info("✅ POSITION EXITED SUCCESSFULLY")
                    logger.info("=" * 60)
                    logger.info(f"Order ID: {resp.get('orderid', 'N/A')}")
                    logger.info(f"Entry: ₹{self.entry_price:,.2f}")
                    logger.info(f"Exit: ₹{exit_price:,.2f}")
                    logger.info(f"P&L: ₹{pnl:,.2f} ({pnl_pct:+.2f}%)")
                    logger.info(f"Reason: {reason}")
                    logger.info("=" * 60)
                    
                    # Send alert
                    alert_msg = f"✅ Silver Mini Position Exited\n"
                    alert_msg += f"Reason: {reason}\n"
                    alert_msg += f"Entry: ₹{self.entry_price:,.2f}\n"
                    alert_msg += f"Exit: ₹{exit_price:,.2f}\n"
                    alert_msg += f"P&L: ₹{pnl:,.2f} ({pnl_pct:+.2f}%)"
                    self.send_clawdbot_alert(alert_msg, priority="success")
                    
                    self.position_active = False
                    return True
                else:
                    logger.error(f"❌ Exit order failed: {resp}")
                    self.send_clawdbot_alert(f"⚠️ Exit order failed: {reason}", priority="error")
                    return False
                    
            except Exception as e:
                logger.error(f"❌ Error placing exit order: {e}")
                import traceback
                logger.error(traceback.format_exc())
                self.send_clawdbot_alert(f"❌ Exit order error: {str(e)}", priority="error")
                return False
                
        except Exception as e:
            logger.error(f"Error in exit_position: {e}")
            return False
    
    def send_clawdbot_alert(self, message, priority="info"):
        """Send alert via Clawdbot"""
        try:
            openai_key = os.getenv("OPENAI_API_KEY")
            if not openai_key:
                return False
            
            alert_message = f"[{priority.upper()}] Silver Mini Monitor: {message}"
            result = subprocess.run(
                ["clawdbot", "message", "--text", alert_message],
                capture_output=True,
                text=True,
                timeout=10,
                env=dict(os.environ, OPENAI_API_KEY=openai_key)
            )
            return result.returncode == 0
        except Exception as e:
            logger.debug(f"Alert error: {e}")
            return False
    
    def log_status(self, current_price, pnl, pnl_pct, distance_to_sl, distance_to_tp):
        """Log current position status"""
        logger.info("-" * 60)
        logger.info(f"📊 Position Status - {datetime.now(self.ist).strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"   Current Price: ₹{current_price:,.2f}")
        logger.info(f"   Entry Price: ₹{self.entry_price:,.2f}")
        logger.info(f"   P&L: ₹{pnl:,.2f} ({pnl_pct:+.2f}%)")
        logger.info(f"   Stop Loss: ₹{self.stop_loss:,.2f} ({distance_to_sl:.2f}% away)")
        logger.info(f"   Take Profit: ₹{self.take_profit:,.2f} ({distance_to_tp:.2f}% away)")
        logger.info(f"   Highest Price: ₹{self.highest_price:,.2f}")
        logger.info("-" * 60)
    
    def run(self):
        """Main monitoring loop"""
        logger.info("🚀 Starting position monitoring...")
        self.send_clawdbot_alert(f"Monitor started\nEntry: ₹{self.entry_price:,.2f}\nSL: ₹{self.stop_loss:,.2f}\nTP: ₹{self.take_profit:,.2f}")
        
        while self.position_active:
            try:
                # Get current price
                current_price, df = self.get_current_price()
                
                if current_price is None:
                    logger.warning("⚠️ Could not fetch current price, retrying...")
                    time.sleep(CHECK_INTERVAL)
                    continue
                
                # Calculate ATR for trailing stop
                atr = None
                if TRAILING_STOP_ENABLED and df is not None:
                    atr = self.calculate_atr(df)
                
                # Update trailing stop
                if TRAILING_STOP_ENABLED:
                    self.update_trailing_stop(current_price, atr)
                
                # Calculate P&L
                pnl = current_price - self.entry_price
                pnl_pct = (pnl / self.entry_price) * 100
                
                # Calculate distance to SL/TP
                distance_to_sl = ((current_price - self.stop_loss) / current_price) * 100
                distance_to_tp = ((self.take_profit - current_price) / current_price) * 100
                
                # Check exit conditions
                exit_reason, exit_price = self.check_exit_conditions(current_price)
                
                if exit_reason:
                    # Exit position
                    if self.exit_position(exit_reason, current_price):
                        logger.info("✅ Position exited. Monitor stopping.")
                        break
                    else:
                        logger.error("❌ Exit failed, continuing to monitor...")
                
                # Log status periodically
                if (datetime.now() - self.last_alert_time).total_seconds() >= ALERT_INTERVAL:
                    self.log_status(current_price, pnl, pnl_pct, distance_to_sl, distance_to_tp)
                    self.last_alert_time = datetime.now()
                
                # Wait before next check
                time.sleep(CHECK_INTERVAL)
                
            except KeyboardInterrupt:
                logger.info("🛑 Monitor stopped by user")
                self.send_clawdbot_alert("Monitor stopped manually", priority="warning")
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                import traceback
                logger.error(traceback.format_exc())
                time.sleep(CHECK_INTERVAL)
        
        logger.info("👋 Position monitor stopped")

if __name__ == "__main__":
    monitor = PositionMonitor()
    monitor.run()
