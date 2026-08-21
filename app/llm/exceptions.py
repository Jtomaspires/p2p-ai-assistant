"""LLM-specific application errors."""


class LLMUnavailableError(RuntimeError):
    """Raised after every configured LLM attempt has failed."""
