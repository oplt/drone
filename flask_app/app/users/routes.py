from datetime import datetime, timezone
import os
from flask import (
    render_template,
    url_for,
    flash,
    redirect,
    request,
    Blueprint,
    current_app,
    jsonify,
)
from itsdangerous import BadSignature, SignatureExpired
from flask_app.app.users.forms import (
    RegistrationForm,
    LoginForm,
    UpdateAccountForm,
    RequestResetForm,
    ResetPasswordForm,
    SettingsForm,
)
from db.models import User, Flight, TelemetryRecord
from db.flask_repository import FlaskUserRepository, FlaskSettingsRepository
from flask_login import login_user, current_user, logout_user, login_required
from flask_app.app.users.utils import save_picture, send_reset_email
from db.flask_session import get_sync_session
from sqlalchemy import select, desc

users = Blueprint("users", __name__)
user_repo = FlaskUserRepository()  # Use sync repository for Flask
config_repo = FlaskSettingsRepository()  # Settings repository


@users.route("/register", methods=["GET", "POST"])
def register():
    """Register new user (synchronous - no async to avoid event loop issues)"""
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))
    form = RegistrationForm()
    if form.validate_on_submit():
        try:
            # Validate username uniqueness (synchronous)
            existing_user = user_repo.get_user_by_username(form.username.data)
            if existing_user:
                form.username.errors.append(
                    "That username is taken. Please choose a different one."
                )
                return render_template("register.html", title="Register", form=form)

            # Validate email uniqueness (synchronous)
            existing_user = user_repo.get_user_by_email(form.email.data)
            if existing_user:
                form.email.errors.append(
                    "That email is taken. Please choose a different one."
                )
                return render_template("register.html", title="Register", form=form)

            flash(
                "Your account has been created! You are now able to log in", "success"
            )
            return redirect(url_for("users.login"))
        except Exception as e:
            flash(f"An error occurred during registration: {str(e)}", "danger")
            current_app.logger.error(f"Registration error: {e}", exc_info=True)
    return render_template("register.html", title="Register", form=form)


@users.route("/login", methods=["GET", "POST"])
def login():
    """Login user (synchronous - no async to avoid event loop issues)"""
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))
    form = LoginForm()
    if form.validate_on_submit():
        try:
            user = user_repo.authenticate_user(
                username_or_email=form.email.data, password=form.password.data
            )
            if user:
                login_user(user, remember=form.remember.data)
                next_page = request.args.get("next")
                return (
                    redirect(next_page) if next_page else redirect(url_for("main.home"))
                )
            else:
                flash("Login Unsuccessful. Please check email and password", "danger")
        except Exception as e:
            flash("An error occurred during login. Please try again.", "danger")
            current_app.logger.error(f"Login error: {e}", exc_info=True)
    return render_template("login.html", title="Login", form=form)


@users.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("main.home"))


@users.route("/account", methods=["GET", "POST"])
@login_required
def account():
    form = UpdateAccountForm()
    if form.validate_on_submit():
        try:
            # Validate username uniqueness if changed (synchronous)
            if form.username.data != current_user.username:
                existing_user = user_repo.get_user_by_username(form.username.data)
                if existing_user:
                    form.username.errors.append(
                        "That username is taken. Please choose a different one."
                    )
                    image_file = url_for(
                        "static", filename="profile_pics/" + current_user.image_file
                    )
                    return render_template(
                        "account.html",
                        title="Account",
                        image_file=image_file,
                        form=form,
                    )

            # Validate email uniqueness if changed (synchronous)
            if form.email.data != current_user.email:
                existing_user = user_repo.get_user_by_email(form.email.data)
                if existing_user:
                    form.email.errors.append(
                        "That email is taken. Please choose a different one."
                    )
                    image_file = url_for(
                        "static", filename="profile_pics/" + current_user.image_file
                    )
                    return render_template(
                        "account.html",
                        title="Account",
                        image_file=image_file,
                        form=form,
                    )

            update_data = {}
            if form.picture.data:
                picture_file = save_picture(form.picture.data)
                update_data["image_file"] = picture_file
            update_data["username"] = form.username.data
            update_data["email"] = form.email.data

            # Update user via repository
            updated_user = user_repo.update_user(current_user.id, **update_data)
            if updated_user:
                # Update current_user object for Flask-Login
                # Note: Flask-Login will reload user on next request via user_loader
                flash("Your account has been updated!", "success")
                return redirect(url_for("users.account"))
            else:
                flash("Failed to update account. Please try again.", "danger")
        except Exception as e:
            flash(f"An error occurred: {str(e)}", "danger")
            current_app.logger.error(f"Account update error: {e}", exc_info=True)
    elif request.method == "GET":
        form.username.data = current_user.username
        form.email.data = current_user.email
    image_file = url_for("static", filename="profile_pics/" + current_user.image_file)
    return render_template(
        "account.html", title="Account", image_file=image_file, form=form
    )


