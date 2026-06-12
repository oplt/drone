from __future__ import annotations

import re
import shlex
import socket
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from backend.modules.ai.schemas import (
    LlamaCppCommandResponse,
    LlamaCppParsedConfig,
    LlamaCppServerStatus,
    LLMProfile,
)

DEFAULT_LLAMA_API_BASE = "http://127.0.0.1:8080/v1"
SHELL_OPERATOR_RE = re.compile(r"(;|&&|\|\||\||>|<|\$\(|`)")
VALUE_FLAGS = {
    "-m": "model_path",
    "--model": "model_path",
    "--host": "host",
    "--port": "port",
    "-c": "context_window",
    "--ctx-size": "context_window",
    "--context-size": "context_window",
    "-ngl": "gpu_layers",
    "--n-gpu-layers": "gpu_layers",
    "-np": "parallel_slots",
    "--parallel": "parallel_slots",
    "-t": "threads",
    "--threads": "threads",
    "-b": "batch_size",
    "--batch-size": "batch_size",
    "--flash-attn": "flash_attention",
}
EXTRA_VALUE_FLAGS = {"--ubatch-size", "--rope-scaling", "--rope-freq-base", "--rope-freq-scale"}
EXTRA_BOOL_FLAGS = {"--mlock", "--no-mmap", "--cont-batching"}


def parse_llama_cpp_command(command: str) -> LlamaCppCommandResponse:
    if not command.strip():
        raise ValueError("llama.cpp command is required.")
    if SHELL_OPERATOR_RE.search(command):
        raise ValueError("Shell operators are not allowed in managed llama.cpp commands.")

    try:
        argv = shlex.split(command)
    except ValueError as exc:
        raise ValueError(f"Invalid command syntax: {exc}") from exc
    if not argv:
        raise ValueError("llama.cpp command is required.")

    binary = Path(argv[0]).expanduser()
    if binary.name != "llama-server":
        raise ValueError("Managed command must execute llama-server.")
    if not binary.is_absolute():
        found = _resolve_from_path(binary.name)
        if found is None:
            raise ValueError("llama-server binary must be an existing absolute path or on PATH.")
        binary = found
    binary = binary.resolve()
    if not binary.is_file():
        raise ValueError(f"llama-server binary not found: {binary}")

    data: dict[str, object] = {
        "binary_path": str(binary),
        "host": "127.0.0.1",
        "port": 8080,
        "context_window": 8192,
        "gpu_layers": 0,
        "flash_attention": False,
        "parallel_slots": 1,
        "threads": 0,
        "batch_size": 512,
        "extra_allowed_args": [],
    }
    extra: list[str] = []
    index = 1
    while index < len(argv):
        token = argv[index]
        if token in VALUE_FLAGS:
            value = _next_value(argv, index, token)
            key = VALUE_FLAGS[token]
            data[key] = _coerce_value(key, value)
            index += 2
            continue
        if token in EXTRA_VALUE_FLAGS:
            value = _next_value(argv, index, token)
            extra.extend([token, value])
            index += 2
            continue
        if token in EXTRA_BOOL_FLAGS:
            extra.append(token)
            index += 1
            continue
        raise ValueError(f"Unsupported llama-server argument: {token}")

    model_path = Path(str(data.get("model_path") or "")).expanduser()
    if not str(model_path):
        raise ValueError("Managed llama.cpp command must include -m/--model.")
    if not model_path.is_absolute():
        raise ValueError("GGUF model path must be absolute.")
    model_path = model_path.resolve()
    if not model_path.is_file():
        raise ValueError(f"GGUF model not found: {model_path}")
    if model_path.suffix.lower() != ".gguf":
        raise ValueError("Managed llama.cpp model path must end with .gguf.")

    host = str(data["host"])
    port = int(data["port"])
    _validate_host(host)
    if not 1 <= port <= 65535:
        raise ValueError("Managed llama.cpp port is invalid.")

    api_base = f"http://{host}:{port}/v1"
    config = LlamaCppParsedConfig.model_validate(
        {
            **data,
            "model_path": str(model_path),
            "api_base": api_base,
            "extra_allowed_args": extra,
        }
    )
    return LlamaCppCommandResponse(
        command=command,
        config=config,
        summary=_summary(config),
    )


