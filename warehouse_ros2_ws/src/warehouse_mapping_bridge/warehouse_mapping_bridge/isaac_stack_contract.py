from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]


@dataclass(frozen=True)
class StackCommand:
    key: str
    env: str
    description: str
    expected_topics: tuple[str, ...]
    required: bool
    command: str = ""

    @property
    def argv(self) -> list[str]:
        return shlex.split(self.command)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "env": self.env,
            "description": self.description,
            "expected_topics": list(self.expected_topics),
            "required": self.required,
            "configured": bool(self.command.strip()),
            "command": self.command,
        }


def contract_path() -> Path:
    override = os.getenv("WAREHOUSE_ISAAC_STACK_CONTRACT", "").strip()
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parents[1] / "config" / "isaac_stack.yaml"


def _items(payload: dict[str, Any], key: str, *, required: bool) -> list[StackCommand]:
    raw_items = payload.get(key, [])
    if not isinstance(raw_items, list):
        return []
    commands: list[StackCommand] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        env_name = str(raw.get("env") or "").strip()
        command = os.getenv(env_name, "").strip() if env_name else ""
        topics = raw.get("expected_topics", [])
        commands.append(
            StackCommand(
                key=str(raw.get("key") or env_name).strip(),
                env=env_name,
                description=str(raw.get("description") or "").strip(),
                expected_topics=tuple(str(topic) for topic in topics if str(topic).strip())
                if isinstance(topics, list)
                else (),
                required=required,
                command=command,
            )
        )
    return commands


def load_stack_commands() -> tuple[StackCommand, ...]:
    path = contract_path()
    if yaml is None:
        raise RuntimeError("PyYAML is required to load Isaac stack contract")
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise RuntimeError(f"{path} must contain a YAML mapping")
    return tuple(
        [
            *_items(payload, "required_commands", required=True),
            *_items(payload, "optional_commands", required=False),
        ]
    )


def missing_required_commands(commands: tuple[StackCommand, ...]) -> list[StackCommand]:
    return [command for command in commands if command.required and not command.command.strip()]


def expected_topics(commands: tuple[StackCommand, ...]) -> list[str]:
    topics: list[str] = []
    seen: set[str] = set()
    for command in commands:
        if not command.required:
            continue
        for topic in command.expected_topics:
            if topic not in seen:
                seen.add(topic)
                topics.append(topic)
    return topics