@users.route("/reset_password", methods=["GET", "POST"])
def reset_request():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))
    form = RequestResetForm()
    if form.validate_on_submit():
        try:
            user = user_repo.get_user_by_email(form.email.data)
            if user:
                send_reset_email(user)
            # Always show success message for security (don't reveal if email exists)
            flash(
                "An email has been sent with instructions to reset your password.",
                "info",
            )
            return redirect(url_for("users.login"))
        except Exception as e:
            flash("An error occurred. Please try again later.", "danger")
            current_app.logger.error(
                f"Password reset request error: {e}", exc_info=True
            )
    return render_template("reset_request.html", title="Reset Password", form=form)


@users.route("/reset_password/<token>", methods=["GET", "POST"])
def reset_token(token):
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))
    try:
        # For sync routes, we need a sync version of verify_reset_token
        from flask import current_app
        from itsdangerous import URLSafeTimedSerializer as Serializer
        from db.flask_session import get_sync_session
        from sqlalchemy import select

        s = Serializer(current_app.config["SECRET_KEY"])
        try:
            user_id = s.loads(token, max_age=3600)["user_id"]  # Token expires in 1 hour
        except (BadSignature, SignatureExpired, KeyError) as e:
            # Token is invalid, expired, or missing user_id
            current_app.logger.debug(f"Token validation failed: {e}")
            user = None
        else:
            with get_sync_session() as session:
                result = session.execute(select(User).where(User.id == user_id))
                user = result.scalar_one_or_none()

        if user is None:
            flash("That is an invalid or expired token", "warning")
            return redirect(url_for("users.reset_request"))
    except Exception as e:
        flash("Invalid reset token.", "warning")
        current_app.logger.error(f"Token verification error: {e}", exc_info=True)
        return redirect(url_for("users.reset_request"))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        try:
            # Update password via repository
            user_repo.update_user(user.id, password=form.password.data)
            flash(
                "Your password has been updated! You are now able to log in", "success"
            )
            return redirect(url_for("users.login"))
        except Exception as e:
            flash(
                "An error occurred while updating your password. Please try again.",
                "danger",
            )
            current_app.logger.error(f"Password reset error: {e}", exc_info=True)
    return render_template("reset_token.html", title="Reset Password", form=form)


@users.route("/dashboard")
@login_required
def dashboard():
    """User dashboard showing flights and stats"""
    # Get user's flights from database
    from db.flask_session import get_sync_session
    from db.models import Flight
    from sqlalchemy import select, func, desc

    with get_sync_session() as session:
        # Get total flight count
        total_flights_result = session.execute(
            select(func.count(Flight.id)).where(Flight.user_id == current_user.id)
        )
        total_flights = total_flights_result.scalar() or 0

        # Get recent flights (last 10)
        flights_result = session.execute(
            select(Flight)
            .where(Flight.user_id == current_user.id)
            .order_by(desc(Flight.started_at))
            .limit(10)
        )
        flights = flights_result.scalars().all()

    from config import settings

    return render_template(
        "dashboard.html",
        title="Dashboard",
        user=current_user,
        flights=flights,
        total_flights=total_flights,
        google_javascript_api_key=settings.google_javascript_api_key,
    )


@users.route("/api/telemetry/latest")
@login_required
def get_latest_telemetry():
    """Get the latest telemetry data for the user's most recent active flight - optimized query"""
    with get_sync_session() as session:
        # Optimized: Get flight and latest telemetry in a single query with join

        # Get the most recent active flight for the user
        flight_result = session.execute(
            select(Flight)
            .where(Flight.user_id == current_user.id)
            .where(Flight.status == "in_progress")
            .order_by(desc(Flight.started_at))
            .limit(1)
        )
        flight = flight_result.scalar_one_or_none()

        if not flight:
            # If no active flight, get the most recent flight (any status)
            flight_result = session.execute(
                select(Flight)
                .where(Flight.user_id == current_user.id)
                .order_by(desc(Flight.started_at))
                .limit(1)
            )
            flight = flight_result.scalar_one_or_none()

        if not flight:
            return jsonify({"error": "No flight found", "telemetry": None}), 404

        # Get the latest telemetry record for this flight (optimized with index)
        telemetry_result = session.execute(
            select(TelemetryRecord)
            .where(TelemetryRecord.flight_id == flight.id)
            .order_by(desc(TelemetryRecord.created_at))
            .limit(1)
        )
        telemetry = telemetry_result.scalar_one_or_none()

        if not telemetry:
            return (
                jsonify(
                    {
                        "error": "No telemetry data available",
                        "telemetry": None,
                        "flight_id": flight.id,
                    }
                ),
                404,
            )

        # Return telemetry data with home location (from flight start coordinates)
        return jsonify(
            {
                "telemetry": {
                    "altitude": telemetry.alt,
                    "latitude": telemetry.lat,
                    "longitude": telemetry.lon,
                    "battery_percentage": (
                        telemetry.battery_remaining
                        if telemetry.battery_remaining is not None
                        else None
                    ),
                    "heading": telemetry.heading,
                    "groundspeed": telemetry.groundspeed,
                    "mode": telemetry.mode,
                    "battery_voltage": telemetry.battery_voltage,
                    "battery_current": telemetry.battery_current,
                    "timestamp": (
                        telemetry.created_at.isoformat()
                        if telemetry.created_at
                        else None
                    ),
                },
                "flight_id": flight.id,
                "flight_status": flight.status,
                "home_location": (
                    {
                        "lat": flight.start_lat,
                        "lon": flight.start_lon,
                        "alt": flight.start_alt,
                    }
                    if flight
                    else None
                ),
            }
        )


