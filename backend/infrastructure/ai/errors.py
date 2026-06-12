from __future__ import annotations


class LLMError(RuntimeError):
    code = "LLM_ERROR"

    def __init__(self, message: str, *, detail: str = "") -> None:
        super().__init__(message)
        self.detail = detail


class LLMConfigError(LLMError):
    code = "INVALID_LLM_CONFIG"


class LLMNetworkError(LLMError):
    code = "LLM_NETWORK_FAILURE"


class LLMProviderUnavailableError(LLMError):
    code = "LLM_PROVIDER_UNAVAILABLE"


class LLMUnsupportedModelError(LLMError):
    code = "LLM_UNSUPPORTED_MODEL"
