from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (
    StringField,
    PasswordField,
    SubmitField,
    BooleanField,
    IntegerField,
    FloatField,
)
from wtforms.validators import (
    DataRequired,
    Length,
    Email,
    EqualTo,
    ValidationError,
    Optional,
    NumberRange,
)
from db.repository import UserRepository
import asyncio

# Create repository instance for form validators
_user_repo = UserRepository()


def _run_async(async_func, *args, **kwargs):
    """Helper to run async code in sync context (form validators)

    Args:
        async_func: The async function to call (not a coroutine!)
        *args, **kwargs: Arguments to pass to the async function
    """
    import concurrent.futures

    def _run_in_thread():
        """Run async function in a new event loop in a thread"""
        # Create a completely new event loop for this thread
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        try:
            # Create a fresh coroutine from the function
            coro = async_func(*args, **kwargs)
            return new_loop.run_until_complete(coro)
        finally:
            # Clean up all pending tasks
            try:
                # Cancel all pending tasks
                pending = asyncio.all_tasks(new_loop)
                for task in pending:
                    task.cancel()
                # Wait for cancellation
                if pending:
                    new_loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
            except Exception:
                pass
            finally:
                new_loop.close()

    try:
        # Try to get the current event loop
        loop = asyncio.get_running_loop()
        # If we get here, loop is running - use thread executor
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(_run_in_thread)
            return future.result(timeout=5)  # 5 second timeout
    except RuntimeError:
        # No running loop - create new one
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            # Still running somehow - use thread
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(_run_in_thread)
                return future.result(timeout=5)
        else:
            # Create fresh coroutine
            coro = async_func(*args, **kwargs)
            return loop.run_until_complete(coro)


class RegistrationForm(FlaskForm):
    username = StringField(
        "Username", validators=[DataRequired(), Length(min=2, max=20)]
    )
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    confirm_password = PasswordField(
        "Confirm Password", validators=[DataRequired(), EqualTo("password")]
    )
    submit = SubmitField("Sign Up")

    # Note: Username and email uniqueness validation moved to route
    # to avoid event loop conflicts with async database operations


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember = BooleanField("Remember Me")
    submit = SubmitField("Login")


class UpdateAccountForm(FlaskForm):
    username = StringField(
        "Username", validators=[DataRequired(), Length(min=2, max=20)]
    )
    email = StringField("Email", validators=[DataRequired(), Email()])
    picture = FileField(
        "Update Profile Picture", validators=[FileAllowed(["jpg", "png"])]
    )
    submit = SubmitField("Update")

    # Note: Username and email uniqueness validation moved to route
    # to avoid event loop conflicts with async database operations


class RequestResetForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    submit = SubmitField("Request Password Reset")

    def validate_email(self, email):
        user = _run_async(_user_repo.get_user_by_email, email.data)
        if user is None:
            raise ValidationError(
                "There is no account with that email. You must register first."
            )


class ResetPasswordForm(FlaskForm):
    password = PasswordField("Password", validators=[DataRequired()])
    confirm_password = PasswordField(
        "Confirm Password", validators=[DataRequired(), EqualTo("password")]
    )
    submit = SubmitField("Reset Password")


