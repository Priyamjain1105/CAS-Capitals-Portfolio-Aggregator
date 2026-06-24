import re
import uuid
from datetime import datetime, date

def parse_symbol(symbol, segment=None):
    """
    Parse Zerodha symbol structure into instrument type, strike price, and expiry representation.
    Returns a dict with: underlying_symbol, instrument_type, strike_price, expiry_date
    """
    if not symbol:
        return {
            'underlying_symbol': '',
            'instrument_type': 'EQ',
            'strike_price': None,
            'expiry_date': None
        }

    symbol = str(symbol).strip().upper()
    
    # Equity segment
    if segment == 'EQ':
        return {
            'underlying_symbol': symbol,
            'instrument_type': 'EQ',
            'strike_price': None,
            'expiry_date': None
        }
    
    # Futures (e.g. NIFTY25JNFUT)
    if 'FUT' in symbol:
        underlying = re.sub(r'\d+[A-Z]+FUT$', '', symbol)
        return {
            'underlying_symbol': underlying,
            'instrument_type': 'FUT',
            'strike_price': None,
            'expiry_date': None
        }
    
    # Options with numeric expiry date (e.g., NIFTY2560524750PE, where expiry is 2025-06-05)
    numeric_match = re.match(r"^([A-Z&\-\d]+)(\d{5})(\d+(?:\.\d+)?)(CE|PE)$", symbol)
    if numeric_match:
        underlying, date_str, strike, opt_type = numeric_match.groups()
        return {
            'underlying_symbol': underlying,
            'instrument_type': opt_type,
            'strike_price': float(strike),
            'expiry_date': date_str
        }
        
    # Options with alphanumeric expiry date (e.g., BANKNIFTY25APR51200PE)
    alpha_match = re.match(r"^([A-Z&\-\d]+)(\d{2}[A-Z]{3})(\d+(?:\.\d+)?)(CE|PE)$", symbol)
    if alpha_match:
        underlying, date_str, strike, opt_type = alpha_match.groups()
        return {
            'underlying_symbol': underlying,
            'instrument_type': opt_type,
            'strike_price': float(strike),
            'expiry_date': date_str
        }
    
    # Fallback option check
    if symbol.endswith('CE') or symbol.endswith('PE'):
        opt_type = symbol[-2:]
        underlying = re.sub(r'\d+[CP]E$', '', symbol)
        return {
            'underlying_symbol': underlying,
            'instrument_type': opt_type,
            'strike_price': None,
            'expiry_date': None
        }
        
    # Fallback default
    return {
        'underlying_symbol': symbol,
        'instrument_type': 'EQ' if segment == 'EQ' else 'FUT',
        'strike_price': None,
        'expiry_date': None
    }