@users.route("/api/telemetry/history")
@login_required
def get_telemetry_history():
    """Get recent telemetry history for graphing (last N records) - optimized"""
    limit = request.args.get("limit", 100, type=int)
    flight_id = request.args.get("flight_id", type=int)

    # Limit max records to prevent excessive queries
    limit = min(limit, 1000)

    with get_sync_session() as session:
        # If flight_id provided, use it; otherwise get most recent flight
        if not flight_id:
            flight_result = session.execute(
                select(Flight)
                .where(Flight.user_id == current_user.id)
                .order_by(desc(Flight.started_at))
                .limit(1)
            )
            flight = flight_result.scalar_one_or_none()
            if not flight:
                return jsonify({"error": "No flight found", "data": []}), 404
            flight_id = flight.id

        # Get recent telemetry records (optimized with index on flight_id, created_at)
        telemetry_result = session.execute(
            select(TelemetryRecord)
            .where(TelemetryRecord.flight_id == flight_id)
            .order_by(desc(TelemetryRecord.created_at))
            .limit(limit)
        )
        telemetry_records = list(telemetry_result.scalars().all())

        # Reverse to get chronological order
        telemetry_records = list(reversed(telemetry_records))

        data = {
            "timestamps": [
                t.created_at.isoformat() if t.created_at else None
                for t in telemetry_records
            ],
            "altitude": [t.alt for t in telemetry_records],
            "latitude": [t.lat for t in telemetry_records],
            "longitude": [t.lon for t in telemetry_records],
            "battery_percentage": [
                t.battery_remaining if t.battery_remaining is not None else None
                for t in telemetry_records
            ],
            "battery_voltage": [
                t.battery_voltage if t.battery_voltage is not None else None
                for t in telemetry_records
            ],
            "battery_current": [
                t.battery_current if t.battery_current is not None else None
                for t in telemetry_records
            ],
            "speed": [t.groundspeed for t in telemetry_records],
            "heading": [t.heading for t in telemetry_records],
        }

        return jsonify(
            {"flight_id": flight_id, "count": len(telemetry_records), "data": data}
        )


@users.route("/api/commands", methods=["POST"])
@login_required
def send_command():
    """Send command to drone"""
    from flask import request
    import logging
    from flask_app.app.dashboard.drone_command_handler import get_command_handler

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    command = data.get("command")
    params = data.get("params", {})

    if not command:
        return jsonify({"error": "No command provided"}), 400

    # Log the command
    logging.info(
        f"User {current_user.id} sent command: {command} with params: {params}"
    )

    # Map dashboard commands to drone commands
    command_mapping = {
        "ARM": "ARM",
        "DISARM": "DISARM",
        "TAKEOFF": "TAKEOFF",
        "LAND": "LAND",
        "RTL": "RTL",
        "HOLD": "HOLD",
        "EMERGENCY_STOP": "EMERGENCY_STOP",
        "SET_MODE": "SET_MODE",
    }

    drone_command = command_mapping.get(command, command)

    # Handle specific commands with parameters
    if command == "TAKEOFF" and "altitude" not in params:
        params["altitude"] = 10.0  # Default takeoff altitude

    if command == "SET_MODE" and "mode" in params:
        drone_command = "SET_MODE"

    # Send command via MQTT
    try:
        command_handler = get_command_handler()
        success = command_handler.send_command(drone_command, params)

        if success:
            return jsonify(
                {
                    "status": "success",
                    "message": f"Command '{command}' sent successfully",
                    "command": command,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
        else:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Failed to send command '{command}'",
                        "command": command,
                    }
                ),
                500,
            )
    except Exception as e:
        logging.error(f"Error sending command: {e}")
        return (
            jsonify(
                {
                    "status": "error",
                    "message": f"Error sending command: {str(e)}",
                    "command": command,
                }
            ),
            500,
        )


