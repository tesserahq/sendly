"""User service for the tessera_sdk authentication/onboarding middlewares.

Each call runs in its own managed session and returns a detached user; see
tessera_sdk.server.user_service.
"""

from tessera_sdk.server.user_service import create_managed_user_service_factory

from app.db import db_manager
from app.repositories.user_repository import UserRepository

create_sdk_user_service = create_managed_user_service_factory(
    db_manager,
    get_user=lambda db, user_id: UserRepository(db).get_user_by_id_or_external_id(
        user_id
    ),
    onboard_user=lambda db, user_data: UserRepository(db).onboard_user(user_data),
)
