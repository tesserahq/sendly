from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories.soft_delete_repository import SoftDeleteRepository
from app.schemas.user import UserCreate, UserOnboard, UserUpdate
from app.utils.db.filtering import apply_filters


class UserRepository(SoftDeleteRepository[User]):
    def __init__(self, db: Session):
        super().__init__(db, User)

    def get_user(self, user_id: UUID) -> User | None:
        return self.db.query(User).filter(User.id == user_id).first()

    def get_user_by_email(self, email: str) -> User | None:
        return self.db.query(User).filter(User.email == email).first()

    def get_user_by_external_id(self, external_id: str) -> User | None:
        return self.db.query(User).filter(User.external_id == external_id).first()

    def get_user_by_id_or_external_id(self, id: str) -> User | None:
        try:
            uuid_id = UUID(str(id))
            return (
                self.db.query(User)
                .filter(or_(User.id == uuid_id, User.external_id == str(id)))
                .first()
            )
        except (ValueError, TypeError):
            # Not a valid UUID, only match on external_id
            return self.db.query(User).filter(User.external_id == str(id)).first()

    def get_users(self, skip: int = 0, limit: int = 100) -> list[User]:
        return self.db.query(User).offset(skip).limit(limit).all()

    def create_user(self, user: UserCreate) -> User:
        db_user = User(**user.model_dump())
        self.db.add(db_user)
        self.db.flush()
        self.db.refresh(db_user)
        return db_user

    def onboard_user(self, user: UserOnboard) -> User:
        db_user = User(**user.model_dump())
        self.db.add(db_user)
        self.db.flush()
        self.db.refresh(db_user)
        return db_user

    def update_user(self, user_id: UUID, user: UserUpdate) -> User | None:
        db_user = self.db.query(User).filter(User.id == user_id).first()
        if db_user:
            update_data = user.model_dump(exclude_unset=True)
            for key, value in update_data.items():
                setattr(db_user, key, value)
            self.db.flush()
            self.db.refresh(db_user)
        return db_user

    def delete_user(self, user_id: UUID) -> bool:
        """Soft delete a user."""
        return self.delete_record(user_id)

    def verify_user(self, user_id: UUID) -> User | None:
        db_user = self.db.query(User).filter(User.id == user_id).first()
        if db_user:
            db_user.verified = True
            db_user.verified_at = datetime.now(UTC)
            self.db.flush()
            self.db.refresh(db_user)
        return db_user

    def search(self, filters: dict) -> list[User]:
        """
        Search users based on dynamic filter criteria.

        Args:
            filters: A dictionary where keys are field names and values are either:
                - A direct value (e.g. {"email": "test@example.com"})
                - A dictionary with 'operator' and 'value' keys (e.g. {"email": {"operator": "ilike", "value": "%@example.com"}})

        Returns:
            List[User]: Filtered list of users matching the criteria.
        """
        query = self.db.query(User)
        query = apply_filters(query, User, filters)
        return query.all()