@users.route("/api/video/stream")
@login_required
def get_video_stream():
    """Get video stream URL"""
    from config import settings

    # Check if video is enabled
    if not settings.drone_video_enabled:
        return (
            jsonify({"error": "Video streaming is disabled", "stream_url": None}),
            404,
        )

    # Determine video stream URL
    stream_url = None

    if settings.raspberry_camera_enabled and settings.rasperry_ip:
        # Raspberry Pi camera stream
        stream_url = (
            f"http://{settings.rasperry_ip}:{settings.rasperry_streaming_port}/stream"
        )
    elif hasattr(settings, "drone_video_source") and settings.drone_video_source:
        # Direct video source
        stream_url = settings.drone_video_source
    else:
        # Default to local stream
        stream_url = "/video_feed"

    return jsonify({"stream_url": stream_url, "enabled": True})


@users.route("/video_feed")
@login_required
def video_feed():
    """Video streaming route (placeholder - needs actual video stream implementation)"""
    from flask import Response

    # TODO: Implement actual video streaming
    # This would use OpenCV or similar to stream video frames
    return Response("Video stream not yet implemented", mimetype="text/plain")


@users.route("/api/flight/start", methods=["POST"])
@login_required
def start_flight_task():
    """Start flight task with coordinates from map - with validation"""
    from flask import request
    from flask_app.app.flight_task_runner import start_flight_task_async
    from utils.geo import haversine_km
    import logging

    data = request.get_json()

    if not data:
        return jsonify({"error": "No data provided"}), 400

    # Get coordinates from request
    start_lat = data.get("start_lat")
    start_lon = data.get("start_lon")
    start_alt = data.get("start_alt", 35.0)
    dest_lat = data.get("dest_lat")
    dest_lon = data.get("dest_lon")
    dest_alt = data.get("dest_alt", 35.0)

    # Validate coordinates exist
    if start_lat is None or start_lon is None or dest_lat is None or dest_lon is None:
        return (
            jsonify(
                {
                    "error": "Missing coordinates",
                    "message": "Please set both start and end points on the map",
                }
            ),
            400,
        )

    # Validate coordinate ranges
    try:
        start_lat = float(start_lat)
        start_lon = float(start_lon)
        start_alt = float(start_alt)
        dest_lat = float(dest_lat)
        dest_lon = float(dest_lon)
        dest_alt = float(dest_alt)
    except (ValueError, TypeError):
        return (
            jsonify(
                {
                    "error": "Invalid coordinates",
                    "message": "Coordinates must be valid numbers",
                }
            ),
            400,
        )

    # Validate latitude/longitude ranges
    if not (-90.0 <= start_lat <= 90.0) or not (-90.0 <= dest_lat <= 90.0):
        return (
            jsonify(
                {
                    "error": "Invalid latitude",
                    "message": "Latitude must be between -90 and 90 degrees",
                }
            ),
            400,
        )

    if not (-180.0 <= start_lon <= 180.0) or not (-180.0 <= dest_lon <= 180.0):
        return (
            jsonify(
                {
                    "error": "Invalid longitude",
                    "message": "Longitude must be between -180 and 180 degrees",
                }
            ),
            400,
        )

    # Validate altitude
    if start_alt < 0 or dest_alt < 0:
        return (
            jsonify(
                {
                    "error": "Invalid altitude",
                    "message": "Altitude must be positive",
                }
            ),
            400,
        )

    # Calculate and validate distance
    distance_km = haversine_km(start_lat, start_lon, dest_lat, dest_lon)
    if distance_km > 100:  # Max 100km flight
        return (
            jsonify(
                {
                    "error": "Distance too large",
                    "message": f"Flight distance ({distance_km:.2f} km) exceeds maximum (100 km)",
                    "distance_km": round(distance_km, 2),
                }
            ),
            400,
        )

    if distance_km < 0.01:  # Min 10m flight
        return (
            jsonify(
                {
                    "error": "Distance too small",
                    "message": "Start and end points are too close together",
                    "distance_km": round(distance_km, 2),
                }
            ),
            400,
        )

    try:
        # Start flight task
        success, message = start_flight_task_async(
            start_lat=start_lat,
            start_lon=start_lon,
            start_alt=start_alt,
            dest_lat=dest_lat,
            dest_lon=dest_lon,
            dest_alt=dest_alt,
            user_id=current_user.id,
        )

        if success:
            logging.info(
                f"User {current_user.id} started flight task: ({start_lat}, {start_lon}) -> ({dest_lat}, {dest_lon}), distance: {distance_km:.2f} km"
            )
            return jsonify(
                {
                    "status": "success",
                    "message": message,
                    "start": {"lat": start_lat, "lon": start_lon, "alt": start_alt},
                    "dest": {"lat": dest_lat, "lon": dest_lon, "alt": dest_alt},
                    "distance_km": round(distance_km, 2),
                }
            )
        else:
            logging.error(f"Failed to start flight task: {message}")
            return jsonify({"status": "error", "message": message}), 500

    except Exception as e:
        logging.error(f"Error starting flight task: {e}", exc_info=True)
        return (
            jsonify(
                {"status": "error", "message": f"Error starting flight task: {str(e)}"}
            ),
            500,
        )


