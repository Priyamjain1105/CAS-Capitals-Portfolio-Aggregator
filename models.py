from app import db
from datetime import datetime

class UserUploadHistory(db.Model):
    __tablename__ = 'user_upload_history'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.String(255), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)
    file_label = db.Column(db.String(255), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    row_count = db.Column(db.Integer, default=0)

class TradeLog(db.Model):
    __tablename__ = 'trade_log'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.String(255), nullable=False, index=True)
    upload_id = db.Column(db.Integer, db.ForeignKey('user_upload_history.id', ondelete='CASCADE'), nullable=True)
    
    symbol = db.Column(db.String(100), nullable=False, index=True)
    isin = db.Column(db.String(50), nullable=True)
    trade_date = db.Column(db.Date, nullable=False)
    exchange = db.Column(db.String(50), nullable=False)
    segment = db.Column(db.String(50), nullable=False)
    series = db.Column(db.String(50), nullable=True)
    trade_type = db.Column(db.String(20), nullable=False) # 'buy' or 'sell'
    auction = db.Column(db.Boolean, default=False)
    quantity = db.Column(db.Float, nullable=False)
    price = db.Column(db.Float, nullable=False)
    trade_id = db.Column(db.String(100), nullable=False)
    order_id = db.Column(db.String(100), nullable=False)
    order_execution_time = db.Column(db.DateTime, nullable=False)
    expiry_date = db.Column(db.Date, nullable=True)
    value = db.Column(db.Float, nullable=False) # quantity * price

class PositionMetric(db.Model):
    __tablename__ = 'position_metric'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.String(255), nullable=False, index=True)
    
    symbol = db.Column(db.String(100), nullable=False)
    instrument_type = db.Column(db.String(50), nullable=False) # CE, PE, FUT, EQ
    strike_price = db.Column(db.Float, nullable=True)
    expiry_date = db.Column(db.Date, nullable=True)
    net_quantity = db.Column(db.Float, nullable=False)
    avg_buy_price = db.Column(db.Float, default=0.0)
    avg_sell_price = db.Column(db.Float, default=0.0)
    total_buy_value = db.Column(db.Float, default=0.0)
    total_sell_value = db.Column(db.Float, default=0.0)
    realized_pnl = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(50), nullable=False) # open, closed
    
    open_time = db.Column(db.DateTime, nullable=False)
    close_time = db.Column(db.DateTime, nullable=True)
    entry_price = db.Column(db.Float, nullable=False)
    exit_price = db.Column(db.Float, nullable=True)

class DailyPnLMetric(db.Model):
    __tablename__ = 'daily_pnl_metric'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.String(255), nullable=False, index=True)
    
    date = db.Column(db.Date, nullable=False)
    realized_pnl = db.Column(db.Float, default=0.0)
    brokerage = db.Column(db.Float, default=0.0)
    net_pnl = db.Column(db.Float, default=0.0)
    total_trades = db.Column(db.Integer, default=0)
    winning_trades = db.Column(db.Integer, default=0)
    losing_trades = db.Column(db.Integer, default=0)
    gross_turnover = db.Column(db.Float, default=0.0)

class AggregateMetric(db.Model):
    __tablename__ = 'aggregate_metric'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.String(255), nullable=False, unique=True)
    
    total_trades = db.Column(db.Integer, default=0)
    winning_trades = db.Column(db.Integer, default=0)
    losing_trades = db.Column(db.Integer, default=0)
    win_rate = db.Column(db.Float, default=0.0)
    total_pnl = db.Column(db.Float, default=0.0)
    avg_win = db.Column(db.Float, default=0.0)
    avg_loss = db.Column(db.Float, default=0.0)
    max_win = db.Column(db.Float, default=0.0)
    max_loss = db.Column(db.Float, default=0.0)
    profit_factor = db.Column(db.Float, default=0.0)
    gross_turnover = db.Column(db.Float, default=0.0)
    total_brokerage = db.Column(db.Float, default=0.0)
    net_pnl = db.Column(db.Float, default=0.0)
    max_drawdown = db.Column(db.Float, default=0.0)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
