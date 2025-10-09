from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate, UserOnboard
from datetime import datetime, timezone
from app.services.soft_delete_service import SoftDeleteService

from app.utils.db.filtering import apply_filters


class UserService(SoftDeleteService[User]):
    def __init__(self, db: Session):
        super().__init__(db, User)

    def get_user(self, user_id: UUID) -> Optional[User]:
        return self.db.query(User).filter(User.id == user_id).first()

    def get_user_by_email(self, email: str) -> Optional[User]:
        return self.db.query(User).filter(User.email == email).first()

    def get_user_by_external_id(self, external_id: str) -> Optional[User]:
        return self.db.query(User).filter(User.external_id == external_id).first()

    def get_user_by_username(self, username: str) -> Optional[User]:
        return self.db.query(User).filter(User.username == username).first()

    def get_users(self, skip: int = 0, limit: int = 100) -> List[User]:
        return self.db.query(User).offset(skip).limit(limit).all()

    def create_user(self, user: UserCreate) -> User:
        db_user = User(**user.model_dump())
        self.db.add(db_user)
        self.db.commit()
        self.db.refresh(db_user)
        return db_user

    def onboard_user(self, user: UserOnboard) -> User:
        db_user = User(**user.model_dump())
        self.db.add(db_user)
        self.db.commit()
        self.db.refresh(db_user)
        return db_user

    def update_user(self, user_id: UUID, user: UserUpdate) -> Optional[User]:
        db_user = self.db.query(User).filter(User.id == user_id).first()
        if db_user:
            update_data = user.model_dump(exclude_unset=True)
            for key, value in update_data.items():
                setattr(db_user, key, value)
            self.db.commit()
            self.db.refresh(db_user)
        return db_user

    def delete_user(self, user_id: UUID) -> bool:
        """Soft delete a user."""
        return self.delete_record(user_id)

    def verify_user(self, user_id: UUID) -> Optional[User]:
        db_user = self.db.query(User).filter(User.id == user_id).first()
        if db_user:
            db_user.verified = True
            db_user.verified_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(db_user)
        return db_user

    def search(self, filters: dict) -> List[User]:
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