@users.route("/api/flight/stop", methods=["POST"])
@login_required
def stop_flight_task():
    """Stop the running flight task"""
    from flask_app.app.flight_task_runner import stop_flight_task
    import logging

    try:
        success, message = stop_flight_task()
        if success:
            logging.info(f"User {current_user.id} stopped flight task")
            return jsonify({"status": "success", "message": message})
        else:
            return jsonify({"status": "error", "message": message}), 400
    except Exception as e:
        logging.error(f"Error stopping flight task: {e}", exc_info=True)
        return (
            jsonify(
                {"status": "error", "message": f"Error stopping flight task: {str(e)}"}
            ),
            500,
        )


@users.route("/api/flight/status")
@login_required
def get_flight_task_status():
    """Get status of flight task"""
    from flask_app.app.flight_task_runner import is_flight_task_running
    from config import settings

    return jsonify(
        {
            "running": is_flight_task_running(),
            "connection_string": settings.drone_conn,
            "connection_info": "Check logs for connection details",
        }
    )


@users.route("/api/drone/connection/test")
@login_required
def test_drone_connection():
    """Test drone connection without starting a flight"""
    from config import settings
    import logging
    import socket

    connection_info = {
        "connection_string": settings.drone_conn,
        "heartbeat_timeout": settings.heartbeat_timeout,
    }

    # Check if it's a TCP connection and test the port
    if settings.drone_conn.startswith("tcp:"):
        try:
            # Parse host:port from connection string
            parts = settings.drone_conn.replace("tcp:", "").split(":")
            if len(parts) == 2:
                try:
                    host, port = parts[0], int(parts[1])
                    connection_info["host"] = host
                    connection_info["port"] = port
                except (ValueError, IndexError) as e:
                    connection_info["parse_error"] = f"Invalid port format: {str(e)}"
                    return jsonify(connection_info)

                # Test TCP connection (host and port are now defined)
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(2)
                    result = sock.connect_ex(
                        (connection_info["host"], connection_info["port"])
                    )
                    sock.close()
                    if result == 0:
                        connection_info["tcp_port_open"] = True
                    else:
                        connection_info["tcp_port_open"] = False
                        connection_info["tcp_error"] = (
                            f"Port {connection_info.get('port', 'unknown')} is not accessible"
                        )
                except Exception as e:
                    connection_info["tcp_port_open"] = False
                    connection_info["tcp_error"] = str(e)
        except Exception as e:
            connection_info["parse_error"] = str(e)

    try:
        from drone.mavlink_drone import MavlinkDrone

        logging.info(f"Testing drone connection to: {settings.drone_conn}")
        drone = MavlinkDrone(
            settings.drone_conn,
            heartbeat_timeout=settings.heartbeat_timeout,
            baud_rate=settings.drone_baud_rate,
        )

        # Try to connect (this will raise an exception if it fails)
        drone.connect()

        # Get connection status
        status = drone.get_connection_status()

        # Close connection
        drone.close()

        return jsonify(
            {
                "status": "success",
                "message": "Successfully connected to drone",
                "connection_info": connection_info,
                "details": status,
            }
        )

    except ConnectionError as e:
        error_msg = str(e)
        logging.error(f"Drone connection test failed: {error_msg}", exc_info=True)
        return (
            jsonify(
                {
                    "status": "error",
                    "message": f"Failed to connect to drone: {error_msg}",
                    "connection_info": connection_info,
                    "suggestions": [
                        "Check if drone is powered on",
                        "Verify connection string is correct",
                        "For TCP: Ensure MAVProxy or SITL is running and listening on the port",
                        "For Serial: Check device permissions (may need to add user to dialout group)",
                        "Check firewall settings if connecting over network",
                    ],
                }
            ),
            500,
        )
    except Exception as e:
        error_msg = str(e)
        logging.error(f"Drone connection test failed: {error_msg}", exc_info=True)
        return (
            jsonify(
                {
                    "status": "error",
                    "message": f"Unexpected error during connection test: {error_msg}",
                    "connection_info": connection_info,
                    "suggestions": [
                        "Check drone.log file for detailed error messages",
                        "Verify connection string format",
                        "Ensure all required dependencies are installed",
                    ],
                }
            ),
            500,
        )


