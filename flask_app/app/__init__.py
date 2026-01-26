from flask import Flask
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_mail import Mail
from flask_socketio import SocketIO
from config import settings, setup_logging
import logging
import os
import threading

# Removed Flask-SQLAlchemy - using async SQLAlchemy directly
bcrypt = Bcrypt()
login_manager = LoginManager()
login_manager.login_view = "users.login"
login_manager.login_message_category = "info"
mail = Mail()
socketio = SocketIO(cors_allowed_origins="*", async_mode="threading")


def create_app(config_class=settings):
    # Setup logging first - ensure drone.log file is created
    # Always call setup_logging to ensure proper configuration
    setup_logging()

    # Verify logging is working and flush
    log_file_path = os.path.abspath(
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "drone.log"
        )
    )
    logging.info(f"Flask app initializing - logs will be written to {log_file_path}")
    # Flush all file handlers to ensure logs are written
    for handler in logging.root.handlers:
        if isinstance(handler, logging.FileHandler):
            handler.flush()

    app = Flask(__name__)
    app.config.from_object(settings)

    # Set SECRET_KEY for Flask-Login and token generation
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = (
            settings.flask_secret_key or "dev-secret-key-change-in-production"
        )

    # Configure Flask's logger - ensure it propagates to root logger
    app.logger.setLevel(logging.INFO)
    app.logger.propagate = (
        True  # This ensures Flask logs go to root logger (and thus to file)
    )

    # Also configure werkzeug (Flask's underlying server)
    werkzeug_logger = logging.getLogger("werkzeug")
    werkzeug_logger.setLevel(logging.INFO)
    werkzeug_logger.propagate = True  # Ensure werkzeug logs also go to root logger

    bcrypt.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)
    socketio.init_app(app)

    # Setup synchronous user loader for Flask-Login
    from db.models import load_user_sync

    login_manager.user_loader(load_user_sync)

    # Initialize database on Flask startup (synchronous) - optimized
    _db_initialized = False
    _db_init_lock = threading.Lock()

    def initialize_database():
        """Initialize database when Flask starts (synchronous) - with error handling"""
        nonlocal _db_initialized
        if _db_initialized:
            return

        with _db_init_lock:
            # Double-check after acquiring lock
            if _db_initialized:
                return
        import logging
        from db.flask_session import init_sync_db

        try:
            logging.info("Initializing database for Flask application (sync mode)...")
            init_sync_db()
            logging.info("✅ Database initialized successfully")
            _db_initialized = True
        except Exception as e:
            logging.error(f"❌ Failed to initialize database: {e}", exc_info=True)
            # Don't raise - allow Flask to start, but database operations will fail
            _db_initialized = False

    # Initialize database lazily on first request (optimized - only once)
    @app.before_request
    def check_db_initialized():
        """Check database is initialized (lightweight check - only runs once)"""
        if not _db_initialized:
            initialize_database()

    # Initialize command handler (lazy - will initialize on first use)
    _command_handler_initialized = False

    def init_command_handler_once():
        """Initialize command handler once"""
        nonlocal _command_handler_initialized
        if not _command_handler_initialized:
            try:
                from flask_app.app.dashboard.drone_command_handler import (
                    get_command_handler,
                )

                get_command_handler()  # Initialize and connect
                _command_handler_initialized = True
            except Exception as e:
                import logging

                logging.error(f"Failed to initialize command handler: {e}")

    # Initialize on first request
    @app.before_request
    def init_command_handler():
        init_command_handler_once()

    from flask_app.app.users.routes import users
    from flask_app.app.dashboard.routes import dashboard_bp
    from flask_app.app.main.routes import main
    from flask_app.app.errors.handlers import errors

    app.register_blueprint(users)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(main)
    app.register_blueprint(errors)

    # Register socketio events (this will also initialize MQTT bridge)
    from flask_app.app.dashboard import socketio_events

    socketio_events.register_events(socketio)

    return app
