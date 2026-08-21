import logging


class LangfuseAuthenticationError(Exception):
    """Raised when Langfuse authentication fails."""

    def __init__(self, message: str = "Failed to authenticate with Langfuse."):
        logging.error(message)
        super().__init__(message)
