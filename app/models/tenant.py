from sqlalchemy.orm import relationship
from app.models.mixins import TimestampMixin, SoftDeleteMixin
from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

import uuid
import json

from app.db import Base
from app.security.crypto import encrypt_password, decrypt_password, is_encrypted


class Tenant(Base, TimestampMixin, SoftDeleteMixin):
    """Provider model for the application.
    This model represents a provider in the system.
    """

    __tablename__ = "tenants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, nullable=False)
    provider_id = Column(UUID(as_uuid=True), ForeignKey("providers.id"), nullable=False)
    _provider_settings = Column("provider_settings", String, nullable=True)

    provider = relationship("Provider", back_populates="tenants")
    emails = relationship("Email", back_populates="tenant")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @property
    def provider_settings(self) -> dict:
        """
        Get the decrypted provider settings.

        Returns:
            The decrypted provider settings as a dict or empty dict if no settings
        """
        if self._provider_settings is None:
            return {}

        decrypted = decrypt_password(self._provider_settings)
        if not decrypted:
            return {}

        try:
            return json.loads(decrypted)
        except json.JSONDecodeError:
            return {}

    @provider_settings.setter
    def provider_settings(self, value: dict) -> None:
        """
        Set the provider settings, automatically encrypting them.

        Args:
            value: The provider settings dict to set (plain or already encrypted string)
        """
        if value is None:
            self._provider_settings = None
            return

        # Handle empty dict as None
        if isinstance(value, dict) and not value:
            self._provider_settings = None
            return

        # If it's already an encrypted string (e.g., from database), store as-is
        if isinstance(value, str) and is_encrypted(value):
            self._provider_settings = value
        elif isinstance(value, dict):
            # Serialize and encrypt the dict
            json_str = json.dumps(value)
            self._provider_settings = encrypt_password(json_str)
        elif isinstance(value, str):
            # Plain JSON string, encrypt it
            # First validate it's valid JSON
            try:
                json.loads(value)
                self._provider_settings = encrypt_password(value)
            except json.JSONDecodeError:
                raise ValueError(
                    "provider_settings must be a valid JSON string or dict"
                )
        else:
            raise ValueError("provider_settings must be a dict or JSON string")
