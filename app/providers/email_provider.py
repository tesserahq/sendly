# sendly/providers/base.py
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, Iterable

from app.providers.base import EmailEvent, EmailCreateRequest, EmailSendResult

# ---------------------------
# Provider Interface
# ---------------------------


class EmailProvider(ABC):
    """Strategy interface for providers. Subclasses must set provider_id and provider_name."""

    provider_id: str = ""
    provider_name: str = ""
    enabled: bool = True
    default: bool = False
    site: str | None = None

    def __init__(self, settings: dict):
        self.settings = settings

    @abstractmethod
    def send_email(self, req: EmailCreateRequest) -> EmailSendResult:
        """Translate EmailCreateRequest -> provider API call -> EmailSendResult."""
        raise NotImplementedError

    @abstractmethod
    def parse_webhook(
        self, payload: Dict[str, Any], headers: Dict[str, str]
    ) -> Iterable[EmailEvent]:
        """Normalize provider webhook payload -> iterable of EmailEvent."""
        raise NotImplementedError

    @abstractmethod
    def verify_webhook(self, payload: bytes, headers: Dict[str, str]) -> bool:
        """Return True if webhook signature is valid."""
        raise NotImplementedError
