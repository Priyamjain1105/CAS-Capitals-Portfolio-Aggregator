function parseSymbol(symbol, segment) {
    if (!symbol) {
        return {
            underlyingSymbol: '',
            instrumentType: 'EQ',
            strikePrice: null,
            expiryDate: null
        };
    }
    symbol = String(symbol).trim().toUpperCase();
    if (segment === 'EQ') {
        return {
            underlyingSymbol: symbol,
            instrumentType: 'EQ',
            strikePrice: null,
            expiryDate: null
        };
    }
    if (symbol.includes('FUT')) {
        const underlying = symbol.replace(/\d+[A-Z]+FUT$/, '');
        return {
            underlyingSymbol: underlying,
            instrumentType: 'FUT',
            strikePrice: null,
            expiryDate: null
        };
    }
    
    // Options numeric match (e.g. NIFTY2560524750PE)
    const numericMatch = symbol.match(/^([A-Z&\-\d]+)(\d{5})(\d+(?:\.\d+)?)(CE|PE)$/);
    if (numericMatch) {
        const [, underlying, dateStr, strike, optType] = numericMatch;
        return {
            underlyingSymbol: underlying,
            instrumentType: optType,
            strikePrice: parseFloat(strike),
            expiryDate: dateStr
        };
    }
    
    // Options alpha match (e.g. BANKNIFTY25APR51200PE)
    const alphaMatch = symbol.match(/^([A-Z&\-\d]+)(\d{2}[A-Z]{3})(\d+(?:\.\d+)?)(CE|PE)$/);
    if (alphaMatch) {
        const [, underlying, dateStr, strike, optType] = alphaMatch;
        return {
            underlyingSymbol: underlying,
            instrumentType: optType,
            strikePrice: parseFloat(strike),
            expiryDate: dateStr
        };
    }
    
    if (symbol.endsWith('CE') || symbol.endsWith('PE')) {
        const optType = symbol.slice(-2);
        const underlying = symbol.replace(/\d+[CP]E$/, '');
        return {
            underlyingSymbol: underlying,
            instrumentType: optType,
            strikePrice: null,
            expiryDate: null
        };
    }
    return {
        underlyingSymbol: symbol,
        instrumentType: segment === 'EQ' ? 'EQ' : 'FUT',
        strikePrice: null,
        expiryDate: null
    };
}

