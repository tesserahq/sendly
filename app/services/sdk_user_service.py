"""Application-owned session boundary for tessera_sdk authentication middleware."""

from app.db import session_scope
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserOnboard


class SDKUserService:
    """Expose the SDK's expected user methods without giving it session ownership."""

    def get_user_by_id_or_external_id(self, user_id: str):
        with session_scope() as session:
            user = UserRepository(session).get_user_by_id_or_external_id(user_id)
            if user is not None:
                session.expunge(user)
            return user

    def onboard_user(self, user_data: UserOnboard):
        with session_scope() as session:
            user = UserRepository(session).onboard_user(user_data)
            session.expunge(user)
            return user

    def close(self) -> None:
        """The SDK calls close; each method has already completed its scope."""


def create_sdk_user_service() -> SDKUserService:
    return SDKUserService()
