"""Vehicle runtime application services."""

from typing import Any

__all__ = ["Orchestrator"]


def __getattr__(name: str) -> Any:
    if name == "Orchestrator":
        from .orchestrator import Orchestrator

        return Orchestrator
    raise AttributeError(name)