function calculatePositions(trades) {
    // Sort trades chronologically by execution time
    const sortedTrades = [...trades].sort((a, b) => new Date(a.order_execution_time) - new Date(b.order_execution_time));
    const positions = [];
    const openPositions = {}; // key -> array of open positions
    
    for (let trade of sortedTrades) {
        const symbol = trade.symbol;
        const segment = trade.segment;
        const expiryDate = trade.expiry_date;
        
        const symbolInfo = parseSymbol(symbol, segment);
        const instType = symbolInfo.instrumentType;
        const strikePrice = symbolInfo.strikePrice;
        const expiryStr = expiryDate ? String(expiryDate).split(' ')[0] : 'None';
        const instKey = `${symbol}_${instType}_${strikePrice || 0.0}_${expiryStr}`;
        
        if (!openPositions[instKey]) {
            openPositions[instKey] = [];
        }
        
        const tradeType = trade.trade_type.toLowerCase();
        const quantity = parseFloat(trade.quantity);
        const price = parseFloat(trade.price);
        const value = quantity * price;
        const execTime = new Date(trade.order_execution_time);
        
        if (tradeType === 'buy') {
            const shortPositions = openPositions[instKey].filter(p => p.position_type === 'short' && p.remaining_quantity > 0);
            let remainingQty = quantity;
            
            for (let pos of shortPositions) {
                if (remainingQty <= 0) break;
                const qtyToClose = Math.min(pos.remaining_quantity, remainingQty);
                
                pos.trades.push(trade);
                pos.total_buy_value += (qtyToClose / quantity) * value;
                pos.remaining_quantity -= qtyToClose;
                
                // P&L for short: Sell Price (Entry) - Buy Price (Exit)
                const realizedPnL = qtyToClose * (pos.entry_price - price);
                pos.realized_pnl += realizedPnL;
                
                if (pos.remaining_quantity === 0) {
                    pos.status = 'closed';
                    pos.close_time = execTime;
                    pos.exit_price = price;
                    pos.net_quantity = 0.0;
                    pos.avg_buy_price = pos.total_buy_value / pos.max_quantity;
                } else {
                    pos.net_quantity = -pos.remaining_quantity;
                }
                
                remainingQty -= qtyToClose;
            }
            
            if (remainingQty > 0) {
                const newPos = {
                    position_id: `${instKey}_${execTime.getTime()}_${Math.random().toString(36).substring(2, 8)}`,
                    symbol: symbol,
                    instrument_type: instType,
                    strike_price: strikePrice,
                    expiry_date: expiryDate,
                    net_quantity: remainingQty,
                    avg_buy_price: price,
                    avg_sell_price: 0.0,
                    total_buy_value: (remainingQty / quantity) * value,
                    total_sell_value: 0.0,
                    realized_pnl: 0.0,
                    unrealized_pnl: 0.0,
                    status: 'open',
                    trades: [trade],
                    open_time: execTime,
                    close_time: null,
                    entry_price: price,
                    exit_price: null,
                    max_quantity: remainingQty,
                    remaining_quantity: remainingQty,
                    position_type: 'long'
                };
                openPositions[instKey].push(newPos);
                positions.push(newPos);
            }
            
        } else if (tradeType === 'sell') {
            const longPositions = openPositions[instKey].filter(p => p.position_type === 'long' && p.remaining_quantity > 0);
            let remainingQty = quantity;
            
            for (let pos of longPositions) {
                if (remainingQty <= 0) break;
                const qtyToClose = Math.min(pos.remaining_quantity, remainingQty);
                
                pos.trades.push(trade);
                pos.total_sell_value += (qtyToClose / quantity) * value;
                pos.remaining_quantity -= qtyToClose;
                
                // P&L for long: Exit Price (Sell) - Entry Price (Buy)
                const realizedPnL = qtyToClose * (price - pos.entry_price);
                pos.realized_pnl += realizedPnL;
                
                if (pos.remaining_quantity === 0) {
                    pos.status = 'closed';
                    pos.close_time = execTime;
                    pos.exit_price = price;
                    pos.net_quantity = 0.0;
                    pos.avg_sell_price = pos.total_sell_value / pos.max_quantity;
                } else {
                    pos.net_quantity = pos.remaining_quantity;
                }
                
                remainingQty -= qtyToClose;
            }
            
            if (remainingQty > 0) {
                const newPos = {
                    position_id: `${instKey}_${execTime.getTime()}_${Math.random().toString(36).substring(2, 8)}`,
                    symbol: symbol,
                    instrument_type: instType,
                    strike_price: strikePrice,
                    expiry_date: expiryDate,
                    net_quantity: -remainingQty,
                    avg_buy_price: 0.0,
                    avg_sell_price: price,
                    total_buy_value: 0.0,
                    total_sell_value: (remainingQty / quantity) * value,
                    realized_pnl: 0.0,
                    unrealized_pnl: 0.0,
                    status: 'open',
                    trades: [trade],
                    open_time: execTime,
                    close_time: null,
                    entry_price: price,
                    exit_price: null,
                    max_quantity: remainingQty,
                    remaining_quantity: remainingQty,
                    position_type: 'short'
                };
                openPositions[instKey].push(newPos);
                positions.push(newPos);
            }
        }
        
        // Filter live lookup
        openPositions[instKey] = openPositions[instKey].filter(p => p.remaining_quantity > 0);
    }
    
    return positions;
}

