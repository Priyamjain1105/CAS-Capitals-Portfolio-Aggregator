from flask import Flask
import os

# Load .env variables if present
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
    
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'cas-capitals-secret-key-1234')
    
    # Register routes
    from routes import register_routes
    register_routes(app)
            
    return app