@users.route("/api/drone/connection/info")
@login_required
def get_drone_connection_info():
    """Get current drone connection configuration"""
    from config import settings

    return jsonify(
        {
            "connection_string": settings.drone_conn,
            "heartbeat_timeout": settings.heartbeat_timeout,
            "connection_type": (
                "TCP"
                if settings.drone_conn.startswith("tcp:")
                else (
                    "UDP"
                    if settings.drone_conn.startswith("udp:")
                    else "Serial" if "/dev/" in settings.drone_conn else "Unknown"
                )
            ),
            "environment_variables": {
                "DRONE_CONNECTION_RASPI": os.getenv("DRONE_CONNECTION_RASPI"),
                "DRONE_CONNECTION_SITL": os.getenv("DRONE_CONNECTION_SITL"),
            },
        }
    )


@users.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    """Settings page for configuring application variables"""
    try:
        form = SettingsForm()
    except Exception as e:
        current_app.logger.error(f"Error creating SettingsForm: {e}", exc_info=True)
        flash(f"Error loading settings form: {str(e)}", "danger")
        return redirect(url_for("users.dashboard"))

    if form.validate_on_submit():
        try:
            # Get form data and convert to dictionary
            config_data = {}

            # Google Maps
            if form.google_maps_key.data:
                config_data["google_maps_key"] = form.google_maps_key.data
            if form.google_javascript_api_key.data:
                config_data["google_javascript_api_key"] = (
                    form.google_javascript_api_key.data
                )

            # LLM Settings
            if form.llm_provider.data:
                config_data["llm_provider"] = form.llm_provider.data
            if form.llm_api_base.data:
                config_data["llm_api_base"] = form.llm_api_base.data
            if form.llm_api_key.data:
                config_data["llm_api_key"] = form.llm_api_key.data
            if form.llm_model.data:
                config_data["llm_model"] = form.llm_model.data

            # MQTT Settings
            if form.mqtt_broker.data:
                config_data["mqtt_broker"] = form.mqtt_broker.data
            if form.mqtt_port.data is not None:
                config_data["mqtt_port"] = form.mqtt_port.data
            if form.mqtt_user.data:
                config_data["mqtt_user"] = form.mqtt_user.data
            if form.mqtt_pass.data:
                config_data["mqtt_pass"] = form.mqtt_pass.data
            if form.opcua_endpoint.data:
                config_data["opcua_endpoint"] = form.opcua_endpoint.data

            # Drone Connection
            if form.drone_conn.data:
                config_data["drone_conn"] = form.drone_conn.data
            if form.drone_conn_mavproxy.data:
                config_data["drone_conn_mavproxy"] = form.drone_conn_mavproxy.data
            if form.drone_baud_rate.data is not None:
                config_data["drone_baud_rate"] = form.drone_baud_rate.data

            # Telemetry
            if form.telem_log_interval_sec.data is not None:
                config_data["telem_log_interval_sec"] = form.telem_log_interval_sec.data
            if form.telemetry_topic.data:
                config_data["telemetry_topic"] = form.telemetry_topic.data

            # Video Settings
            config_data["drone_video_enabled"] = form.drone_video_enabled.data
            if form.drone_video_width.data is not None:
                config_data["drone_video_width"] = form.drone_video_width.data
            if form.drone_video_height.data is not None:
                config_data["drone_video_height"] = form.drone_video_height.data
            if form.drone_video_fps.data is not None:
                config_data["drone_video_fps"] = form.drone_video_fps.data
            if form.drone_video_timeout.data is not None:
                config_data["drone_video_timeout"] = form.drone_video_timeout.data
            if form.drone_video_fallback.data:
                config_data["drone_video_fallback"] = form.drone_video_fallback.data
            config_data["drone_video_save_stream"] = form.drone_video_save_stream.data
            if form.drone_video_save_path.data:
                config_data["drone_video_save_path"] = form.drone_video_save_path.data

            # Battery & Flight Parameters
            if form.battery_capacity_wh.data is not None:
                config_data["battery_capacity_wh"] = form.battery_capacity_wh.data
            if form.cruise_power_w.data is not None:
                config_data["cruise_power_w"] = form.cruise_power_w.data
            if form.cruise_speed_mps.data is not None:
                config_data["cruise_speed_mps"] = form.cruise_speed_mps.data
            if form.energy_reserve_frac.data is not None:
                config_data["energy_reserve_frac"] = form.energy_reserve_frac.data
            if form.heartbeat_timeout.data is not None:
                config_data["heartbeat_timeout"] = form.heartbeat_timeout.data
            config_data["enforce_preflight_range"] = form.enforce_preflight_range.data

            # Raspberry Pi Settings
            if form.rasperry_ip.data:
                config_data["rasperry_ip"] = form.rasperry_ip.data
            if form.rasperry_user.data:
                config_data["rasperry_user"] = form.rasperry_user.data
            if form.rasperry_host.data:
                config_data["rasperry_host"] = form.rasperry_host.data
            if form.rasperry_password.data:
                config_data["rasperry_password"] = form.rasperry_password.data
            if form.rasperry_streaming_script_path.data:
                config_data["rasperry_streaming_script_path"] = (
                    form.rasperry_streaming_script_path.data
                )
            if form.ssh_key_path.data:
                config_data["ssh_key_path"] = form.ssh_key_path.data
            config_data["raspberry_camera_enabled"] = form.raspberry_camera_enabled.data
            if form.rasperry_streaming_port.data is not None:
                config_data["rasperry_streaming_port"] = (
                    form.rasperry_streaming_port.data
                )

            # Database Settings
            if form.db_pool_size.data is not None:
                config_data["db_pool_size"] = form.db_pool_size.data
            if form.db_max_overflow.data is not None:
                config_data["db_max_overflow"] = form.db_max_overflow.data
            if form.db_pool_recycle.data is not None:
                config_data["db_pool_recycle"] = form.db_pool_recycle.data
            if form.db_pool_timeout.data is not None:
                config_data["db_pool_timeout"] = form.db_pool_timeout.data
            config_data["db_pool_pre_ping"] = form.db_pool_pre_ping.data
            config_data["db_echo"] = form.db_echo.data
            if form.database_url.data:
                config_data["database_url"] = form.database_url.data
            if form.db_optimize_interval.data is not None:
                config_data["db_optimize_interval"] = form.db_optimize_interval.data

            # Flask Settings
            if form.flask_secret_key.data:
                config_data["flask_secret_key"] = form.flask_secret_key.data
            if form.mail_server.data:
                config_data["mail_server"] = form.mail_server.data
            if form.mail_port.data is not None:
                config_data["mail_port"] = form.mail_port.data
            config_data["mail_use_tls"] = form.mail_use_tls.data
            if form.mail_username.data:
                config_data["mail_username"] = form.mail_username.data
            if form.mail_password.data:
                config_data["mail_password"] = form.mail_password.data

            # Save configuration for current user
            config_repo.create_or_update_configuration(
                user_id=current_user.id, **config_data
            )

            flash("Settings saved successfully!", "success")
            return redirect(url_for("users.settings"))

        except Exception as e:
            flash(f"An error occurred while saving settings: {str(e)}", "danger")
            current_app.logger.error(f"Settings save error: {e}", exc_info=True)

    elif request.method == "GET":
        # Load existing configuration
        try:
            config = config_repo.get_configuration(user_id=current_user.id)
        except Exception as e:
            current_app.logger.error(f"Error loading configuration: {e}", exc_info=True)
            flash(
                f"Error loading settings: {str(e)}. The settings table may need to be created. Please restart the application.",
                "warning",
            )
            config = None
        if config:
            # Populate form with existing values from database
            form.google_maps_key.data = config.google_maps_key
            form.google_javascript_api_key.data = config.google_javascript_api_key
            form.llm_provider.data = config.llm_provider
            form.llm_api_base.data = config.llm_api_base
            form.llm_api_key.data = config.llm_api_key
            form.llm_model.data = config.llm_model
            form.mqtt_broker.data = config.mqtt_broker
            form.mqtt_port.data = config.mqtt_port
            form.mqtt_user.data = config.mqtt_user
            form.mqtt_pass.data = config.mqtt_pass
            form.opcua_endpoint.data = config.opcua_endpoint
            form.drone_conn.data = config.drone_conn
            form.drone_conn_mavproxy.data = config.drone_conn_mavproxy
            form.drone_baud_rate.data = config.drone_baud_rate
            form.telem_log_interval_sec.data = config.telem_log_interval_sec
            form.telemetry_topic.data = config.telemetry_topic
            form.drone_video_enabled.data = (
                config.drone_video_enabled
                if config.drone_video_enabled is not None
                else True
            )
            form.drone_video_width.data = config.drone_video_width
            form.drone_video_height.data = config.drone_video_height
            form.drone_video_fps.data = config.drone_video_fps
            form.drone_video_timeout.data = config.drone_video_timeout
            form.drone_video_fallback.data = config.drone_video_fallback
            form.drone_video_save_stream.data = (
                config.drone_video_save_stream
                if config.drone_video_save_stream is not None
                else True
            )
            form.drone_video_save_path.data = config.drone_video_save_path
            form.battery_capacity_wh.data = config.battery_capacity_wh
            form.cruise_power_w.data = config.cruise_power_w
            form.cruise_speed_mps.data = config.cruise_speed_mps
            form.energy_reserve_frac.data = config.energy_reserve_frac
            form.heartbeat_timeout.data = config.heartbeat_timeout
            form.enforce_preflight_range.data = (
                config.enforce_preflight_range
                if config.enforce_preflight_range is not None
                else True
            )
            form.rasperry_ip.data = config.rasperry_ip
            form.rasperry_user.data = config.rasperry_user
            form.rasperry_host.data = config.rasperry_host
            form.rasperry_password.data = config.rasperry_password
            form.rasperry_streaming_script_path.data = (
                config.rasperry_streaming_script_path
            )
            form.ssh_key_path.data = config.ssh_key_path
            form.raspberry_camera_enabled.data = (
                config.raspberry_camera_enabled
                if config.raspberry_camera_enabled is not None
                else True
            )
            form.rasperry_streaming_port.data = config.rasperry_streaming_port
            form.db_pool_size.data = config.db_pool_size
            form.db_max_overflow.data = config.db_max_overflow
            form.db_pool_recycle.data = config.db_pool_recycle
            form.db_pool_timeout.data = config.db_pool_timeout
            form.db_pool_pre_ping.data = (
                config.db_pool_pre_ping if config.db_pool_pre_ping is not None else True
            )
            form.db_echo.data = config.db_echo if config.db_echo is not None else False
            form.database_url.data = config.database_url
            form.db_optimize_interval.data = config.db_optimize_interval
            form.flask_secret_key.data = config.flask_secret_key
            form.mail_server.data = config.mail_server
            form.mail_port.data = config.mail_port
            form.mail_use_tls.data = (
                config.mail_use_tls if config.mail_use_tls is not None else True
            )
            form.mail_username.data = config.mail_username
            form.mail_password.data = config.mail_password
        # If no config exists, form fields remain empty (no defaults loaded)

    return render_template("settings.html", title="Settings", form=form)


