# video/raspberry_camera.py
import asyncio
import paramiko
import logging
from config import settings
import requests


class RaspberryCameraController:
    """Controls Raspberry Pi camera remotely via SSH with process management"""

    def __init__(
        self,
        host=settings.rasperry_ip,
        user=settings.rasperry_user,
        key_path=settings.ssh_key_path,
        script_path=settings.rasperry_streaming_script_path,
        streaming_port=settings.rasperry_streaming_port,
    ):  # ← Streaming port for Flask
        self.host = host
        self.user = user
        self.key_path = key_path
        self.script_path = script_path
        self.streaming_port = streaming_port  # Flask streaming port
        self.is_streaming = False
        self.process_id = None
        self.ssh_client = None
        self.stream_url = f"http://{host}:{streaming_port}"  # Correct URL

    async def _execute_ssh_command(self, command):
        """Execute SSH command and return result"""
        try:
            if (
                not self.ssh_client
                or not self.ssh_client.get_transport()
                or not self.ssh_client.get_transport().is_active()
            ):
                # Reconnect if needed
                self.ssh_client = paramiko.SSHClient()
                self.ssh_client.load_system_host_keys()
                self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                self.ssh_client.connect(
                    hostname=self.host,
                    username=self.user,
                    key_filename=self.key_path,
                    timeout=10,
                )

            stdin, stdout, stderr = self.ssh_client.exec_command(command)
            output = stdout.read().decode().strip()
            error = stderr.read().decode().strip()
            exit_status = stdout.channel.recv_exit_status()

            return exit_status == 0, output, error

        except Exception as e:
            logging.error(f"SSH command failed: {e}")
            return False, "", str(e)

    async def _find_running_camera_process(self):
        """Find if camera stream is already running on Raspberry Pi"""
        # Check for python processes running camera_stream.py
        command = "ps aux | grep '[p]i_camera_server.py' | awk '{print $2}'"  # Updated to match actual script name
        success, output, error = await self._execute_ssh_command(command)

        if success and output:
            pids = output.split()
            if pids:
                return int(pids[0])

        # Also check for Flask server on port
        command = f"ss -tlnp | grep ':{self.streaming_port}' | awk '{{print $6}}' | cut -d',' -f2 | cut -d'=' -f2"
        success, output, error = await self._execute_ssh_command(command)

        if success and output:
            return int(output)

        return None

    async def _kill_existing_stream(self):
        """Kill any existing camera stream process"""
        # Find and kill by process name
        command = "pkill -f 'pi_camera_server.py'"
        await self._execute_ssh_command(command)

        # Kill by port if still running
        command = f"fuser -k {self.streaming_port}/tcp"
        await self._execute_ssh_command(command)

        await asyncio.sleep(1)  # Give time for process to terminate
        return True

    async def verify_server_running(self):
        """Verify the Flask server is actually running with multiple checks"""
        try:
            # Check 1: Process exists
            command = "ps aux | grep '[p]i_camera_server.py'"
            success, output, error = await self._execute_ssh_command(command)

            if not success or not output:
                logging.error("❌ Camera server process not found")
                return False

            logging.info(f"✅ Camera process found: {output[:100]}...")

            # Check 2: Port is listening
            command = f"netstat -tlnp | grep :{self.streaming_port} || ss -tlnp | grep :{self.streaming_port} || lsof -i :{self.streaming_port}"
            success, output, error = await self._execute_ssh_command(command)

            if success and output:
                logging.info(
                    f"✅ Port {self.streaming_port} is listening: {output[:100]}..."
                )
            else:
                logging.error(f"❌ Port {self.streaming_port} is not listening")
                return False

            # Check 3: Check server logs
            command = "tail -20 /tmp/drone_camera.log"
            success, output, error = await self._execute_ssh_command(command)

            if success and output:
                logging.info(f"📋 Server logs:\n{output}")

            return True

        except Exception as e:
            logging.error(f"Server verification error: {e}")
            return False

    async def start_streaming(self):
        """Start camera streaming on Raspberry Pi via SSH"""
        try:
            logging.info(f"🔄 Starting camera streaming on {self.host}...")

            # 1. Check if already running
            existing_pid = await self._find_running_camera_process()
            if existing_pid:
                logging.info(f"📷 Camera stream already running (PID: {existing_pid})")
                self.process_id = existing_pid
                self.is_streaming = True
                return True

            # 2. Kill any existing processes first
            await self._kill_existing_stream()

            # 3. Start new camera stream
            script_dir = (
                self.script_path.rsplit("/", 1)[0] if "/" in self.script_path else "."
            )
            command = f"""
            cd {script_dir}
            nohup python3 pi_camera_server.py > /tmp/drone_camera.log 2>&1 &
            echo $!  # Print the process ID
            """

            logging.info(f"Executing command: {command}")
            success, output, error = await self._execute_ssh_command(command)

            if success and output:
                try:
                    self.process_id = int(output.strip())
                    self.is_streaming = True
                    logging.info(f"✅ Camera process started (PID: {self.process_id})")

                    # Wait for Flask server to start
                    logging.info("⏳ Waiting for server to start...")
                    await asyncio.sleep(7)  # Increased wait time

                    # Verify server is actually running
                    if await self.verify_server_running():
                        logging.info("✅ Server verified as running")

                        # Now try health check with retries
                        max_retries = 3
                        for attempt in range(max_retries):
                            logging.info(
                                f"🔍 Health check attempt {attempt + 1}/{max_retries}"
                            )
                            if await self.check_stream_health():
                                logging.info("✅ Camera stream fully healthy")
                                return True
                            await asyncio.sleep(2)  # Wait between retries

                        logging.warning("⚠️ Server running but health checks failing")
                        return True  # Return true anyway if server is running
                    else:
                        logging.error("❌ Server failed to start")
                        return False

                except ValueError:
                    logging.error(f"❌ Could not parse process ID from: {output}")
                    return False
            else:
                logging.error(f"❌ Failed to start camera: {error}")
                return False

        except Exception as e:
            logging.error(f"❌ SSH connection failed: {e}")
            return False

    async def stop_streaming(self):
        """Stop camera streaming on Raspberry Pi"""
        try:
            logging.info(f"🛑 Stopping camera streaming on {self.host}...")

            if await self._kill_existing_stream():
                self.is_streaming = False
                self.process_id = None
                logging.info("✅ Camera streaming stopped")
                return True
            return False

        except Exception as e:
            logging.error(f"❌ Error stopping camera: {e}")
            return False

    async def check_stream_health(self, timeout=5):
        """Check if camera stream is healthy with better diagnostics"""
        try:
            # Try to connect to multiple endpoints
            endpoints = [
                f"{self.stream_url}/video_feed",
                f"{self.stream_url}/",  # Root endpoint
                f"http://{self.host}:{self.streaming_port}",  # Basic connection
            ]

            for endpoint in endpoints:
                try:
                    logging.debug(f"Trying health check on: {endpoint}")
                    response = await asyncio.wait_for(
                        asyncio.to_thread(requests.get, endpoint, timeout=2),
                        timeout=timeout,
                    )

                    if response.status_code == 200:
                        logging.info(f"✅ Camera stream healthy at {endpoint}")
                        return True

                    logging.debug(
                        f"Endpoint {endpoint} returned status {response.status_code}"
                    )

                except requests.RequestException as e:
                    logging.debug(f"Request to {endpoint} failed: {e}")
                except asyncio.TimeoutError:
                    logging.debug(f"Timeout connecting to {endpoint}")

            return False

        except Exception as e:
            logging.error(f"Health check error: {e}")
            return False

    async def check_health(self):
        """Check overall health of the camera stream"""
        return await self.check_stream_health()

    async def get_stream_url(self):
        """Get the video feed URL"""
        return f"{self.stream_url}/video_feed"

    async def cleanup(self):
        """Clean up SSH connection"""
        if self.ssh_client:
            self.ssh_client.close()