class LlamaCppServerManager:
    def __init__(self) -> None:
        self._process: subprocess.Popen[bytes] | None = None
        self._profile_id: str | None = None
        self._command: list[str] = []

    def is_api_reachable(self, api_base: str) -> bool:
        url = f"{api_base.rstrip('/')}/models"
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                return response.status == 200
        except (urllib.error.URLError, TimeoutError, ValueError):
            return False

    def status(self) -> LlamaCppServerStatus:
        process = self._process
        if process is None:
            return LlamaCppServerStatus(running=False, detail="llama-server not started.")
        return_code = process.poll()
        if return_code is not None:
            return LlamaCppServerStatus(
                running=False,
                profile_id=self._profile_id,
                command=self._command,
                detail=f"llama-server exited with code {return_code}.",
            )
        return LlamaCppServerStatus(
            running=True,
            profile_id=self._profile_id,
            pid=process.pid,
            command=self._command,
            detail="llama-server running.",
        )

    def start(self, profile: LLMProfile) -> LlamaCppServerStatus:
        if profile.provider != "llama_cpp":
            raise ValueError("Profile provider must be llama_cpp.")

        command = profile.llama_command.strip()
        if not command:
            raise ValueError("llama.cpp command is required.")

        parsed = parse_llama_cpp_command(command)
        config = parsed.config
        if self.is_api_reachable(config.api_base):
            return LlamaCppServerStatus(
                running=True,
                profile_id=profile.id,
                command=shlex.split(command),
                detail="llama-server already reachable.",
            )

        current = self.status()
        if current.running and current.profile_id == profile.id:
            return current
        if current.running:
            self.stop()

        validate_start_config(config)
        if _port_in_use(config.host, config.port) and not self.is_api_reachable(config.api_base):
            raise ValueError(f"Port already in use: {config.host}:{config.port}")

        argv = shlex.split(command)
        self._process = subprocess.Popen(
            argv,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        self._profile_id = profile.id
        self._command = argv
        return self.status()

    def restart(self, profile: LLMProfile) -> LlamaCppServerStatus:
        self.stop()
        return self.start(profile)

    def stop(self) -> LlamaCppServerStatus:
        process = self._process
        if process is None or process.poll() is not None:
            self._process = None
            return LlamaCppServerStatus(running=False, detail="llama-server not running.")
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        status = LlamaCppServerStatus(
            running=False,
            profile_id=self._profile_id,
            command=self._command,
            detail="llama-server stopped.",
        )
        self._process = None
        return status


def _build_argv(config: LlamaCppParsedConfig) -> list[str]:
    argv = [
        config.binary_path,
        "-m",
        config.model_path,
        "--host",
        config.host,
        "--port",
        str(config.port),
        "-c",
        str(config.context_window),
        "-ngl",
        str(config.gpu_layers),
        "-np",
        str(config.parallel_slots),
        "-b",
        str(config.batch_size),
    ]
    if config.threads:
        argv.extend(["-t", str(config.threads)])
    argv.extend(["--flash-attn", "on" if config.flash_attention else "off"])
    argv.extend(config.extra_allowed_args)
    return argv


def _coerce_value(key: str, value: str) -> object:
    if key in {"port", "context_window", "gpu_layers", "parallel_slots", "threads", "batch_size"}:
        return int(value)
    if key == "flash_attention":
        normalized = value.lower()
        if normalized not in {"on", "off", "true", "false", "1", "0"}:
            raise ValueError("--flash-attn must be on/off.")
        return normalized in {"on", "true", "1"}
    return value


def _next_value(argv: list[str], index: int, flag: str) -> str:
    if index + 1 >= len(argv):
        raise ValueError(f"{flag} requires a value.")
    value = argv[index + 1]
    if value.startswith("-") and not value[1:].isdigit():
        raise ValueError(f"{flag} requires a value.")
    return value


def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) == 0


def _resolve_from_path(name: str) -> Path | None:
    for raw_dir in __import__("os").environ.get("PATH", "").split(":"):
        candidate = Path(raw_dir) / name
        if candidate.is_file():
            return candidate
    return None


def _summary(config: LlamaCppParsedConfig) -> dict[str, str]:
    return {
        "Binary": config.binary_path,
        "Model file": config.model_path,
        "Server URL": config.api_base,
        "Context window": str(config.context_window),
        "GPU offload": str(config.gpu_layers),
        "Flash attention": "on" if config.flash_attention else "off",
        "Parallel slots": str(config.parallel_slots),
    }


def _validate_host(host: str) -> None:
    if host in {"localhost", "127.0.0.1", "0.0.0.0"}:
        return
    try:
        socket.inet_aton(host)
    except OSError as exc:
        raise ValueError("Managed llama.cpp host is invalid.") from exc


def validate_start_config(config: LlamaCppParsedConfig) -> None:
    binary = Path(config.binary_path).expanduser().resolve()
    model = Path(config.model_path).expanduser().resolve()
    if binary.name != "llama-server" or not binary.is_file():
        raise ValueError(f"llama-server binary not found: {binary}")
    if not model.is_file():
        raise ValueError(f"GGUF model not found: {model}")
    if model.suffix.lower() != ".gguf":
        raise ValueError("Managed llama.cpp model path must end with .gguf.")
    _validate_host(config.host)


shared_llama_cpp_server = LlamaCppServerManager()
