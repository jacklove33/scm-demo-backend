from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import Select, exists, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.core.exceptions import EntityConflict, VersionConflict
from app.modules.customers.infrastructure.models import (
    BusinessPartnerModel,
    PartnerAddressModel,
    PartnerRoleModel,
    PaymentTermModel,
)
from app.modules.iam.infrastructure.models import ProfileModel, UserGroupModel
from app.modules.suppliers.domain.entities import Supplier, SupplierAddress
from app.modules.suppliers.domain.repository import (
    SupplierAccessFacts,
    SupplierPage,
    SupplierSearchCriteria,
    SupplierSearchItem,
)
from app.modules.suppliers.infrastructure.models import (
    SupplierGroupAssignmentModel,
    SupplierUserAssignmentModel,
)
from app.shared.domain.current_user import PermissionScope

SUPPLIER_ROLE = "SUPPLIER"


class SqlAlchemySupplierRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _to_domain(
        row: BusinessPartnerModel,
        role: PartnerRoleModel,
        owner_display_name: str | None,
    ) -> Supplier:
        return Supplier(
            id=row.id,
            tenant_id=row.tenant_id,
            supplier_code=row.partner_code,
            supplier_name=row.partner_name,
            tax_id=row.tax_id,
            country_code=row.country_code,
            currency_code=row.currency_code,
            payment_term_id=row.payment_term_id,
            owner_user_id=row.owner_user_id,
            owner_display_name=owner_display_name,
            status=row.status,
            deleted_at=role.deleted_at,
            deleted_by=role.deleted_by,
            row_version=row.row_version,
            created_at=row.created_at,
            updated_at=row.updated_at,
            addresses=tuple(
                SupplierAddress(
                    id=a.id,
                    address_code=a.address_code,
                    address_type=a.address_type,
                    contact_name=a.contact_name,
                    address1=a.address1,
                    address2=a.address2,
                    city=a.city,
                    state=a.state,
                    postal_code=a.postal_code,
                    country_code=a.country_code,
                    phone=a.phone,
                    email=a.email,
                    is_default=a.is_default,
                )
                for a in row.addresses
            ),
        )

    @staticmethod
    def _is_assigned(actor_id: UUID) -> ColumnElement[bool]:
        return exists(
            select(SupplierUserAssignmentModel.supplier_id).where(
                SupplierUserAssignmentModel.tenant_id == BusinessPartnerModel.tenant_id,
                SupplierUserAssignmentModel.supplier_id == BusinessPartnerModel.id,
                SupplierUserAssignmentModel.user_id == actor_id,
            )
        )

    @staticmethod
    def _is_team_assigned(actor_id: UUID) -> ColumnElement[bool]:
        return exists(
            select(SupplierGroupAssignmentModel.supplier_id)
            .join(UserGroupModel, UserGroupModel.group_id == SupplierGroupAssignmentModel.group_id)
            .where(
                SupplierGroupAssignmentModel.tenant_id == BusinessPartnerModel.tenant_id,
                SupplierGroupAssignmentModel.supplier_id == BusinessPartnerModel.id,
                UserGroupModel.user_id == actor_id,
            )
        )

    def _base(self) -> Select[Any]:
        return (
            select(BusinessPartnerModel, PartnerRoleModel, ProfileModel.display_name)
            .join(
                PartnerRoleModel,
                (PartnerRoleModel.partner_id == BusinessPartnerModel.id)
                & (PartnerRoleModel.tenant_id == BusinessPartnerModel.tenant_id)
                & (PartnerRoleModel.role_type == SUPPLIER_ROLE),
            )
            .outerjoin(ProfileModel, ProfileModel.id == BusinessPartnerModel.owner_user_id)
            .options(selectinload(BusinessPartnerModel.addresses))
        )

    def _apply_scope(
        self, stmt: Select[Any], *, actor_id: UUID, tenant_id: UUID, scope: PermissionScope
    ) -> Select[Any]:
        stmt = stmt.where(BusinessPartnerModel.tenant_id == tenant_id)
        if scope == PermissionScope.ALL:
            return stmt
        if scope == PermissionScope.OWN:
            return stmt.where(BusinessPartnerModel.owner_user_id == actor_id)
        if scope == PermissionScope.ASSIGNED:
            return stmt.where(self._is_assigned(actor_id))
        if scope == PermissionScope.TEAM:
            return stmt.where(
                or_(
                    BusinessPartnerModel.owner_user_id == actor_id, self._is_team_assigned(actor_id)
                )
            )
        return stmt.where(BusinessPartnerModel.id.is_(None))

    async def find_valid_payment_term_ids(self, tenant_id: UUID, ids: set[UUID]) -> set[UUID]:
        if not ids:
            return set()
        return set(
            await self.session.scalars(
                select(PaymentTermModel.id).where(
                    PaymentTermModel.tenant_id == tenant_id, PaymentTermModel.id.in_(ids)
                )
            )
        )

    async def list_payment_terms(self, tenant_id: UUID) -> list[tuple[UUID, str, str]]:
        rows = (
            await self.session.execute(
                select(PaymentTermModel.id, PaymentTermModel.code, PaymentTermModel.name)
                .where(PaymentTermModel.tenant_id == tenant_id)
                .order_by(PaymentTermModel.code)
            )
        ).all()
        return [(row.id, row.code, row.name) for row in rows]

    async def find_existing_partner_owner(
        self, tenant_id: UUID, supplier_code: str
    ) -> tuple[bool, UUID | None]:
        row = (
            await self.session.execute(
                select(BusinessPartnerModel.owner_user_id).where(
                    BusinessPartnerModel.tenant_id == tenant_id,
                    BusinessPartnerModel.partner_code == supplier_code,
                )
            )
        ).first()
        return (True, row[0]) if row else (False, None)

    async def find_valid_owner_ids(self, tenant_id: UUID, ids: set[UUID]) -> set[UUID]:
        if not ids:
            return set()
        return set(
            await self.session.scalars(
                select(ProfileModel.id).where(
                    ProfileModel.tenant_id == tenant_id,
                    ProfileModel.id.in_(ids),
                    ProfileModel.is_active.is_(True),
                )
            )
        )

    async def search(
        self,
        criteria: SupplierSearchCriteria,
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
    ) -> SupplierPage:
        owner = BusinessPartnerModel.owner_user_id == actor_id
        assigned, team = self._is_assigned(actor_id), self._is_team_assigned(actor_id)
        stmt = self._base().add_columns(
            owner.label("is_owner"), assigned.label("is_assigned"), team.label("is_team_assigned")
        )
        stmt = self._apply_scope(stmt, actor_id=actor_id, tenant_id=tenant_id, scope=scope)
        if not criteria.show_deleted:
            stmt = stmt.where(PartnerRoleModel.deleted_at.is_(None))
        if criteria.supplier_code:
            stmt = stmt.where(
                BusinessPartnerModel.partner_code == criteria.supplier_code.strip().upper()
            )
        if criteria.supplier_name_prefix:
            stmt = stmt.where(
                BusinessPartnerModel.partner_name.ilike(f"{criteria.supplier_name_prefix.strip()}%")
            )
        if criteria.status:
            stmt = stmt.where(BusinessPartnerModel.status == criteria.status)
        for value, column, operation in (
            (criteria.created_at_from, BusinessPartnerModel.created_at, "ge"),
            (criteria.created_at_to_exclusive, BusinessPartnerModel.created_at, "lt"),
            (criteria.updated_at_from, BusinessPartnerModel.updated_at, "ge"),
            (criteria.updated_at_to_exclusive, BusinessPartnerModel.updated_at, "lt"),
        ):
            if value:
                stmt = stmt.where(column >= value if operation == "ge" else column < value)
        total = int(
            await self.session.scalar(
                select(func.count()).select_from(stmt.order_by(None).subquery())
            )
            or 0
        )
        columns = {
            "supplier_code": BusinessPartnerModel.partner_code,
            "supplier_name": BusinessPartnerModel.partner_name,
            "created_at": BusinessPartnerModel.created_at,
            "updated_at": BusinessPartnerModel.updated_at,
            "status": BusinessPartnerModel.status,
        }
        col = columns.get(criteria.sort_field, BusinessPartnerModel.created_at)
        stmt = (
            stmt.order_by(col.asc() if criteria.sort_direction == "asc" else col.desc())
            .offset((criteria.page - 1) * criteria.page_size)
            .limit(criteria.page_size)
        )
        rows = (await self.session.execute(stmt)).all()
        return SupplierPage(
            [
                SupplierSearchItem(
                    self._to_domain(bp, role, display),
                    SupplierAccessFacts(bool(own), bool(direct), bool(group)),
                )
                for bp, role, display, own, direct, group in rows
            ],
            total,
            criteria.page,
            criteria.page_size,
        )

    async def get_by_id(
        self,
        supplier_id: UUID,
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
        include_deleted: bool = False,
    ) -> Supplier | None:
        stmt = self._apply_scope(
            self._base().where(BusinessPartnerModel.id == supplier_id),
            actor_id=actor_id,
            tenant_id=tenant_id,
            scope=scope,
        )
        if not include_deleted:
            stmt = stmt.where(PartnerRoleModel.deleted_at.is_(None))
        row = (await self.session.execute(stmt)).first()
        return self._to_domain(row[0], row[1], row[2]) if row else None

    async def get_access_facts(
        self, supplier_id: UUID, *, actor_id: UUID, tenant_id: UUID
    ) -> SupplierAccessFacts:
        row = (
            await self.session.execute(
                select(
                    BusinessPartnerModel.owner_user_id == actor_id,
                    self._is_assigned(actor_id),
                    self._is_team_assigned(actor_id),
                ).where(
                    BusinessPartnerModel.id == supplier_id,
                    BusinessPartnerModel.tenant_id == tenant_id,
                )
            )
        ).first()
        return (
            SupplierAccessFacts(*(bool(value) for value in row))
            if row
            else SupplierAccessFacts(False, False, False)
        )

    @staticmethod
    def _assert_compatible(existing: BusinessPartnerModel, supplier: Supplier) -> None:
        expected = {
            "name": (existing.partner_name, supplier.supplier_name),
            "tax_id": (existing.tax_id, supplier.tax_id),
            "country_code": (existing.country_code, supplier.country_code),
            "currency_code": (existing.currency_code, supplier.currency_code),
            "payment_term_id": (existing.payment_term_id, supplier.payment_term_id),
            "owner_user_id": (existing.owner_user_id, supplier.owner_user_id),
        }
        conflicts = [
            name
            for name, (current, requested) in expected.items()
            if requested is not None and current != requested
        ]
        if conflicts:
            raise EntityConflict(
                "Existing Business Partner master data conflicts", details={"fields": conflicts}
            )

    async def create(self, supplier: Supplier) -> Supplier:
        existing = (
            await self.session.execute(
                select(BusinessPartnerModel)
                .where(
                    BusinessPartnerModel.tenant_id == supplier.tenant_id,
                    BusinessPartnerModel.partner_code == supplier.supplier_code,
                )
                .options(selectinload(BusinessPartnerModel.addresses))
            )
        ).scalar_one_or_none()
        try:
            if existing:
                self._assert_compatible(existing, supplier)
                role = (
                    await self.session.execute(
                        select(PartnerRoleModel).where(
                            PartnerRoleModel.tenant_id == supplier.tenant_id,
                            PartnerRoleModel.partner_id == existing.id,
                            PartnerRoleModel.role_type == SUPPLIER_ROLE,
                        )
                    )
                ).scalar_one_or_none()
                if role:
                    raise EntityConflict("Supplier role already exists; restore it if deleted")
                self.session.add(
                    PartnerRoleModel(
                        tenant_id=supplier.tenant_id,
                        partner_id=existing.id,
                        role_type=SUPPLIER_ROLE,
                    )
                )
                await self.session.flush()
                created = await self.get_by_id(
                    existing.id,
                    actor_id=supplier.owner_user_id or existing.id,
                    tenant_id=supplier.tenant_id,
                    scope=PermissionScope.ALL,
                )
                assert created is not None
                return created
            bp = BusinessPartnerModel(
                id=supplier.id,
                tenant_id=supplier.tenant_id,
                partner_code=supplier.supplier_code,
                partner_name=supplier.supplier_name,
                tax_id=supplier.tax_id,
                country_code=supplier.country_code,
                currency_code=supplier.currency_code,
                payment_term_id=supplier.payment_term_id,
                owner_user_id=supplier.owner_user_id,
                status=supplier.status,
                row_version=1,
            )
            bp.addresses = [
                PartnerAddressModel(
                    id=a.id,
                    tenant_id=supplier.tenant_id,
                    partner_id=supplier.id,
                    address_code=a.address_code,
                    address_type=a.address_type,
                    contact_name=a.contact_name,
                    address1=a.address1,
                    address2=a.address2,
                    city=a.city,
                    state=a.state,
                    postal_code=a.postal_code,
                    country_code=a.country_code,
                    phone=a.phone,
                    email=a.email,
                    is_default=a.is_default,
                )
                for a in supplier.addresses
            ]
            self.session.add_all(
                [
                    bp,
                    PartnerRoleModel(
                        tenant_id=supplier.tenant_id,
                        partner_id=supplier.id,
                        role_type=SUPPLIER_ROLE,
                    ),
                ]
            )
            await self.session.flush()
        except IntegrityError as exc:
            raise EntityConflict("Business Partner or Supplier role already exists") from exc
        created = await self.get_by_id(
            bp.id,
            actor_id=supplier.owner_user_id or bp.id,
            tenant_id=supplier.tenant_id,
            scope=PermissionScope.ALL,
        )
        assert created is not None
        return created

    async def update(
        self,
        supplier_id: UUID,
        expected_version: int,
        data: dict[str, object],
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
    ) -> Supplier | None:
        if (
            await self.get_by_id(supplier_id, actor_id=actor_id, tenant_id=tenant_id, scope=scope)
            is None
        ):
            return None
        values = {
            **data,
            "updated_at": datetime.now(UTC),
            "row_version": BusinessPartnerModel.row_version + 1,
        }
        row = (
            await self.session.execute(
                update(BusinessPartnerModel)
                .where(
                    BusinessPartnerModel.id == supplier_id,
                    BusinessPartnerModel.tenant_id == tenant_id,
                    BusinessPartnerModel.row_version == expected_version,
                )
                .values(**values)
                .returning(BusinessPartnerModel.id)
            )
        ).scalar_one_or_none()
        if row is None:
            raise VersionConflict("Supplier was modified by another user")
        await self.session.flush()
        return await self.get_by_id(
            supplier_id, actor_id=actor_id, tenant_id=tenant_id, scope=scope
        )

    async def _set_deleted(
        self,
        supplier_id: UUID,
        expected_version: int,
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
        restore: bool,
    ) -> Supplier | None:
        visible = await self.get_by_id(
            supplier_id, actor_id=actor_id, tenant_id=tenant_id, scope=scope, include_deleted=True
        )
        if (
            visible is None
            or (restore and visible.deleted_at is None)
            or (not restore and visible.deleted_at is not None)
        ):
            return None
        now = datetime.now(UTC)
        bumped = await self.session.execute(
            update(BusinessPartnerModel)
            .where(
                BusinessPartnerModel.id == supplier_id,
                BusinessPartnerModel.tenant_id == tenant_id,
                BusinessPartnerModel.row_version == expected_version,
            )
            .values(row_version=BusinessPartnerModel.row_version + 1, updated_at=now)
        )
        if cast(Any, bumped).rowcount == 0:
            raise VersionConflict("Supplier was modified by another user")
        await self.session.execute(
            update(PartnerRoleModel)
            .where(
                PartnerRoleModel.partner_id == supplier_id,
                PartnerRoleModel.tenant_id == tenant_id,
                PartnerRoleModel.role_type == SUPPLIER_ROLE,
            )
            .values(
                deleted_at=None if restore else now,
                deleted_by=None if restore else actor_id,
                updated_at=now,
            )
        )
        await self.session.flush()
        return await self.get_by_id(
            supplier_id, actor_id=actor_id, tenant_id=tenant_id, scope=scope, include_deleted=True
        )

    async def soft_delete(
        self,
        supplier_id: UUID,
        expected_version: int,
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
    ) -> Supplier | None:
        return await self._set_deleted(
            supplier_id,
            expected_version,
            actor_id=actor_id,
            tenant_id=tenant_id,
            scope=scope,
            restore=False,
        )

    async def restore(
        self,
        supplier_id: UUID,
        expected_version: int,
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
    ) -> Supplier | None:
        return await self._set_deleted(
            supplier_id,
            expected_version,
            actor_id=actor_id,
            tenant_id=tenant_id,
            scope=scope,
            restore=True,
        )
