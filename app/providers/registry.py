# sendly/providers/registry.py
from __future__ import annotations
from typing import Dict, Type

from app.providers.postmark_provider import PostmarkProvider
from app.providers.email_provider import EmailProvider

# Register providers here
_PROVIDER_CLASSES: Dict[str, Type[EmailProvider]] = {
    "postmark": PostmarkProvider,
    # "resend": ResendProvider,
    # "ses": SESProvider,
}


def get_provider(slug, settings: dict) -> EmailProvider:
    cls = _PROVIDER_CLASSES.get(slug)
    if not cls:
        raise ValueError(f"Unsupported provider: {slug}")
    return cls(settings)
