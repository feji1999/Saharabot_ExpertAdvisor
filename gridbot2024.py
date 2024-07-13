import MetaTrader5 as mt5
import time
import pandas as pd
import os

# Symbol to trade
symbol = "USDJPYm"

# Initialize the DataFrame for logging
columns = ['timestamp', 'order_type', 'volume', 'price', 'sl', 'tp', 'result']
trade_log_df = pd.DataFrame(columns=columns)

# Connect to MetaTrader 5
if not mt5.initialize():
    print("Failed to initialize, error code =", mt5.last_error())
    quit()

# Get the current price
def get_current_price(symbol):
    ticker = mt5.symbol_info_tick(symbol)
    if ticker is None:
        raise Exception(f"Failed to get ticker for {symbol}")
    return ticker.bid, ticker.ask

# Function to log buy/sell order details
def log_trade(order_type, volume, price, sl, tp, result):
    global trade_log_df
    print(f"Logging trade: {order_type}, {volume}, {price}, {sl}, {tp}, {result.retcode if result else 'failed'}")
    
    new_trade = pd.DataFrame([{
        'timestamp': pd.Timestamp.now(),
        'order_type': order_type,
        'volume': volume,
        'price': price,
        'sl': sl,
        'tp': tp,
        'result': result.retcode if result else 'failed'
    }])
    
    print(f"New trade DataFrame:\n{new_trade}")
    
    if not new_trade.isna().all().all():
        trade_log_df = pd.concat([trade_log_df, new_trade], ignore_index=True)
        print(f"Updated trade_log_df:\n{trade_log_df}")

# Function to save DataFrame into CSV file locally
def save_log_to_csv():
    desktop = os.path.join(os.path.join(os.environ['USERPROFILE']), 'Desktop')
    filepath = os.path.join(desktop, 'gridbotlog.csv')
    trade_log_df.to_csv(filepath, index=False)

# Place an order with correct price precision
def place_order(symbol, order_type, volume, price, sl, tp):
    # Ensure the price has the correct precision
    price = round(price, 3)  # For JPY pairs, using 3 decimal places
    sl = round(sl, 3)
    tp = round(tp, 3)

    request = {
        "action": mt5.TRADE_ACTION_PENDING,
        "symbol": symbol,
        "volume": volume,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 10,
        "magic": 234000,
        "comment": "Grid strategy",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_RETURN,
    }
    
    result = mt5.order_send(request)
    
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"Failed to send order: {result}")
        log_trade(order_type, volume, price, sl, tp, result)
        return None
    else:
        print(f"Order sent successfully: {result}")
        log_trade(order_type, volume, price, sl, tp, result)
    
    return result

# Update trailing stop loss for open positions
def update_trailing_stop(symbol, trailing_stop_distance):
    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        print(f"No positions found for {symbol}, error code:", mt5.last_error())
        return
    
    for position in positions:
        if position.type == mt5.ORDER_TYPE_BUY:
            new_sl = mt5.symbol_info_tick(symbol).bid - trailing_stop_distance
            if new_sl > position.sl:
                modify_order(position.ticket, new_sl, position.tp)
        elif position.type == mt5.ORDER_TYPE_SELL:
            new_sl = mt5.symbol_info_tick(symbol).ask + trailing_stop_distance
            if new_sl < position.sl:
                modify_order(position.ticket, new_sl, position.tp)

# Modify an existing order's stop loss and take profit
def modify_order(position_ticket, new_sl, new_tp):
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": position_ticket,
        "sl": new_sl,
        "tp": new_tp,
        "deviation": 10,
    }
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"Failed to modify order: {result}")
        return None
    return result