def calculate_positions(trades):
    """
    Take a list of trade dictionaries sorted chronologically and resolve them into positions using FIFO.
    Each trade in trades has keys: symbol, segment, trade_date, trade_type, quantity, price, value,
    order_id, order_execution_time, expiry_date, exchange.
    
    Returns a list of Position dictionaries.
    """
    # Sort trades chronologically
    sorted_trades = sorted(trades, key=lambda t: t['order_execution_time'])
    
    positions = []
    # Map of key -> open positions for that instrument
    open_positions = {}
    
    for trade in sorted_trades:
        symbol = trade['symbol']
        segment = trade['segment']
        expiry_date = trade['expiry_date']
        
        symbol_info = parse_symbol(symbol, segment)
        inst_type = symbol_info['instrument_type']
        strike_price = symbol_info['strike_price']
        
        # Structure a unique key for tracking open positions of the same contract
        expiry_str = expiry_date.strftime('%Y-%m-%d') if isinstance(expiry_date, (date, datetime)) else str(expiry_date or 'None')
        inst_key = f"{symbol}_{inst_type}_{strike_price or 0.0}_{expiry_str}"
        
        if inst_key not in open_positions:
            open_positions[inst_key] = []
            
        trade_type = trade['trade_type'].lower()
        quantity = float(trade['quantity'])
        price = float(trade['price'])
        value = float(trade['value'])
        exec_time = trade['order_execution_time']
        
        if trade_type == 'buy':
            # Match against open SHORT positions (position_type = short & remaining_quantity > 0)
            short_positions = [p for p in open_positions[inst_key] if p['position_type'] == 'short' and p['remaining_quantity'] > 0]
            remaining_qty = quantity
            
            for pos in short_positions:
                if remaining_qty <= 0:
                    break
                qty_to_close = min(pos['remaining_quantity'], remaining_qty)
                
                # Add trade reference to position
                pos['trades'].append(trade)
                pos['total_buy_value'] += (qty_to_close / quantity) * value
                pos['remaining_quantity'] -= qty_to_close
                
                # PnL for short position = Entry Price (Sell) - Exit Price (Buy)
                realized_pnl = qty_to_close * (pos['entry_price'] - price)
                pos['realized_pnl'] += realized_pnl
                
                if pos['remaining_quantity'] == 0:
                    pos['status'] = 'closed'
                    pos['close_time'] = exec_time
                    pos['exit_price'] = price
                    pos['net_quantity'] = 0.0
                    pos['avg_buy_price'] = pos['total_buy_value'] / pos['max_quantity']
                else:
                    pos['net_quantity'] = -pos['remaining_quantity']
                    
                remaining_qty -= qty_to_close
                
            if remaining_qty > 0:
                # Open a new LONG position
                new_pos = {
                    'position_id': f"{inst_key}_{int(exec_time.timestamp()*1000)}_{uuid.uuid4().hex[:6]}",
                    'symbol': symbol,
                    'instrument_type': inst_type,
                    'strike_price': strike_price,
                    'expiry_date': expiry_date,
                    'net_quantity': remaining_qty,
                    'avg_buy_price': price,
                    'avg_sell_price': 0.0,
                    'total_buy_value': (remaining_qty / quantity) * value,
                    'total_sell_value': 0.0,
                    'realized_pnl': 0.0,
                    'unrealized_pnl': 0.0,
                    'status': 'open',
                    'trades': [trade],
                    'open_time': exec_time,
                    'close_time': None,
                    'entry_price': price,
                    'exit_price': None,
                    'max_quantity': remaining_qty,
                    'remaining_quantity': remaining_qty,
                    'position_type': 'long'
                }
                open_positions[inst_key].append(new_pos)
                positions.append(new_pos)
                
        elif trade_type == 'sell':
            # Match against open LONG positions (position_type = long & remaining_quantity > 0)
            long_positions = [p for p in open_positions[inst_key] if p['position_type'] == 'long' and p['remaining_quantity'] > 0]
            remaining_qty = quantity
            
            for pos in long_positions:
                if remaining_qty <= 0:
                    break
                qty_to_close = min(pos['remaining_quantity'], remaining_qty)
                
                pos['trades'].append(trade)
                pos['total_sell_value'] += (qty_to_close / quantity) * value
                pos['remaining_quantity'] -= qty_to_close
                
                # PnL for long position = Exit Price (Sell) - Entry Price (Buy)
                realized_pnl = qty_to_close * (price - pos['entry_price'])
                pos['realized_pnl'] += realized_pnl
                
                if pos['remaining_quantity'] == 0:
                    pos['status'] = 'closed'
                    pos['close_time'] = exec_time
                    pos['exit_price'] = price
                    pos['net_quantity'] = 0.0
                    pos['avg_sell_price'] = pos['total_sell_value'] / pos['max_quantity']
                else:
                    pos['net_quantity'] = pos['remaining_quantity']
                    
                remaining_qty -= qty_to_close
                
            if remaining_qty > 0:
                # Open a new SHORT position
                new_pos = {
                    'position_id': f"{inst_key}_{int(exec_time.timestamp()*1000)}_{uuid.uuid4().hex[:6]}",
                    'symbol': symbol,
                    'instrument_type': inst_type,
                    'strike_price': strike_price,
                    'expiry_date': expiry_date,
                    'net_quantity': -remaining_qty,
                    'avg_buy_price': 0.0,
                    'avg_sell_price': price,
                    'total_buy_value': 0.0,
                    'total_sell_value': (remaining_qty / quantity) * value,
                    'realized_pnl': 0.0,
                    'unrealized_pnl': 0.0,
                    'status': 'open',
                    'trades': [trade],
                    'open_time': exec_time,
                    'close_time': None,
                    'entry_price': price,
                    'exit_price': None,
                    'max_quantity': remaining_qty,
                    'remaining_quantity': remaining_qty,
                    'position_type': 'short'
                }
                open_positions[inst_key].append(new_pos)
                positions.append(new_pos)
                
        # Update the open_positions tracker to keep only active items
        open_positions[inst_key] = [p for p in open_positions[inst_key] if p['remaining_quantity'] > 0]
        
    return positions

