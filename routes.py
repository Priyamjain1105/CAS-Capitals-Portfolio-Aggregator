import uuid
import pandas as pd
from datetime import datetime, date
from flask import request, render_template, session, jsonify, flash, redirect, url_for
from models import db, UserUploadHistory, TradeLog, PositionMetric, DailyPnLMetric, AggregateMetric
from analytics import calculate_all_metrics

ALLOWED_EXTENSIONS = {"csv"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def parse_csv_file(file_storage):
    """
    Parse uploaded CSV directly from memory without saving to disk.
    Returns list of dictionaries (one dict per row).
    """
    file_storage.stream.seek(0)
    df = pd.read_csv(file_storage)

    # Replace NaN with None for cleaner downstream processing
    df = df.where(pd.notnull(df), None)

    return df.to_dict(orient="records")

def get_session_id():
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    return session['session_id']

def parse_csv_row_to_db(row, session_id, upload_id):
    # safe date parsing
    trade_date_val = None
    if row.get('trade_date'):
        try:
            trade_date_val = datetime.strptime(str(row['trade_date']).strip(), '%Y-%m-%d').date()
        except Exception:
            pass
            
    exec_time_val = None
    if row.get('order_execution_time'):
        try:
            t_str = str(row['order_execution_time']).strip()
            if 'T' in t_str:
                exec_time_val = datetime.strptime(t_str, '%Y-%m-%dT%H:%M:%S')
            else:
                exec_time_val = datetime.strptime(t_str, '%Y-%m-%d %H:%M:%S')
        except Exception:
            pass
    if not exec_time_val and trade_date_val:
        exec_time_val = datetime.combine(trade_date_val, datetime.min.time())
        
    expiry_date_val = None
    if row.get('expiry_date'):
        try:
            expiry_date_val = datetime.strptime(str(row['expiry_date']).strip(), '%Y-%m-%d').date()
        except Exception:
            pass
            
    qty = float(row.get('quantity', 0) or 0)
    price = float(row.get('price', 0) or 0)
    value = qty * price
    
    auction_val = False
    if row.get('auction') is not None:
        auction_val = str(row['auction']).lower() == 'true'
        
    return TradeLog(
        session_id=session_id,
        upload_id=upload_id,
        symbol=str(row.get('symbol', '')),
        isin=str(row.get('isin', '')) if row.get('isin') else None,
        trade_date=trade_date_val or date.today(),
        exchange=str(row.get('exchange', 'NSE')),
        segment=str(row.get('segment', 'FO')),
        series=str(row.get('series', '')) if row.get('series') else None,
        trade_type=str(row.get('trade_type', 'buy')).lower(),
        auction=auction_val,
        quantity=qty,
        price=price,
        trade_id=str(row.get('trade_id', '')),
        order_id=str(row.get('order_id', '')),
        order_execution_time=exec_time_val or datetime.now(),
        expiry_date=expiry_date_val,
        value=value
    )

def register_routes(app):

    @app.route('/', methods=['GET'])
    def home():
        return render_template('index.html')

    @app.route('/upload', methods=['GET'])
    def upload():
        session_id = get_session_id()
        # Retrieve upload history for the session
        uploads = UserUploadHistory.query.filter_by(session_id=session_id).order_by(UserUploadHistory.uploaded_at.desc()).all()
        return render_template('upload.html', uploads=uploads)

    @app.route('/upload-trades', methods=['POST'])
    def upload_file():
        file_label = request.form.get('file_label', '').strip()
        files = request.files.getlist("files")
        session_id = get_session_id()

        if not files or all(f.filename == '' for f in files):
            return render_template(
                "upload.html",
                error_message="Please select at least one CSV file.",
                file_label=file_label
            )

        # CRITICAL: Wipe strategy for re-upload. Clear all previous session metrics/trades
        try:
            TradeLog.query.filter_by(session_id=session_id).delete()
            UserUploadHistory.query.filter_by(session_id=session_id).delete()
            PositionMetric.query.filter_by(session_id=session_id).delete()
            DailyPnLMetric.query.filter_by(session_id=session_id).delete()
            AggregateMetric.query.filter_by(session_id=session_id).delete()
            db.session.commit()
        except Exception as err:
            db.session.rollback()
            print("Session overwrite wipe error:", err)
            return render_template(
                "upload.html",
                error_message=f"Failed to clear existing database entries: {str(err)}",
                file_label=file_label
            )

        parsed_payload = []
        total_rows = 0

        try:
            for file in files:
                if not file or file.filename == '':
                    continue

                if not allowed_file(file.filename):
                    return render_template(
                        "upload.html",
                        error_message=f'"{file.filename}" is not a CSV file.',
                        file_label=file_label
                    )

                rows = parse_csv_file(file)

                # Save file upload record
                upload_record = UserUploadHistory(
                    session_id=session_id,
                    filename=file.filename,
                    file_label=file_label if file_label else None,
                    row_count=len(rows)
                )
                db.session.add(upload_record)
                db.session.commit() # commit to get upload_record.id

                # Save raw trades
                for row in rows:
                    trade_log = parse_csv_row_to_db(row, session_id, upload_record.id)
                    db.session.add(trade_log)
                db.session.commit()

                parsed_payload.append({
                    "source_file": file.filename,
                    "row_count": len(rows),
                    "rows": rows[:5]   # preview first 5 rows
                })
                total_rows += len(rows)

            # Trigger analytics engine computation automatically following DB insertion
            db_trades = TradeLog.query.filter_by(session_id=session_id).all()
            
            # Format to dictionaries for analytics module
            trades_list = []
            for t in db_trades:
                trades_list.append({
                    'symbol': t.symbol,
                    'segment': t.segment,
                    'trade_date': t.trade_date,
                    'trade_type': t.trade_type,
                    'quantity': t.quantity,
                    'price': t.price,
                    'value': t.value,
                    'order_id': t.order_id,
                    'order_execution_time': t.order_execution_time,
                    'expiry_date': t.expiry_date,
                    'exchange': t.exchange
                })

            metrics = calculate_all_metrics(trades_list)

            # Save aggregate metrics
            agg = AggregateMetric(
                session_id=session_id,
                total_trades=metrics['total_trades'],
                winning_trades=metrics['winning_trades'],
                losing_trades=metrics['losing_trades'],
                win_rate=metrics['win_rate'],
                total_pnl=metrics['total_pnl'],
                avg_win=metrics['avg_win'],
                avg_loss=metrics['avg_loss'],
                max_win=metrics['max_win'],
                max_loss=metrics['max_loss'],
                profit_factor=metrics['profit_factor'] if metrics['profit_factor'] != float('inf') else 999.0,
                gross_turnover=metrics['gross_turnover'],
                total_brokerage=metrics['total_brokerage'],
                net_pnl=metrics['net_pnl'],
                max_drawdown=metrics['max_drawdown']
            )
            db.session.add(agg)

            # Save positions metrics
            for p in metrics['positions']:
                pm = PositionMetric(
                    session_id=session_id,
                    symbol=p['symbol'],
                    instrument_type=p['instrument_type'],
                    strike_price=p['strike_price'],
                    expiry_date=p['expiry_date'],
                    net_quantity=p['net_quantity'],
                    avg_buy_price=p['avg_buy_price'],
                    avg_sell_price=p['avg_sell_price'],
                    total_buy_value=p['total_buy_value'],
                    total_sell_value=p['total_sell_value'],
                    realized_pnl=p['realized_pnl'],
                    status=p['status'],
                    open_time=p['open_time'],
                    close_time=p['close_time'],
                    entry_price=p['entry_price'],
                    exit_price=p['exit_price']
                )
                db.session.add(pm)

            # Save daily P&L metrics
            for d in metrics['daily_pnl']:
                dpm = DailyPnLMetric(
                    session_id=session_id,
                    date=d['date'],
                    realized_pnl=d['realized_pnl'],
                    brokerage=d['brokerage'],
                    net_pnl=d['net_pnl'],
                    total_trades=0,
                    winning_trades=0,
                    losing_trades=0,
                    gross_turnover=0.0
                )
                db.session.add(dpm)

            db.session.commit()

            # Load updated upload history
            uploads = UserUploadHistory.query.filter_by(session_id=session_id).order_by(UserUploadHistory.uploaded_at.desc()).all()
            
            return render_template(
                "upload.html",
                success_message=f"Successfully parsed {len(parsed_payload)} CSV file(s) with {total_rows} total row(s) and updated analytics.",
                parsed_payload=parsed_payload,
                total_rows=total_rows,
                file_label=file_label,
                uploads=uploads
            )

        except Exception as err:
            db.session.rollback()
            print("CSV parsing/storage error:", err)
            return render_template(
                "upload.html",
                error_message=f"CSV parsing or database insertion failed: {str(err)}",
                file_label=file_label
            )

    @app.route('/dashboard', methods=['GET'])
    def dashboard():
        session_id = get_session_id()
        aggregate = AggregateMetric.query.filter_by(session_id=session_id).first()
        daily_pnl = DailyPnLMetric.query.filter_by(session_id=session_id).order_by(DailyPnLMetric.date).all()
        positions = PositionMetric.query.filter_by(session_id=session_id).all()

        chart_labels = [d.date.strftime('%Y-%m-%d') for d in daily_pnl]
        chart_daily_net = [d.net_pnl for d in daily_pnl]

        # Calculate running cumulative net return curve
        chart_cum_net = []
        cum_sum = 0.0
        for val in chart_daily_net:
            cum_sum += val
            chart_cum_net.append(cum_sum)

        closed_positions = [p for p in positions if p.status == 'closed']
        open_positions = [p for p in positions if p.status == 'open']

        # Aggregate P&L by Instrument Type
        inst_pnl = {}
        for pos in closed_positions:
            itype = pos.instrument_type or 'EQ'
            inst_pnl[itype] = inst_pnl.get(itype, 0.0) + pos.realized_pnl
        inst_labels = list(inst_pnl.keys())
        inst_values = list(inst_pnl.values())

        # Aggregate P&L by Symbol
        symbol_pnl = {}
        for pos in closed_positions:
            sym = pos.symbol
            symbol_pnl[sym] = symbol_pnl.get(sym, 0.0) + pos.realized_pnl
        # Sort symbols by P&L for plotting
        sorted_syms = sorted(symbol_pnl.items(), key=lambda x: x[1])
        sym_labels = [x[0] for x in sorted_syms]
        sym_values = [x[1] for x in sorted_syms]

        return render_template(
            'dashboard.html',
            aggregate=aggregate,
            daily_pnl=daily_pnl,
            closed_positions=closed_positions,
            open_positions=open_positions,
            chart_labels=chart_labels,
            chart_daily_net=chart_daily_net,
            chart_cum_net=chart_cum_net,
            inst_labels=inst_labels,
            inst_values=inst_values,
            sym_labels=sym_labels,
            sym_values=sym_values
        )

    @app.route('/pyramiding', methods=['GET'])
    def pyramiding():
        session_id = get_session_id()
        positions = PositionMetric.query.filter_by(session_id=session_id).order_by(PositionMetric.open_time.desc()).all()

        positions_with_trades = []
        for pos in positions:
            # Query matching TradeLogs to list chronology
            query = TradeLog.query.filter_by(session_id=session_id, symbol=pos.symbol)
            if pos.expiry_date:
                query = query.filter_by(expiry_date=pos.expiry_date)
            
            # Find trades within position timeframe
            query = query.filter(TradeLog.order_execution_time >= pos.open_time)
            if pos.close_time:
                query = query.filter(TradeLog.order_execution_time <= pos.close_time)

            trades = query.order_by(TradeLog.order_execution_time).all()

            running_qty = 0.0
            running_value = 0.0
            steps = []

            for t in trades:
                t_type = t.trade_type.lower()
                qty = t.quantity
                val = t.value

                if t_type == 'buy':
                    if pos.net_quantity >= 0 or pos.entry_price > 0: # Long
                        running_qty += qty
                        running_value += val
                    else: # Covering Short
                        running_qty -= qty
                        running_value -= val
                elif t_type == 'sell':
                    if pos.net_quantity >= 0 or pos.entry_price > 0: # Liquidating Long
                        running_qty -= qty
                        running_value -= val
                    else: # Shorting more
                        running_qty += qty
                        running_value += val

                avg_cost = (running_value / running_qty) if running_qty > 0 else 0
                steps.append({
                    'trade': t,
                    'running_qty': running_qty,
                    'avg_cost': avg_cost
                })

            positions_with_trades.append({
                'position': pos,
                'steps': steps
            })

        return render_template('pyramiding.html', positions_with_trades=positions_with_trades)

    @app.route('/api/llm/advanced-analysis', methods=['POST'])
    def advanced_analysis():
        session_id = get_session_id()

        # Retrieve session data to prepare payload
        trades = TradeLog.query.filter_by(session_id=session_id).order_by(TradeLog.order_execution_time).all()
        positions = PositionMetric.query.filter_by(session_id=session_id).all()
        aggregate = AggregateMetric.query.filter_by(session_id=session_id).first()

        if not trades:
            return jsonify({
                'status': 'error',
                'message': 'No trade records found for the current session. Please upload a CSV first.'
            }), 400

        # Construct analytical dataset for Claude
        serialized_trades = [{
            'symbol': t.symbol,
            'trade_date': str(t.trade_date),
            'trade_type': t.trade_type,
            'quantity': t.quantity,
            'price': t.price,
            'order_execution_time': str(t.order_execution_time),
            'segment': t.segment,
            'value': t.value
        } for t in trades]

        serialized_positions = [{
            'symbol': p.symbol,
            'instrument_type': p.instrument_type,
            'net_quantity': p.net_quantity,
            'entry_price': p.entry_price,
            'exit_price': p.exit_price,
            'realized_pnl': p.realized_pnl,
            'status': p.status,
            'open_time': str(p.open_time),
            'close_time': str(p.close_time) if p.close_time else None
        } for p in positions]

        serialized_metrics = {
            'total_trades': aggregate.total_trades if aggregate else 0,
            'win_rate': aggregate.win_rate if aggregate else 0.0,
            'total_pnl': aggregate.total_pnl if aggregate else 0.0,
            'net_pnl': aggregate.net_pnl if aggregate else 0.0,
            'max_drawdown': aggregate.max_drawdown if aggregate else 0.0,
            'profit_factor': aggregate.profit_factor if aggregate else 0.0
        }

        # Customizable system prompt
        custom_system_prompt = None
        if request.is_json:
            custom_system_prompt = request.json.get('system_prompt')
        
        if not custom_system_prompt:
            custom_system_prompt = (
                "You are an expert trading psychologist and risk analyst. Analyze the following trade data "
                "for behavioral patterns, psychological flags (like revenge trading, FOMO, over-trading, or lack of discipline), "
                "and strategic alignment. Provide a strict JSON response containing: psychological_flags, strategic_insights, "
                "and grading_and_feedback."
            )

        # Prepare payload structure for Anthropic API
        claude_payload = {
            'model': 'claude-3-5-sonnet-20241022',
            'max_tokens': 4000,
            'system': custom_system_prompt,
            'messages': [
                {
                    'role': 'user',
                    'content': f"Here are the trade log details, positions, and aggregate metrics to analyze:\n\n"
                               f"Metrics: {serialized_metrics}\n\n"
                               f"Positions: {serialized_positions[:30]}\n\n"
                               f"Raw Trade Execution Log: {serialized_trades[:100]}"
                }
            ]
        }

        # Define a structured placeholder JSON response mimicking Claude's output
        mock_claude_response = {
            'psychological_flags': [
                {
                    'flag': 'Revenge Trading Pattern',
                    'severity': 'High',
                    'description': 'Detected multiple large trades placed in quick succession immediately following a losing trade. Trade size increased by 50% on option contracts within 15 minutes of a loss.',
                    'evidence': 'Large size buy logs occurred at 09:25:00, shortly after a negative transaction occurred at 09:21:55.'
                },
                {
                    'flag': 'Over-Trading Frequency',
                    'severity': 'Medium',
                    'description': 'Frequent short-term trades placed within short intervals, leading to ballooning transaction and brokerage fees.',
                    'evidence': 'Executed multiple micro-order lines on the same stock under identical minute windows.'
                }
            ],
            'strategic_insights': [
                {
                    'insight_type': 'Option Premium Theta Decay',
                    'description': 'High decay exposure on long options (CE/PE) held across multiple sessions.',
                    'actionable_advice': 'Avoid holding overnight naked options. Use spread strategies (such as bull call spreads or bear put spreads) to mitigate theta risk.'
                },
                {
                    'insight_type': 'Market Opening Volatility',
                    'description': 'Positions initiated in the first 15 minutes of open (09:15 - 09:30) have a win-rate of only 25%, whereas post-10:30 trades exceed 60%.',
                    'actionable_advice': 'Wait for the opening range to settle. Avoid entering positions before 10:00 AM.'
                }
            ],
            'grading_and_feedback': {
                'discipline_score': 68,
                'risk_management_score': 55,
                'consistency_score': 72,
                'overall_feedback': 'Discipline is moderately stable, but overall risk controls are deficient due to revenge scaling (increasing lot sizing after losses) and higher drawdowns. Individual loss size exceeds average wins.',
                'actionable_optimization_points': [
                    'Enforce a strict daily loss cap. Terminate trading activities once threshold is breached.',
                    'Limit active trade entry logs per asset contract to 3 per day.',
                    'Standardize position risk limits; never double transaction sizing during drawdowns.'
                ]
            }
        }

        return jsonify({
            'status': 'success',
            'message': 'Payload prepared successfully (mock response returned as external api execution is deferred).',
            'payload_prepared': claude_payload,
            'llm_analysis': mock_claude_response
        })
