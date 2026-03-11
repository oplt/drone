"""ML runtime package for in-flight anomaly detection."""

__all__ = ["ml_runtime"]


def __getattr__(name: str):
    if name == "ml_runtime":
        from .runtime import ml_runtime

        return ml_runtime
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
