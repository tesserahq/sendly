from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from app.models.tenant import Tenant
from app.schemas.tenant import TenantCreate, TenantUpdate
from app.services.soft_delete_service import SoftDeleteService
from app.utils.db.filtering import apply_filters


class TenantService(SoftDeleteService[Tenant]):
    """Service class for managing tenant CRUD operations."""

    def __init__(self, db: Session):
        """
        Initialize the tenant service.

        Args:
            db: Database session
        """
        super().__init__(db, Tenant)

    def get_tenant(self, tenant_id: UUID) -> Optional[Tenant]:
        """
        Get a single tenant by ID.

        Args:
            tenant_id: The ID of the tenant to retrieve

        Returns:
            Optional[Tenant]: The tenant or None if not found
        """
        return self.db.query(Tenant).filter(Tenant.id == tenant_id).first()

    def get_tenant_by_name(self, name: str) -> Optional[Tenant]:
        """
        Get a tenant by name.

        Args:
            name: The name of the tenant to retrieve

        Returns:
            Optional[Tenant]: The tenant or None if not found
        """
        return self.db.query(Tenant).filter(Tenant.name == name).first()

    def get_tenants(self, skip: int = 0, limit: int = 100) -> List[Tenant]:
        """
        Get a list of tenants with pagination.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List[Tenant]: List of tenants
        """
        return self.db.query(Tenant).offset(skip).limit(limit).all()

    def get_tenants_by_provider(
        self, provider_id: UUID, skip: int = 0, limit: int = 100
    ) -> List[Tenant]:
        """
        Get all tenants for a specific provider.

        Args:
            provider_id: The ID of the provider
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List[Tenant]: List of tenants for the provider
        """
        return (
            self.db.query(Tenant)
            .filter(Tenant.provider_id == provider_id)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def create_tenant(self, tenant: TenantCreate) -> Tenant:
        """
        Create a new tenant.

        Args:
            tenant: The tenant data to create

        Returns:
            Tenant: The created tenant
        """
        db_tenant = Tenant(**tenant.model_dump())
        self.db.add(db_tenant)
        self.db.commit()
        self.db.refresh(db_tenant)
        return db_tenant

    def update_tenant(self, tenant_id: UUID, tenant: TenantUpdate) -> Optional[Tenant]:
        """
        Update an existing tenant.

        Args:
            tenant_id: The ID of the tenant to update
            tenant: The updated tenant data

        Returns:
            Optional[Tenant]: The updated tenant or None if not found
        """
        db_tenant = self.db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if db_tenant:
            update_data = tenant.model_dump(exclude_unset=True)
            for key, value in update_data.items():
                setattr(db_tenant, key, value)
            self.db.commit()
            self.db.refresh(db_tenant)
        return db_tenant

    def delete_tenant(self, tenant_id: UUID) -> bool:
        """
        Soft delete a tenant.

        Args:
            tenant_id: The ID of the tenant to delete

        Returns:
            bool: True if the tenant was deleted, False otherwise
        """
        return self.delete_record(tenant_id)

    def search(self, filters: dict) -> List[Tenant]:
        """
        Search tenants based on dynamic filter criteria.

        Args:
            filters: A dictionary where keys are field names and values are either:
                - A direct value (e.g. {"name": "My Tenant"})
                - A dictionary with 'operator' and 'value' keys (e.g. {"name": {"operator": "ilike", "value": "%tenant%"}})

        Returns:
            List[Tenant]: Filtered list of tenants matching the criteria.
        """
        query = self.db.query(Tenant)
        query = apply_filters(query, Tenant, filters)
        return query.all()
