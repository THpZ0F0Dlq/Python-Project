import os
from flask import Flask, jsonify, request, Response
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_bcrypt import Bcrypt
from dotenv import load_dotenv
from flasgger import Swagger
from flask_cors import CORS
import time
from werkzeug.exceptions import HTTPException
from sqlalchemy.exc import SQLAlchemyError

# Load environment variables
load_dotenv()

# Initialize extensions
db = SQLAlchemy()
jwt = JWTManager()
bcrypt = Bcrypt()

# Dictionary to track request counts for rate limiting
request_counts = {}
# How many requests allowed within the time window
RATE_LIMIT = 15
# Time window in seconds
RATE_LIMIT_WINDOW = 60

def create_app(test_config=None):
    # Create and configure the app
    app = Flask(__name__, instance_relative_config=True)

    # Enable CORS for all routes
    CORS(app)

    # Initialize Swagger for API documentation
    swagger = Swagger(app, template_file=os.path.join(os.path.dirname(__file__), 'swagger.yaml'))
    
    # Default configuration
    app.config.from_mapping(
        SECRET_KEY=os.environ.get('SECRET_KEY', os.urandom(24).hex()),
        SQLALCHEMY_DATABASE_URI=os.environ.get(
            'SQLALCHEMY_DATABASE_URI',
            f"sqlite:///{os.path.join(app.instance_path, 'bank.db')}"
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        JWT_SECRET_KEY=os.environ.get('JWT_SECRET_KEY', os.urandom(24).hex()),
        JWT_ACCESS_TOKEN_EXPIRES=3600,  # 1 hour
        JWT_COOKIE_SECURE=True,
        JWT_COOKIE_CSRF_PROTECT=True,
        JWT_CSRF_CHECK_FORM=True,
    )
    
    # Enable debug mode only in development
    app.debug = os.environ.get('FLASK_ENV') == 'development'

    if test_config is None:
        # Load the instance config, if it exists, when not testing
        app.config.from_pyfile('config.py', silent=True)
    else:
        # Load the test config if passed in
        app.config.from_mapping(test_config)

    # Ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # Initialize extensions with app
    db.init_app(app)
    jwt.init_app(app)
    bcrypt.init_app(app)
    
    # Configure JWT handling
    @jwt.user_identity_loader
    def user_identity_lookup(identity):
        return str(identity)
    
    @jwt.user_lookup_loader
    def user_lookup_callback(_jwt_header, jwt_data):
        identity = jwt_data["sub"]
        try:
            user_id = int(identity)
            from app.models.user import User
            return User.query.filter_by(id=user_id).one_or_none()
        except (ValueError, TypeError):
            return None
    
    # Error handling
    @app.errorhandler(HTTPException)
    def handle_http_error(error):
        return jsonify({
            "error": error.name,
            "message": error.description
        }), error.code

    @app.errorhandler(SQLAlchemyError)
    def handle_db_error(error):
        app.logger.error(f"Database error: {str(error)}")
        return jsonify({
            "error": "Database error",
            "message": "An error occurred while processing your request"
        }), 500

    @app.errorhandler(Exception)
    def handle_generic_error(error):
        app.logger.error(f"Unexpected error: {str(error)}")
        return jsonify({
            "error": "Internal server error",
            "message": "An unexpected error occurred"
        }), 500

    @jwt.expired_token_loader
    def expired_token_callback(_jwt_header, jwt_payload):
        return jsonify({
            "error": "Token expired",
            "message": "The token has expired, please login again"
        }), 401
    
    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        return jsonify({
            "error": "Invalid token",
            "message": "The provided token is invalid"
        }), 401
    
    @jwt.unauthorized_loader
    def missing_token_callback(error):
        return jsonify({
            "error": "Authentication required",
            "message": "Please provide a valid authentication token"
        }), 401

    # Add security headers
    @app.after_request
    def add_security_headers(response):
        # Skip Swagger UI routes
        if request.path.startswith('/apidocs') or request.path.startswith('/flasgger_static'):
            return response

        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Content-Security-Policy'] = "default-src 'self'"
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        
        return response
    
    # Implement rate limiting for all endpoints
    @app.before_request
    def rate_limiting():
        # Skip rate limiting in test mode
        if app.config.get('TESTING'):
            return
        
        # Get the client IP and user agent for better identification
        client_ip = request.remote_addr
        user_agent = request.headers.get('User-Agent', '')
        client_id = f"{client_ip}:{user_agent}"
        current_time = time.time()
        
        # Clean up old requests
        for client in list(request_counts.keys()):
            request_counts[client] = [req_time for req_time in request_counts[client] 
                                    if current_time - req_time < RATE_LIMIT_WINDOW]
            if not request_counts[client]:
                del request_counts[client]
        
        # Check current request count
        if client_id in request_counts and len(request_counts[client_id]) >= RATE_LIMIT:
            return jsonify({
                "error": "Rate limit exceeded",
                "message": "Too many requests, please try again later",
                "retry_after": RATE_LIMIT_WINDOW
            }), 429
        
        # Add current request
        if client_id not in request_counts:
            request_counts[client_id] = []
        request_counts[client_id].append(current_time)

    # Register models
    from app.models import user, account, transaction

    # Register blueprints
    from app.routes import auth, accounts, transactions
    app.register_blueprint(auth.bp)
    app.register_blueprint(accounts.bp)
    app.register_blueprint(transactions.bp)
    
    # Root endpoint for testing
    @app.route('/')
    def home():
        return jsonify({
            "message": "Welcome to the Banking API",
            "version": "1.0.0",
            "status": "operational"
        })

    # CLI commands
    @app.cli.command('init-db')
    def init_db_command():
        """Clear the existing data and create new tables."""
        try:
            db.drop_all()
            db.create_all()
            print('Initialized the database.')
        except SQLAlchemyError as e:
            print(f'Error initializing database: {str(e)}')

    return app 