function calculateBrokerageCharges(position, exchange = 'NSE') {
    const instType = position.instrument_type;
    const trades = position.trades;
    
    let isIntraday = true;
    if (position.open_time && position.close_time) {
        const oDate = new Date(position.open_time).toDateString();
        const cDate = new Date(position.close_time).toDateString();
        isIntraday = oDate === cDate;
    }
    
    const orderMap = {};
    for (let t of trades) {
        const oid = t.order_id;
        if (!orderMap[oid]) orderMap[oid] = [];
        orderMap[oid].push(t);
    }
    
    let totalBrokerage = 0.0;
    let totalStt = 0.0;
    let totalTxn = 0.0;
    let totalSebi = 0.0;
    let totalStamp = 0.0;
    let totalIpft = 0.0;
    let totalGst = 0.0;
    
    for (let oid in orderMap) {
        const oTrades = orderMap[oid];
        const buyVal = oTrades.filter(t => t.trade_type.toLowerCase() === 'buy').reduce((s, t) => s + parseFloat(t.quantity)*parseFloat(t.price), 0.0);
        const sellVal = oTrades.filter(t => t.trade_type.toLowerCase() === 'sell').reduce((s, t) => s + parseFloat(t.quantity)*parseFloat(t.price), 0.0);
        const totalVal = buyVal + sellVal;
        
        let brokerage = 0.0;
        if (instType === 'CE' || instType === 'PE') {
            brokerage = 20.0;
        } else if (instType === 'FUT') {
            brokerage = Math.min(totalVal * 0.0003, 20.0);
        } else if (instType === 'EQ') {
            brokerage = isIntraday ? Math.min(totalVal * 0.0003, 20.0) : 0.0;
        }
        
        let stt = 0.0;
        if (instType === 'FUT') {
            stt = sellVal * 0.0002;
        } else if (instType === 'CE' || instType === 'PE') {
            stt = sellVal * 0.001;
        } else if (instType === 'EQ') {
            stt = isIntraday ? sellVal * 0.00025 : totalVal * 0.001;
        }
        
        let txn = 0.0;
        if (instType === 'FUT') {
            txn = exchange === 'NSE' ? totalVal * 0.0000173 : 0.0;
        } else if (instType === 'CE' || instType === 'PE') {
            txn = exchange === 'NSE' ? totalVal * 0.0003503 : totalVal * 0.000325;
        } else if (instType === 'EQ') {
            txn = exchange === 'NSE' ? totalVal * 0.0000297 : totalVal * 0.0000375;
        }
        
        const sebi = (totalVal / 10000000.0) * 10.0;
        
        let ipft = 0.0;
        if (exchange === 'NSE') {
            if (instType === 'FUT' || instType === 'EQ') {
                ipft = (totalVal / 10000000.0) * 10.0 * 1.18;
            } else if (instType === 'CE' || instType === 'PE') {
                ipft = (totalVal / 10000000.0) * 50.0 * 1.18;
            }
        }
        
        let stamp = 0.0;
        if (buyVal > 0) {
            if (instType === 'FUT') {
                stamp = Math.min(buyVal * 0.00002, (buyVal / 10000000.0) * 200.0);
            } else if (instType === 'CE' || instType === 'PE') {
                stamp = Math.min(buyVal * 0.00003, (buyVal / 10000000.0) * 300.0);
            } else if (instType === 'EQ') {
                stamp = isIntraday ? Math.min(buyVal * 0.00003, (buyVal / 10000000.0) * 300.0) : Math.min(buyVal * 0.00015, (buyVal / 10000000.0) * 1500.0);
            }
        }
        
        const gst = (brokerage + sebi + txn) * 0.18;
        
        totalBrokerage += brokerage;
        totalStt += stt;
        totalTxn += txn;
        totalSebi += sebi;
        totalStamp += stamp;
        totalIpft += ipft;
        totalGst += gst;
    }
    
    const totalCharges = totalBrokerage + totalStt + totalTxn + totalSebi + totalStamp + totalIpft + totalGst;
    return {
        brokerage: totalBrokerage,
        stt: totalStt,
        transactionCharges: totalTxn,
        sebiCharges: totalSebi,
        stampCharges: totalStamp,
        ipftCharges: totalIpft,
        gst: totalGst,
        totalCharges: totalCharges
    };
}

