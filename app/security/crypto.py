"""
Cryptography utilities for field-level encryption using Fernet.

This module provides encryption and decryption functions for sensitive data
like passwords, using Python's cryptography.fernet.Fernet.
"""

import base64
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from app.config import get_settings


class CryptoManager:
    """Manages encryption and decryption operations using Fernet."""

    def __init__(self):
        self.settings = get_settings()
        self._fernet = None

    @property
    def fernet(self) -> Fernet:
        """Get or create the Fernet instance."""
        if self._fernet is None:
            key = self._get_or_create_key()
            self._fernet = Fernet(key)
        return self._fernet

    def _get_or_create_key(self) -> bytes:
        """Get the Fernet key from environment or create a new one."""
        # Always read fresh settings so env patches during tests take effect
        settings = get_settings()
        # Try to get from config
        fernet_key = settings.fernet_key

        if fernet_key:
            try:
                # Add padding if needed and validate the key format
                padded_key = fernet_key + "=" * (-len(fernet_key) % 4)
                # Decode and validate length (must be 32 bytes for Fernet)
                decoded_bytes = base64.urlsafe_b64decode(padded_key)
                if len(decoded_bytes) != 32:
                    raise ValueError("Fernet key must decode to exactly 32 bytes")
                # Return the padded key as bytes for Fernet constructor
                return padded_key.encode("utf-8")
            except Exception as e:
                raise ValueError(f"Invalid FERNET_KEY format: {e}")

        # For development/testing, create a key from a salt
        # In production, this should always be set via environment variable
        if settings.environment in ["development", "test"]:
            salt = settings.fernet_salt.encode()

            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(salt))
            return key

        raise ValueError(
            "FERNET_KEY environment variable is required in production. "
            "Set it to a base64-encoded 32-byte key."
        )

    def encrypt_password(self, plain_text: str) -> str:
        """
        Encrypt a plain text password.

        Args:
            plain_text: The plain text password to encrypt

        Returns:
            The encrypted password as a base64-encoded string

        Raises:
            ValueError: If the input is not a string
        """
        if plain_text is None:
            return ""

        if not isinstance(plain_text, str):
            raise ValueError("Password must be a string")

        if not plain_text:
            return ""

        # Check if already encrypted (starts with Fernet prefix)
        if plain_text.startswith("gAAAAA"):
            return plain_text

        try:
            encrypted_bytes = self.fernet.encrypt(plain_text.encode())
            return encrypted_bytes.decode()
        except Exception as e:
            raise ValueError(f"Failed to encrypt password: {e}")

    def decrypt_password(self, encrypted_text: str) -> str:
        """
        Decrypt an encrypted password.

        Args:
            encrypted_text: The encrypted password as a base64-encoded string

        Returns:
            The decrypted password

        Raises:
            ValueError: If the input is not a string or decryption fails
        """
        if encrypted_text is None:
            return ""

        if not isinstance(encrypted_text, str):
            raise ValueError("Encrypted password must be a string")

        if not encrypted_text:
            return ""

        # Check if it's not encrypted (doesn't start with Fernet prefix)
        if not encrypted_text.startswith("gAAAAA"):
            return encrypted_text

        try:
            decrypted_bytes = self.fernet.decrypt(encrypted_text.encode())
            return decrypted_bytes.decode()
        except InvalidToken:
            raise ValueError("Invalid encrypted token - cannot decrypt")
        except Exception as e:
            raise ValueError(f"Failed to decrypt password: {e}")

    def is_encrypted(self, text: str) -> bool:
        """
        Check if a text appears to be encrypted.

        Args:
            text: The text to check

        Returns:
            True if the text appears to be encrypted, False otherwise
        """
        if text is None or not isinstance(text, str) or not text:
            return False

        # Fernet tokens start with "gAAAAA"
        return text.startswith("gAAAAA")


# Global instance for easy access
crypto_manager = CryptoManager()


def encrypt_password(plain_text: str) -> str:
    """
    Convenience function to encrypt a password.

    Args:
        plain_text: The plain text password to encrypt

    Returns:
        The encrypted password
    """
    return crypto_manager.encrypt_password(plain_text)


def decrypt_password(encrypted_text: str) -> str:
    """
    Convenience function to decrypt a password.

    Args:
        encrypted_text: The encrypted password

    Returns:
        The decrypted password
    """
    return crypto_manager.decrypt_password(encrypted_text)


def is_encrypted(text: str) -> bool:
    """
    Convenience function to check if text is encrypted.

    Args:
        text: The text to check

    Returns:
        True if the text appears to be encrypted
    """
    return crypto_manager.is_encrypted(text)