def calculate_brokerage_charges(position, exchange='NSE'):
    """
    Calculate Indian brokerage taxes and charges (Zerodha format) for the trades in a position.
    """
    inst_type = position['instrument_type']
    trades = position['trades']
    
    is_intraday = True
    if position['open_time'] and position['close_time']:
        is_intraday = position['open_time'].date() == position['close_time'].date()
        
    # Group trades by order_id to apply per-order brokerage cap
    order_map = {}
    for t in trades:
        oid = t['order_id']
        if oid not in order_map:
            order_map[oid] = []
        order_map[oid].append(t)
        
    total_brokerage = 0.0
    total_stt = 0.0
    total_transaction_charges = 0.0
    total_sebi_charges = 0.0
    total_stamp_charges = 0.0
    total_ipft_charges = 0.0
    total_gst = 0.0
    
    for oid, o_trades in order_map.items():
        buy_value = sum(float(t['value']) for t in o_trades if t['trade_type'].lower() == 'buy')
        sell_value = sum(float(t['value']) for t in o_trades if t['trade_type'].lower() == 'sell')
        total_val = buy_value + sell_value
        
        # 1. Brokerage (Rs 20 flat for options; Min of 0.03% or Rs 20 for FUT/EQ Intraday)
        brokerage = 0.0
        if inst_type in ['CE', 'PE']:
            brokerage = 20.0
        elif inst_type == 'FUT':
            brokerage = min(total_val * 0.0003, 20.0)
        elif inst_type == 'EQ':
            if is_intraday:
                brokerage = min(total_val * 0.0003, 20.0)
            else:
                brokerage = 0.0 # Free equity delivery brokerage
                
        # 2. STT/CTT
        stt = 0.0
        if inst_type == 'FUT':
            stt = sell_value * 0.0002 # 0.02% on sell side
        elif inst_type in ['CE', 'PE']:
            stt = sell_value * 0.001 # 0.1% on sell premium
        elif inst_type == 'EQ':
            if is_intraday:
                stt = sell_value * 0.00025 # 0.025% on sell side
            else:
                stt = total_val * 0.001 # 0.1% on both sides
                
        # 3. Transaction charges
        txn = 0.0
        if inst_type == 'FUT':
            txn = total_val * 0.0000173 if exchange == 'NSE' else 0.0
        elif inst_type in ['CE', 'PE']:
            txn = total_val * 0.0003503 if exchange == 'NSE' else total_val * 0.000325
        elif inst_type == 'EQ':
            txn = total_val * 0.0000297 if exchange == 'NSE' else total_val * 0.0000375
            
        # 4. SEBI charges (₹10 per crore)
        sebi = (total_val / 10000000.0) * 10.0
        
        # 5. IPFT charges (NSE only)
        ipft = 0.0
        if exchange == 'NSE':
            if inst_type in ['FUT', 'EQ']:
                ipft = (total_val / 10000000.0) * 10.0 * 1.18
            elif inst_type in ['CE', 'PE']:
                ipft = (total_val / 10000000.0) * 50.0 * 1.18
                
        # 6. Stamp charges (on buy side only)
        stamp = 0.0
        if buy_value > 0:
            if inst_type == 'FUT':
                stamp = min(buy_value * 0.00002, (buy_value / 10000000.0) * 200.0)
            elif inst_type in ['CE', 'PE']:
                stamp = min(buy_value * 0.00003, (buy_value / 10000000.0) * 300.0)
            elif inst_type == 'EQ':
                if is_intraday:
                    stamp = min(buy_value * 0.00003, (buy_value / 10000000.0) * 300.0)
                else:
                    stamp = min(buy_value * 0.00015, (buy_value / 10000000.0) * 1500.0)
                    
        # 7. GST: 18% on (brokerage + sebi + transaction charges)
        gst = (brokerage + sebi + txn) * 0.18
        
        total_brokerage += brokerage
        total_stt += stt
        total_transaction_charges += txn
        total_sebi_charges += sebi
        total_stamp_charges += stamp
        total_ipft_charges += ipft
        total_gst += gst
        
    total_charges = (total_brokerage + total_stt + total_transaction_charges + 
                     total_sebi_charges + total_stamp_charges + total_ipft_charges + total_gst)
                     
    return {
        'brokerage': total_brokerage,
        'stt': total_stt,
        'transaction_charges': total_transaction_charges,
        'sebi_charges': total_sebi_charges,
        'stamp_charges': total_stamp_charges,
        'ipft_charges': total_ipft_charges,
        'gst': total_gst,
        'total_charges': total_charges
    }

