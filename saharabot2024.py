import os
import time
import math
import pandas as pd
from datetime import datetime
import MetaTrader5 as mt5

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
def calculate_A(M, fibM, S):
    return 60 / M * fibM * S

# Function to get the current minute in 60-minute format
def get_current_minute():
    return datetime.now().minute

# Function to get the spot price of the currency pair/instrument
def get_spot_price(symbol):
    tick = mt5.symbol_info_tick(symbol)
    if tick:
        return tick.last
    else:
        raise Exception(f"Failed to get tick for symbol: {symbol}")

# Function to calculate risk based on account balance
def calculate_risk(start_balance, trade_num):
    risk_percent = 0.05
    risk = start_balance * risk_percent
    reward_multipliers = [4, 2, 2, 2]
    reward = risk * reward_multipliers[trade_num % 4]
    return risk, reward

# Function to execute trades
def execute_trade(symbol, trade_type, volume, price, sl, tp):
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": trade_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 20,
        "magic": 234000,
        "comment": "Automated trade",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    return result

# Function to log trade data
def log_trade(trade_data):
    global trade_log_df
    trade_log_df = pd.concat([trade_log_df, pd.DataFrame([trade_data])], ignore_index=True)
    print(trade_log_df)  # Display the DataFrame
    trade_log_df.to_csv(file_path, index=False)

# Initialize variables
start_balance = mt5.account_info().balance
trade_num = 0
max_trades_per_day = 100
symbol = "USDJPYm"  # Hardcoded symbol
Startinglot = 0.1  # Hardcoded lot size

# Main trading loop
while True:
    try:
        current_minute = get_current_minute()

        if trade_num >= max_trades_per_day:
            print("Reached maximum trades for the day.")
            break
        
        if trade_num < max_trades_per_day:
            spot_price = get_spot_price(symbol)
            fibM = (current_minute - 1) + current_minute
            A = calculate_A(current_minute, fibM, spot_price)
            sin_A = math.sin(A)

            # Determine trade type based on signal direction
            trade_type = mt5.ORDER_TYPE_BUY if sin_A > 0 else mt5.ORDER_TYPE_SELL
            forecast = "Buy" if sin_A > 0 else "Sell"

            # Calculate risk and reward
            risk, reward = calculate_risk(start_balance, trade_num + 1)

            # Define SL and TP percentages
            sl_percent = 0.5  # Stop loss as a percentage of the current price
            tp_percent = 1.0  # Take profit as a percentage of the current price

            # Calculate SL and TP values
            sl = spot_price - sl_percent / 100 * spot_price if trade_type == mt5.ORDER_TYPE_BUY else spot_price + sl_percent / 100 * spot_price
            tp = spot_price + tp_percent / 100 * spot_price if trade_type == mt5.ORDER_TYPE_BUY else spot_price - tp_percent / 100 * spot_price

            # Execute trade
            result = execute_trade(symbol, trade_type, Startinglot, spot_price, sl, tp)
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

        # Sleep until the next 3 minutes
        time.sleep(180)

    except Exception as e:
        print(f"Error: {e}")
        break

# Shutdown MetaTrader 5
mt5.shutdown()