class SettingsForm(FlaskForm):
    # Google Maps
    google_maps_key = StringField("Google Maps API Key", validators=[Optional()])
    google_javascript_api_key = StringField(
        "Google Maps JavaScript API Key", validators=[Optional()]
    )

    # LLM Settings
    llm_provider = StringField("LLM Provider", validators=[Optional()])
    llm_api_base = StringField("LLM API Base URL", validators=[Optional()])
    llm_api_key = StringField("LLM API Key", validators=[Optional()])
    llm_model = StringField("LLM Model", validators=[Optional()])

    # MQTT Settings
    mqtt_broker = StringField("MQTT Broker", validators=[Optional()])
    mqtt_port = IntegerField(
        "MQTT Port", validators=[Optional(), NumberRange(min=1, max=65535)]
    )
    mqtt_user = StringField("MQTT Username", validators=[Optional()])
    mqtt_pass = PasswordField("MQTT Password", validators=[Optional()])

    # Drone Connection
    drone_conn = StringField("Drone Connection String", validators=[Optional()])
    drone_conn_mavproxy = StringField(
        "Drone Connection (MAVProxy)", validators=[Optional()]
    )
    drone_baud_rate = IntegerField(
        "Drone Baud Rate", validators=[Optional(), NumberRange(min=9600, max=115200)]
    )

    # Telemetry
    telem_log_interval_sec = FloatField(
        "Telemetry Log Interval (seconds)",
        validators=[Optional(), NumberRange(min=0.1, max=60)],
    )
    telemetry_topic = StringField("Telemetry Topic", validators=[Optional()])

    # Video Settings
    drone_video_enabled = BooleanField("Enable Video Streaming")
    drone_video_width = IntegerField(
        "Video Width", validators=[Optional(), NumberRange(min=320, max=1920)]
    )
    drone_video_height = IntegerField(
        "Video Height", validators=[Optional(), NumberRange(min=240, max=1080)]
    )
    drone_video_fps = IntegerField(
        "Video FPS", validators=[Optional(), NumberRange(min=1, max=60)]
    )
    drone_video_timeout = FloatField(
        "Video Timeout (seconds)", validators=[Optional(), NumberRange(min=1, max=60)]
    )
    drone_video_fallback = StringField("Video Fallback", validators=[Optional()])
    drone_video_save_stream = BooleanField("Save Video Stream")
    drone_video_save_path = StringField("Video Save Path", validators=[Optional()])

    # Battery & Flight Parameters
    battery_capacity_wh = FloatField(
        "Battery Capacity (Wh)", validators=[Optional(), NumberRange(min=0)]
    )
    cruise_power_w = FloatField(
        "Cruise Power (W)", validators=[Optional(), NumberRange(min=0)]
    )
    cruise_speed_mps = FloatField(
        "Cruise Speed (m/s)", validators=[Optional(), NumberRange(min=0)]
    )
    energy_reserve_frac = FloatField(
        "Energy Reserve Fraction", validators=[Optional(), NumberRange(min=0, max=1)]
    )
    heartbeat_timeout = FloatField(
        "Heartbeat Timeout (seconds)",
        validators=[Optional(), NumberRange(min=1, max=60)],
    )
    enforce_preflight_range = BooleanField("Enforce Preflight Range Check")

    # Raspberry Pi Settings
    rasperry_ip = StringField("Raspberry Pi IP", validators=[Optional()])
    rasperry_user = StringField("Raspberry Pi User", validators=[Optional()])
    rasperry_host = StringField("Raspberry Pi Host", validators=[Optional()])
    rasperry_password = PasswordField("Raspberry Pi Password", validators=[Optional()])
    rasperry_streaming_script_path = StringField(
        "Streaming Script Path", validators=[Optional()]
    )
    ssh_key_path = StringField("SSH Key Path", validators=[Optional()])
    raspberry_camera_enabled = BooleanField("Enable Raspberry Pi Camera")
    rasperry_streaming_port = IntegerField(
        "Streaming Port", validators=[Optional(), NumberRange(min=1, max=65535)]
    )

    # Database Settings
    db_pool_size = IntegerField(
        "DB Pool Size", validators=[Optional(), NumberRange(min=1, max=100)]
    )
    db_max_overflow = IntegerField(
        "DB Max Overflow", validators=[Optional(), NumberRange(min=0, max=100)]
    )
    db_pool_recycle = IntegerField(
        "DB Pool Recycle (seconds)",
        validators=[Optional(), NumberRange(min=60, max=86400)],
    )
    db_pool_timeout = IntegerField(
        "DB Pool Timeout (seconds)",
        validators=[Optional(), NumberRange(min=1, max=300)],
    )
    db_pool_pre_ping = BooleanField("DB Pool Pre-ping")
    db_echo = BooleanField("DB Echo (SQL Debug)")
    database_url = StringField("Database URL", validators=[Optional()])
    db_optimize_interval = IntegerField(
        "DB Optimize Interval (seconds)",
        validators=[Optional(), NumberRange(min=60, max=86400)],
    )

    # Flask Settings
    flask_secret_key = PasswordField("Flask Secret Key", validators=[Optional()])
    mail_server = StringField("Mail Server", validators=[Optional()])
    mail_port = IntegerField(
        "Mail Port", validators=[Optional(), NumberRange(min=1, max=65535)]
    )
    mail_use_tls = BooleanField("Mail Use TLS")
    mail_username = StringField("Mail Username", validators=[Optional()])
    mail_password = PasswordField("Mail Password", validators=[Optional()])

    submit = SubmitField("Save Settings")
