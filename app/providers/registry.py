# sendly/providers/registry.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Type

from app.providers.postmark_provider import PostmarkProvider
from app.providers.email_provider import EmailProvider


@dataclass(frozen=True)
class ProviderConfig:
    """Metadata for a registered email provider (built from provider class)."""

    name: str
    id: str
    enabled: bool = True
    default: bool = False
    site: str | None = None


def _config_from_class(klass: Type[EmailProvider]) -> ProviderConfig:
    """Build ProviderConfig from a provider class's attributes."""
    return ProviderConfig(
        name=klass.provider_name,
        id=klass.provider_id,
        enabled=klass.enabled,
        default=klass.default,
        site=klass.site,
    )


# Register providers here (slug -> provider class)
_PROVIDERS: Dict[str, Type[EmailProvider]] = {
    "postmark": PostmarkProvider,
    # "resend": ResendProvider,
    # "ses": SESProvider,
}


def get_provider(slug: str, settings: dict) -> EmailProvider:
    """Return an EmailProvider instance for the given slug and runtime settings."""
    klass = _PROVIDERS.get(slug)
    if not klass:
        raise ValueError(f"Unsupported provider: {slug}")
    return klass(settings)


def get_provider_config(slug: str) -> ProviderConfig | None:
    """Return config for a provider by slug, or None if not registered."""
    klass = _PROVIDERS.get(slug)
    return _config_from_class(klass) if klass else None


def list_providers(enabled_only: bool = False) -> Dict[str, ProviderConfig]:
    """Return slug -> config for all registered providers."""
    result = {}
    for slug, klass in _PROVIDERS.items():
        config = _config_from_class(klass)
        if not enabled_only or config.enabled:
            result[slug] = config
    return result


def get_default_provider_slug() -> str | None:
    """Return the slug of the default provider, or None if none is set."""
    for slug, klass in _PROVIDERS.items():
        if klass.enabled and klass.default:
            return slug
    return None


def get_default_provider(settings: dict | None = None) -> EmailProvider:
    """Return the default EmailProvider instance. Raises ValueError if no default provider is configured."""
    slug = get_default_provider_slug()
    if slug is None:
        raise ValueError("No default email provider configured")
    return get_provider(slug, settings or {})
