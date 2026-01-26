from flask_app.app import create_app, socketio
import logging

app = create_app()

# Ensure logging is working
logging.info("=" * 80)
logging.info("Flask application starting...")
logging.info("=" * 80)

if __name__ == "__main__":
    logging.info("Starting Flask development server with SocketIO...")
    socketio.run(app, debug=True, host="0.0.0.0", port=5000, allow_unsafe_werkzeug=True)
