"""
Machine-to-Machine (M2M) token utility for obtaining access tokens from OAuth/OIDC providers.
"""

# TODO: Move this into the SDK

import httpx
from typing import Optional, Dict, Any
from pydantic import BaseModel
from app.config import get_settings


class M2MTokenRequest(BaseModel):
    """Request model for M2M token authentication."""

    client_id: str
    client_secret: str
    audience: str
    grant_type: str = "client_credentials"


class M2MTokenResponse(BaseModel):
    """Response model for M2M token authentication."""

    access_token: str
    token_type: str
    expires_in: int
    scope: Optional[str] = None


class M2MTokenClient:
    """Client for obtaining machine-to-machine tokens from OAuth/OIDC providers."""

    def __init__(self, provider_domain: Optional[str] = None):
        """
        Initialize the M2M token client.

        Args:
            provider_domain: OAuth/OIDC provider domain (e.g., 'dev-si3yygt34d0fk7hc.us.auth0.com')
                           If not provided, will use settings.
        """
        self.settings = get_settings()
        self.provider_domain = provider_domain or self.settings.oidc_domain
        self.base_url = f"https://{self.provider_domain}"

    def _prepare_token_request(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        audience: str = "",
    ) -> tuple[M2MTokenRequest, Dict[str, str]]:
        """
        Prepare the token request payload and headers.

        Args:
            client_id: The OAuth client ID
            client_secret: The OAuth client secret
            audience: The API audience (identifier)

        Returns:
            Tuple of (payload, headers)

        Raises:
            ValueError: If credentials are missing
        """
        # Use settings defaults if not provided
        client_id = client_id or self.settings.service_account_client_id
        client_secret = client_secret or self.settings.service_account_client_secret
        audience = audience or self.settings.oidc_api_audience

        if not client_id or not client_secret:
            raise ValueError(
                "Client ID and Client Secret must be provided either as parameters or via settings"
            )

        payload = M2MTokenRequest(
            client_id=client_id, client_secret=client_secret, audience=audience
        )

        headers = {"Content-Type": "application/json"}
        return payload, headers

    def _process_token_response(self, data: Dict[str, Any]) -> M2MTokenResponse:
        """
        Process and validate the token response.

        Args:
            data: The response data from the OAuth provider

        Returns:
            M2MTokenResponse containing the access token and metadata

        Raises:
            ValueError: If required fields are missing
        """
        # Validate required fields
        required_fields = ["access_token", "token_type", "expires_in"]
        missing_fields = [field for field in required_fields if field not in data]

        if missing_fields:
            raise ValueError(f"Missing required fields in response: {missing_fields}")

        return M2MTokenResponse(**data)

    async def get_token(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        audience: str = "",
        timeout: float = 30.0,
    ) -> M2MTokenResponse:
        """
        Get a machine-to-machine access token from OAuth/OIDC provider.

        Args:
            client_id: The OAuth client ID (uses settings.service_account_client_id if not provided)
            client_secret: The OAuth client secret (uses settings.service_account_client_secret if not provided)
            audience: The API audience (identifier)
            timeout: Request timeout in seconds

        Returns:
            M2MTokenResponse containing the access token and metadata

        Raises:
            httpx.HTTPStatusError: If the request fails
            ValueError: If the response is invalid or credentials are missing
        """
        payload, headers = self._prepare_token_request(
            client_id, client_secret, audience
        )

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{self.base_url}/oauth/token",
                json=payload.model_dump(),
                headers=headers,
            )
            response.raise_for_status()

            data = response.json()
            return self._process_token_response(data)

    def get_token_sync(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        audience: str = "",
        timeout: float = 30.0,
    ) -> M2MTokenResponse:
        """
        Synchronous version of get_token for use in non-async contexts.

        Args:
            client_id: The OAuth client ID (uses settings.service_account_client_id if not provided)
            client_secret: The OAuth client secret (uses settings.service_account_client_secret if not provided)
            audience: The API audience (identifier)
            timeout: Request timeout in seconds

        Returns:
            M2MTokenResponse containing the access token and metadata

        Raises:
            httpx.HTTPStatusError: If the request fails
            ValueError: If the response is invalid or credentials are missing
        """
        payload, headers = self._prepare_token_request(
            client_id, client_secret, audience
        )

        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                f"{self.base_url}/oauth/token",
                json=payload.model_dump(),
                headers=headers,
            )
            response.raise_for_status()

            data = response.json()
            return self._process_token_response(data)


# Convenience function for quick token retrieval
async def get_m2m_token(
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    audience: str = "",
    provider_domain: Optional[str] = None,
    timeout: float = 30.0,
) -> str:
    """
    Convenience function to get an M2M access token.

    Args:
        client_id: The OAuth client ID (uses settings.service_account_client_id if not provided)
        client_secret: The OAuth client secret (uses settings.service_account_client_secret if not provided)
        audience: The API audience (identifier)
        provider_domain: OAuth/OIDC provider domain (optional, uses settings if not provided)
        timeout: Request timeout in seconds

    Returns:
        The access token string

    Raises:
        httpx.HTTPStatusError: If the request fails
        ValueError: If the response is invalid or credentials are missing
    """
    client = M2MTokenClient(provider_domain)
    response = await client.get_token(client_id, client_secret, audience, timeout)
    return response.access_token


def get_m2m_token_sync(
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    audience: str = "",
    provider_domain: Optional[str] = None,
    timeout: float = 30.0,
) -> str:
    """
    Synchronous convenience function to get an M2M access token.

    Args:
        client_id: The OAuth client ID (uses settings.service_account_client_id if not provided)
        client_secret: The OAuth client secret (uses settings.service_account_client_secret if not provided)
        audience: The API audience (identifier)
        provider_domain: OAuth/OIDC provider domain (optional, uses settings if not provided)
        timeout: Request timeout in seconds

    Returns:
        The access token string

    Raises:
        httpx.HTTPStatusError: If the request fails
        ValueError: If the response is invalid or credentials are missing
    """
    client = M2MTokenClient(provider_domain)
    response = client.get_token_sync(client_id, client_secret, audience, timeout)
    return response.access_token
