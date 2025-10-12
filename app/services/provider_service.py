import datetime
from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from app.models.provider import Provider
from app.schemas.provider import ProviderCreate, ProviderUpdate
from app.services.soft_delete_service import SoftDeleteService
from app.utils.db.filtering import apply_filters


class ProviderService(SoftDeleteService[Provider]):
    """Service class for managing provider CRUD operations."""

    def __init__(self, db: Session):
        """
        Initialize the provider service.

        Args:
            db: Database session
        """
        super().__init__(db, Provider)

    def get_provider(self, provider_id: UUID) -> Optional[Provider]:
        """
        Get a single provider by ID.

        Args:
            provider_id: The ID of the provider to retrieve

        Returns:
            Optional[Provider]: The provider or None if not found
        """
        return self.db.query(Provider).filter(Provider.id == provider_id).first()

    def get_provider_by_name(self, name: str) -> Optional[Provider]:
        """
        Get a provider by name.

        Args:
            name: The name of the provider to retrieve

        Returns:
            Optional[Provider]: The provider or None if not found
        """
        return self.db.query(Provider).filter(Provider.name == name).first()

    def get_providers(self, skip: int = 0, limit: int = 100) -> List[Provider]:
        """
        Get a list of providers with pagination.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List[Provider]: List of providers
        """
        return self.db.query(Provider).offset(skip).limit(limit).all()

    def create_provider(self, provider: ProviderCreate) -> Provider:
        """
        Create a new provider.

        Args:
            provider: The provider data to create

        Returns:
            Provider: The created provider
        """
        db_provider = Provider(**provider.model_dump())
        self.db.add(db_provider)
        self.db.commit()
        self.db.refresh(db_provider)
        return db_provider

    def update_provider(
        self, provider_id: UUID, provider: ProviderUpdate
    ) -> Optional[Provider]:
        """
        Update an existing provider.

        Args:
            provider_id: The ID of the provider to update
            provider: The updated provider data

        Returns:
            Optional[Provider]: The updated provider or None if not found
        """
        db_provider = self.db.query(Provider).filter(Provider.id == provider_id).first()
        if db_provider:
            update_data = provider.model_dump(exclude_unset=True)
            for key, value in update_data.items():
                setattr(db_provider, key, value)
            self.db.commit()
            self.db.refresh(db_provider)
        return db_provider

    def delete_provider(self, provider_id: UUID) -> bool:
        """
        Soft delete a provider.

        Args:
            provider_id: The ID of the provider to delete

        Returns:
            bool: True if the provider was deleted, False otherwise
        """
        return self.delete_record(provider_id)

    def restore_provider(self, provider_id: UUID) -> bool:
        """Restore a soft-deleted provider by setting deleted_at to None."""
        return self.restore_record(provider_id)

    def hard_delete_provider(self, provider_id: UUID) -> bool:
        """Permanently delete a provider from the database."""
        return self.hard_delete_record(provider_id)

    def get_deleted_providers(self, skip: int = 0, limit: int = 100) -> List[Provider]:
        """Get all soft-deleted providers."""
        return self.get_deleted_records(skip, limit)

    def get_deleted_provider(self, provider_id: UUID) -> Optional[Provider]:
        """Get a single soft-deleted provider by ID."""
        return self.get_deleted_record(provider_id)

    def get_providers_deleted_after(self, date: datetime) -> List[Provider]:
        """Get providers deleted after a specific date."""
        return self.get_records_deleted_after(date)

    def search(self, filters: dict) -> List[Provider]:
        """
        Search providers based on dynamic filter criteria.

        Args:
            filters: A dictionary where keys are field names and values are either:
                - A direct value (e.g. {"name": "AWS"})
                - A dictionary with 'operator' and 'value' keys (e.g. {"name": {"operator": "ilike", "value": "%aws%"}})

        Returns:
            List[Provider]: Filtered list of providers matching the criteria.
        """
        query = self.db.query(Provider)
        query = apply_filters(query, Provider, filters)
        return query.all()