function calculateAllMetrics(trades) {
    if (!trades || trades.length === 0) {
        return null;
    }
    
    const positions = calculatePositions(trades);
    const closedPositions = positions.filter(p => p.status === 'closed');
    const winningPositions = closedPositions.filter(p => p.realized_pnl > 0);
    const losingPositions = closedPositions.filter(p => p.realized_pnl < 0);
    
    const totalPnL = closedPositions.reduce((s, p) => s + p.realized_pnl, 0.0);
    const grossTurnover = closedPositions.reduce((s, p) => s + p.total_buy_value + p.total_sell_value, 0.0);
    
    let totalBrokerage = 0.0;
    for (let p of closedPositions) {
        const exch = p.trades[0]?.exchange || 'NSE';
        const charges = calculateBrokerageCharges(p, exch);
        totalBrokerage += charges.totalCharges;
    }
    
    const avgWin = winningPositions.length > 0 ? winningPositions.reduce((s, p) => s + p.realized_pnl, 0.0) / winningPositions.length : 0.0;
    const avgLoss = losingPositions.length > 0 ? losingPositions.reduce((s, p) => s + p.realized_pnl, 0.0) / losingPositions.length : 0.0;
    
    const maxWin = winningPositions.length > 0 ? Math.max(...winningPositions.map(p => p.realized_pnl)) : 0.0;
    const maxLoss = losingPositions.length > 0 ? Math.min(...losingPositions.map(p => p.realized_pnl)) : 0.0;
    
    const totalWins = winningPositions.reduce((s, p) => s + p.realized_pnl, 0.0);
    const totalLosses = Math.abs(losingPositions.reduce((s, p) => s + p.realized_pnl, 0.0));
    const profitFactor = totalLosses > 0 ? totalWins / totalLosses : (totalWins > 0 ? 999.0 : 0.0);
    
    const winRate = closedPositions.length > 0 ? (winningPositions.length / closedPositions.length) * 100 : 0.0;
    
    // Group daily P&L
    const dailyMap = {};
    for (let p of closedPositions) {
        if (p.realized_pnl === 0) continue;
        
        // Find unique trading dates for this position
        const dates = [...new Set(p.trades.map(t => String(t.trade_date).split(' ')[0]))].sort();
        if (dates.length === 0) continue;
        
        const charges = calculateBrokerageCharges(p, p.trades[0]?.exchange || 'NSE');
        const totCharges = charges.totalCharges;
        
        if (dates.length === 1) {
            const d = dates[0];
            if (!dailyMap[d]) dailyMap[d] = { realized_pnl: 0, brokerage: 0 };
            dailyMap[d].realized_pnl += p.realized_pnl;
            dailyMap[d].brokerage += totCharges;
        } else {
            const pnlPerDay = p.realized_pnl / dates.length;
            const chargesPerDay = totCharges / dates.length;
            for (let d of dates) {
                if (!dailyMap[d]) dailyMap[d] = { realized_pnl: 0, brokerage: 0 };
                dailyMap[d].realized_pnl += pnlPerDay;
                dailyMap[d].brokerage += chargesPerDay;
            }
        }
    }
    
    const dailyPnL = [];
    for (let d in dailyMap) {
        const netVal = dailyMap[d].realized_pnl - dailyMap[d].brokerage;
        dailyPnL.push({
            date: d,
            realized_pnl: dailyMap[d].realized_pnl,
            brokerage: dailyMap[d].brokerage,
            net_pnl: netVal
        });
    }
    
    dailyPnL.sort((a, b) => new Date(a.date) - new Date(b.date));
    
    // Max drawdown
    let maxDrawdown = 0.0;
    if (dailyPnL.length > 0) {
        let cumPnL = 0.0;
        let peak = 0.0;
        for (let d of dailyPnL) {
            cumPnL += d.net_pnl;
            if (cumPnL > peak) peak = cumPnL;
            const drawdown = peak - cumPnL;
            if (drawdown > maxDrawdown) maxDrawdown = drawdown;
        }
    }
    
    return {
        total_trades: trades.length,
        winning_trades: winningPositions.length,
        losing_trades: losingPositions.length,
        win_rate: winRate,
        total_pnl: totalPnL,
        avg_win: avgWin,
        avg_loss: avgLoss,
        max_win: maxWin,
        max_loss: maxLoss,
        profit_factor: profitFactor,
        gross_turnover: grossTurnover,
        total_brokerage: totalBrokerage,
        net_pnl: totalPnL - totalBrokerage,
        max_drawdown: maxDrawdown,
        positions: positions,
        daily_pnl: dailyPnL
    };
}