# Grid strategy
def grid_strategy(symbol):
    volume = 0.05  # Define your volume/lotsize, adjust as necessary
    pips = 0.05  # pip distance, adjust as necessary

    bid, ask = get_current_price(symbol)
    current_price = (bid + ask) / 2

    # Define sell stops
    last_sell_tp = None
    for i in range(1, 4):
        price = current_price - i * pips
        tp = price - 4 * pips  # Take profit 4 levels away
        sl = price + 2 * pips  # Stop loss half of take profit
        last_sell_tp = tp  # Save the TP level of the last sell stop
        result = place_order(symbol, mt5.ORDER_TYPE_SELL_STOP, volume, price, sl, tp)
        if result is None:
            print(f"Invalid price for sell stop at {price}. Retrying with adjusted price.")
            # Adjust the price slightly and retry
            price = round(current_price - (i * pips * 1.01), 3)
            result = place_order(symbol, mt5.ORDER_TYPE_SELL_STOP, volume, price, sl, tp)
            if result is None:
                print(f"Failed to place adjusted sell stop order at {price}")
                continue

    # Place buy limit at the position of the last sell stop's TP level
    if last_sell_tp is not None:
        buy_limit_price = last_sell_tp
        buy_limit_tp = buy_limit_price + 4 * pips
        buy_limit_sl = buy_limit_price - 2 * pips
        result = place_order(symbol, mt5.ORDER_TYPE_BUY_LIMIT, volume, buy_limit_price, buy_limit_sl, buy_limit_tp)
        if result is None:
            print(f"Invalid price for buy limit at {buy_limit_price}. Retrying with adjusted price.")
            # Adjust the price slightly and retry
            buy_limit_price = round(last_sell_tp * 1.01, 3)
            result = place_order(symbol, mt5.ORDER_TYPE_BUY_LIMIT, volume, buy_limit_price, buy_limit_sl, buy_limit_tp)
            if result is None:
                print(f"Failed to place adjusted buy limit order at {buy_limit_price}")

    # Define buy stops
    last_buy_tp = None
    for i in range(1, 4):
        price = current_price + i * pips
        tp = price + 4 * pips  # Take profit 4 levels away
        sl = price - 2 * pips  # Stop loss half of take profit
        last_buy_tp = tp  # Save the TP level of the last buy stop
        result = place_order(symbol, mt5.ORDER_TYPE_BUY_STOP, volume, price, sl, tp)
        if result is None:
            print(f"Invalid price for buy stop at {price}. Retrying with adjusted price.")
            # Adjust the price slightly and retry
            price = round(current_price + (i * pips * 1.01), 3)
            result = place_order(symbol, mt5.ORDER_TYPE_BUY_STOP, volume, price, sl, tp)
            if result is None:
                print(f"Failed to place adjusted buy stop order at {price}")
                continue

    # Place sell limit at the position of the last buy stop's TP level
    if last_buy_tp is not None:
        sell_limit_price = last_buy_tp
        sell_limit_tp = sell_limit_price - 4 * pips
        sell_limit_sl = sell_limit_price + 2 * pips
        result = place_order(symbol, mt5.ORDER_TYPE_SELL_LIMIT, volume, sell_limit_price, sell_limit_sl, sell_limit_tp)
        if result is None:
            print(f"Invalid price for sell limit at {sell_limit_price}. Retrying with adjusted price.")
            # Adjust the price slightly and retry
            sell_limit_price = round(last_buy_tp * 1.01, 3)
            result = place_order(symbol, mt5.ORDER_TYPE_SELL_LIMIT, volume, sell_limit_price, sell_limit_sl, sell_limit_tp)
            if result is None:
                print(f"Failed to place adjusted sell limit order at {sell_limit_price}")

# Check if all pending orders have been executed
def all_orders_executed():
    orders = mt5.orders_get(symbol=symbol)
    return orders is None or len(orders) == 0

# Main loop
while True:
    # Run the grid strategy
    grid_strategy(symbol)
    
    # Wait for 1 hour and check if all orders have been executed before placing new ones
    time.sleep(3600)
    
    # If there are still pending orders, wait until the next iteration
    if not all_orders_executed():
        continue

    # Update trailing stop loss for open positions
    trailing_stop_distance = 2 * 0.1  # Example trailing stop distance, adjust as needed
    update_trailing_stop(symbol, trailing_stop_distance)

    # Save to CSV file function call
    save_log_to_csv()

# Disconnect from MetaTrader 5
mt5.shutdown()