@users.route("/api/flight/stats")
@login_required
def get_flight_stats():
    """Get flight statistics for the user - optimized with single query"""
    with get_sync_session() as session:
        from utils.geo import haversine_km

        # Get all completed flights for the user
        flights_result = session.execute(
            select(Flight)
            .where(Flight.user_id == current_user.id)
            .where(Flight.status == "completed")
        )
        flights = flights_result.scalars().all()

        # Calculate total flight time
        total_seconds = sum(
            (flight.ended_at - flight.started_at).total_seconds()
            for flight in flights
            if flight.ended_at and flight.started_at
        )

        # Get max altitude and calculate total distance from telemetry
        max_alt = 0.0
        total_distance_km = 0.0

        for flight in flights:
            # Get telemetry records for this flight, ordered by time
            telemetry_result = session.execute(
                select(TelemetryRecord)
                .where(TelemetryRecord.flight_id == flight.id)
                .order_by(TelemetryRecord.created_at)
            )
            telemetry_records = list(telemetry_result.scalars().all())

            if telemetry_records:
                # Update max altitude
                try:
                    flight_max_alt = max(t.alt for t in telemetry_records)
                    max_alt = max(max_alt, flight_max_alt)
                except ValueError:
                    # Empty sequence or all None values
                    pass

                # Calculate distance traveled by summing distances between consecutive points
                for i in range(1, len(telemetry_records)):
                    prev = telemetry_records[i - 1]
                    curr = telemetry_records[i]
                    distance = haversine_km(prev.lat, prev.lon, curr.lat, curr.lon)
                    total_distance_km += distance

        # Format total time
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)

        # Calculate max speed
        max_speed = 0.0
        avg_duration_minutes = 0.0

        for flight in flights:
            telemetry_result = session.execute(
                select(TelemetryRecord).where(TelemetryRecord.flight_id == flight.id)
            )
            telemetry_records = list(telemetry_result.scalars().all())

            if telemetry_records:
                try:
                    flight_max_speed = max(t.groundspeed for t in telemetry_records)
                    max_speed = max(max_speed, flight_max_speed)
                except ValueError:
                    # Empty sequence or all None values
                    pass

                if flight.ended_at and flight.started_at:
                    duration_minutes = (
                        flight.ended_at - flight.started_at
                    ).total_seconds() / 60
                    avg_duration_minutes += duration_minutes

        if len(flights) > 0:
            avg_duration_minutes = avg_duration_minutes / len(flights)

        return jsonify(
            {
                "total_flight_time": f"{hours}h {minutes}m",
                "total_flight_time_seconds": total_seconds,
                "max_altitude": round(max_alt, 2),
                "total_distance": round(total_distance_km, 2),  # in km
                "max_speed": round(max_speed, 2),
                "avg_duration": round(avg_duration_minutes, 1),
            }
        )
