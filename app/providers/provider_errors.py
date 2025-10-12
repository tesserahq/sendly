# ---------------------------
# Provider errors
# ---------------------------


class ProviderError(Exception):
    """Non-retryable provider error (bad request, auth error, etc.)."""


class ProviderRetryableError(Exception):
    """Retryable provider error (timeouts, 5xx)."""
