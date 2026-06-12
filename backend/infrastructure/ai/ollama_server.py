from __future__ import annotations

import shutil
import subprocess
import urllib.error
import urllib.request
from urllib.parse import urlparse


class OllamaServerManager:
    def __init__(self) -> None:
        self._process: subprocess.Popen[bytes] | None = None

    def is_reachable(self, api_base: str) -> bool:
        url = f"{api_base.rstrip('/')}/api/tags"
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                return response.status == 200
        except (urllib.error.URLError, TimeoutError, ValueError):
            return False

    def ensure_running(self, api_base: str = "http://localhost:11434") -> None:
        if self.is_reachable(api_base):
            return

        process = self._process
        if process is not None and process.poll() is None:
            return

        binary = shutil.which("ollama")
        if binary is None:
            raise RuntimeError("ollama binary not found on PATH.")

        self._process = subprocess.Popen(
            [binary, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    def stop(self) -> None:
        process = self._process
        if process is None or process.poll() is not None:
            self._process = None
            return
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        self._process = None


def default_ollama_api_base(api_base: str) -> str:
    parsed = urlparse(api_base.strip() or "http://localhost:11434")
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return "http://localhost:11434"


shared_ollama_server = OllamaServerManager()