def calculate_all_metrics(trades):
    """
    Main entry point for computing trade metrics. Returns dictionary:
    total_trades, winning_trades, losing_trades, win_rate, total_pnl, gross_turnover,
    total_brokerage, net_pnl, max_drawdown, positions, daily_pnl.
    """
    if not trades:
        return {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0.0,
            'total_pnl': 0.0,
            'avg_win': 0.0,
            'avg_loss': 0.0,
            'max_win': 0.0,
            'max_loss': 0.0,
            'profit_factor': 0.0,
            'gross_turnover': 0.0,
            'total_brokerage': 0.0,
            'net_pnl': 0.0,
            'max_drawdown': 0.0,
            'positions': [],
            'daily_pnl': []
        }
        
    positions = calculate_positions(trades)
    closed_positions = [p for p in positions if p['status'] == 'closed']
    
    winning_positions = [p for p in closed_positions if p['realized_pnl'] > 0]
    losing_positions = [p for p in closed_positions if p['realized_pnl'] < 0]
    
    total_pnl = sum(p['realized_pnl'] for p in closed_positions)
    gross_turnover = sum(p['total_buy_value'] + p['total_sell_value'] for p in closed_positions)
    
    total_brokerage = 0.0
    for p in closed_positions:
        exch = p['trades'][0].get('exchange', 'NSE') if p['trades'] else 'NSE'
        charges = calculate_brokerage_charges(p, exch)
        total_brokerage += charges['total_charges']
        
    avg_win = sum(p['realized_pnl'] for p in winning_positions) / len(winning_positions) if winning_positions else 0.0
    avg_loss = sum(p['realized_pnl'] for p in losing_positions) / len(losing_positions) if losing_positions else 0.0
    
    max_win = max([p['realized_pnl'] for p in winning_positions]) if winning_positions else 0.0
    max_loss = min([p['realized_pnl'] for p in losing_positions]) if losing_positions else 0.0
    
    total_wins = sum(p['realized_pnl'] for p in winning_positions)
    total_losses = abs(sum(p['realized_pnl'] for p in losing_positions))
    
    if total_losses > 0:
        profit_factor = total_wins / total_losses
    else:
        profit_factor = 999.0 if total_wins > 0 else 0.0
        
    win_rate = (len(winning_positions) / len(closed_positions)) * 100 if closed_positions else 0.0
    
    # Calculate daily P&L curve
    daily_map = {}
    for p in closed_positions:
        if p['realized_pnl'] == 0:
            continue
            
        # Get unique date list sorted
        trading_dates = []
        for t in p['trades']:
            dt = t['trade_date']
            if isinstance(dt, datetime):
                dt = dt.date()
            if dt not in trading_dates:
                trading_dates.append(dt)
        trading_dates = sorted(trading_dates)
        
        if not trading_dates:
            continue
            
        charges = calculate_brokerage_charges(p, p['trades'][0].get('exchange', 'NSE') if p['trades'] else 'NSE')
        tot_charges = charges['total_charges']
        
        if len(trading_dates) == 1:
            dt = trading_dates[0]
            if dt not in daily_map:
                daily_map[dt] = {'realized_pnl': 0.0, 'brokerage': 0.0}
            daily_map[dt]['realized_pnl'] += p['realized_pnl']
            daily_map[dt]['brokerage'] += tot_charges
        else:
            # Distribute realized P&L and charges evenly across active days (helps with daily statistics)
            pnl_per_day = p['realized_pnl'] / len(trading_dates)
            charges_per_day = tot_charges / len(trading_dates)
            for dt in trading_dates:
                if dt not in daily_map:
                    daily_map[dt] = {'realized_pnl': 0.0, 'brokerage': 0.0}
                daily_map[dt]['realized_pnl'] += pnl_per_day
                daily_map[dt]['brokerage'] += charges_per_day
                
    daily_list = []
    for dt, vals in daily_map.items():
        net_val = vals['realized_pnl'] - vals['brokerage']
        daily_list.append({
            'date': dt,
            'realized_pnl': vals['realized_pnl'],
            'brokerage': vals['brokerage'],
            'net_pnl': net_val
        })
        
    daily_list = sorted(daily_list, key=lambda x: x['date'])
    
    # Maximum Drawdown calculation (peak-to-trough of cumulative returns)
    max_drawdown = 0.0
    if daily_list:
        cum_pnl = 0.0
        peak = 0.0
        for d in daily_list:
            cum_pnl += d['net_pnl']
            if cum_pnl > peak:
                peak = cum_pnl
            drawdown = peak - cum_pnl
            if drawdown > max_drawdown:
                max_drawdown = drawdown
                
    return {
        'total_trades': len(trades),
        'winning_trades': len(winning_positions),
        'losing_trades': len(losing_positions),
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'max_win': max_win,
        'max_loss': max_loss,
        'profit_factor': profit_factor,
        'gross_turnover': gross_turnover,
        'total_brokerage': total_brokerage,
        'net_pnl': total_pnl - total_brokerage,
        'max_drawdown': max_drawdown,
        'positions': positions,
        'daily_pnl': daily_list
    }
