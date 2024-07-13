import os
import time
import math
import pandas as pd
from datetime import datetime
import MetaTrader5 as mt5
import numpy as np

# Initialize MetaTrader 5
if not mt5.initialize():
    print("Failed to initialize MetaTrader 5")
    mt5.shutdown()
    exit()

# Specify the file path
file_path = os.path.join(os.path.expanduser("~"), "Desktop", "trade_log.csv")

# Initialize trade log DataFrame
if os.path.exists(file_path):
    trade_log_df = pd.read_csv(file_path)
else:
    trade_log_df = pd.DataFrame(columns=["SN", "Date", "Instrument", "P/L", "Net Balance", "Comment/ErrorLogs", "Forecast"])

# Function to calculate A
def calculate_A(H, fibH, S):
    return 24 / H * fibH * S

# Function to get the current hour in 24-hour format
def get_current_hour():
    return datetime.now().hour

# Function to get the spot price of the currency pair/instrument
def get_spot_price(symbol):
    tick = mt5.symbol_info_tick(symbol)
    if tick:
        return tick.last
    else:
        raise Exception(f"Failed to get tick for symbol: {symbol}")

# Function to execute trades
def execute_trade(symbol, trade_type, volume, price):
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": trade_type,
        "price": price,
        "deviation": 20,
        "magic": 234000,
        "comment": "Automated trade",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    if result is None:
        print("Failed to execute trade: order_send returned None")
        return None
    return result

# Function to log trade data
def log_trade(trade_data):
    global trade_log_df
    trade_log_df = pd.concat([trade_log_df, pd.DataFrame([trade_data])], ignore_index=True)
    print(trade_log_df)  # Display the DataFrame
    trade_log_df.to_csv(file_path, index=False)

# Function to calculate SMA
def calculate_sma(symbol, period=50):
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, period)
    if rates is None or len(rates) < period:
        return None
    close_prices = [rate['close'] for rate in rates]
    sma = np.mean(close_prices)
    return sma

# Initialize variables
start_balance = mt5.account_info().balance
trade_num = 0
max_trades_per_day = 100
symbol = "USDJPYm"  # Hardcoded symbol
Startinglot = 2.0  # Hardcoded lot size
previous_hour = get_current_hour()

# Main trading loop
while True:
    try:
        current_hour = get_current_hour()

        if trade_num >= max_trades_per_day:
            print("Reached maximum trades for the day.")
            break
        
        if trade_num < max_trades_per_day:
            spot_price = get_spot_price(symbol)
            fibH = current_hour - previous_hour  # Fibonacci sequence based on the current hour and previous hour
            A = calculate_A(current_hour, fibH, spot_price)
            sin_A = math.sin(A)

            sma_50 = calculate_sma(symbol, 50)

            if sma_50 is None:
                print("Not enough data to calculate SMA.")
                continue

            # Print debug information
            print(f"Current hour: {current_hour}")
            print(f"Previous hour: {previous_hour}")
            print(f"Fibonacci H (fibH): {fibH}")
            print(f"Spot price: {spot_price}")
            print(f"Sine(A): {sin_A}")
            print(f"SMA(50): {sma_50}")

            # Check if spot price is not zero
            if spot_price == 0.0:
                print("Spot price is zero. Skipping trade execution.")
                continue

            # Determine trade type based on SMA and sine(A)
            if spot_price > sma_50 and sin_A > 0:
                trade_type = mt5.ORDER_TYPE_BUY
                forecast = "Buy"
            elif spot_price < sma_50 and sin_A < 0:
                trade_type = mt5.ORDER_TYPE_SELL
                forecast = "Sell"
            else:
                print("Conditions not met for trade execution.")
                continue

            # Execute trade
            result = execute_trade(symbol, trade_type, Startinglot, spot_price)
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                print(f"Failed to execute trade: {result.comment}")
                log_trade({
                    "SN": trade_num + 1,
                    "Date": datetime.now(),
                    "Instrument": symbol,
                    "P/L": 0,
                    "Net Balance": start_balance,
                    "Comment/ErrorLogs": result.comment,
                    "Forecast": forecast
                })
            else:
                print(f"Trade executed successfully: {result}")

                trade_num += 1
                time.sleep(180)  # Wait for 3 minutes

                positions = mt5.positions_get(symbol=symbol)
                for position in positions:
                    close_request = {
                        "action": mt5.TRADE_ACTION_DEAL,
                        "symbol": position.symbol,
                        "volume": position.volume,
                        "type": mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY,
                        "position": position.ticket,
                        "price": spot_price,
                        "deviation": 20,
                        "magic": 234000,
                        "comment": "Closing position",
                        "type_time": mt5.ORDER_TIME_GTC,
                        "type_filling": mt5.ORDER_FILLING_IOC,
                    }
                    close_result = mt5.order_send(close_request)
                    if close_result.retcode != mt5.TRADE_RETCODE_DONE:
                        print(f"Failed to close position: {close_result.comment}")

                balance_after_trade = mt5.account_info().balance
                pl = balance_after_trade - start_balance
                print(f"Trade {trade_num}: P/L = {pl}, Net Balance = {balance_after_trade}")
                log_trade({
                    "SN": trade_num,
                    "Date": datetime.now(),
                    "Instrument": symbol,
                    "P/L": pl,
                    "Net Balance": balance_after_trade,
                    "Comment/ErrorLogs": "Trade executed and closed successfully",
                    "Forecast": forecast
                })
                start_balance = balance_after_trade

        # Update previous hour
        previous_hour = current_hour

        # Sleep until the next 8 seconds
        time.sleep(8)

    except Exception as e:
        print(f"Error: {e}")
        break

# Shutdown MetaTrader 5
mt5.shutdown()
