from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import os

#database object

db = SQLAlchemy()


# Load .env variables
import sys
if os.path.exists('.env'):
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        # Fallback to parse manually if dotenv package is not loaded yet
        with open('.env') as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    k, v = line.strip().split('=', 1)
                    os.environ[k.strip()] = v.strip()

def create_app():
    app = Flask(__name__, template_folder='templates')
    
    # DB configuration: look for Aiven link first, then standard url, then local fallback
    db_uri = os.environ.get('DATABASE_URL') or os.environ.get('SQLALCHEMY_DATABASE_URI')
    if not db_uri:
        db_uri = 'mysql+pymysql://root:@127.0.0.1/brokerapp'
    
    app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'cas-capitals-secret-key-1234')
    
    # Configure SSL connect args if connecting to Aiven
    if 'aivencloud.com' in db_uri:
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'connect_args': {
                'ssl': {'ssl_mode': 'REQUIRED'}
            }
        }
    
    db.init_app(app)
    
    # Register routes
    from routes import register_routes
    register_routes(app)
    
    migrate = Migrate(app, db)
    
    # Automatically create tables when the app launches
    with app.app_context():
        import models
        try:
            db.create_all()
            print("INFO: Database models successfully mapped and tables verified.")
        except Exception as e:
            print(f"WARNING: Automatic table initialization skipped: {e}", file=sys.stderr)
            
    return app