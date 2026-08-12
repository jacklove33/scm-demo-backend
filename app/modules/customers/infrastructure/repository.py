from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import Select, exists, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.core.exceptions import EntityConflict, VersionConflict
from app.modules.customers.domain.entities import Customer, CustomerAddress
from app.modules.customers.domain.repository import (
    CustomerAccessFacts,
    CustomerPage,
    CustomerSearchCriteria,
    CustomerSearchItem,
)
from app.modules.customers.infrastructure.models import (
    BusinessPartnerModel,
    CustomerGroupAssignmentModel,
    CustomerUserAssignmentModel,
    PartnerAddressModel,
    PartnerRoleModel,
    PaymentTermModel,
)
from app.modules.iam.infrastructure.models import ProfileModel, UserGroupModel
from app.shared.domain.current_user import PermissionScope

CUSTOMER_ROLE = "CUSTOMER"


class SqlAlchemyCustomerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _to_domain(
        row: BusinessPartnerModel,
        role_deleted_at: datetime | None = None,
        role_deleted_by: UUID | None = None,
    ) -> Customer:
        return Customer(
            id=row.id,
            tenant_id=row.tenant_id,
            customer_code=row.partner_code,
            customer_name=row.partner_name,
            tax_id=row.tax_id,
            country_code=row.country_code,
            currency_code=row.currency_code,
            payment_term_id=row.payment_term_id,
            owner_user_id=row.owner_user_id,
            status=row.status,
            deleted_at=role_deleted_at,
            deleted_by=role_deleted_by,
            row_version=row.row_version,
            created_at=row.created_at,
            updated_at=row.updated_at,
            addresses=tuple(
                CustomerAddress(
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
            select(CustomerUserAssignmentModel.customer_id).where(
                CustomerUserAssignmentModel.customer_id == BusinessPartnerModel.id,
                CustomerUserAssignmentModel.user_id == actor_id,
            )
        )

    @staticmethod
    def _is_team_assigned(actor_id: UUID) -> ColumnElement[bool]:
        return exists(
            select(CustomerGroupAssignmentModel.customer_id)
            .join(UserGroupModel, UserGroupModel.group_id == CustomerGroupAssignmentModel.group_id)
            .where(
                CustomerGroupAssignmentModel.customer_id == BusinessPartnerModel.id,
                UserGroupModel.user_id == actor_id,
            )
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

    def _base(self) -> Select[Any]:
        return (
            select(BusinessPartnerModel, PartnerRoleModel)
            .join(
                PartnerRoleModel,
                (PartnerRoleModel.partner_id == BusinessPartnerModel.id)
                & (PartnerRoleModel.tenant_id == BusinessPartnerModel.tenant_id)
                & (PartnerRoleModel.role_type == CUSTOMER_ROLE),
            )
            .options(selectinload(BusinessPartnerModel.addresses))
        )

    async def find_existing_codes(self, tenant_id: UUID, codes: set[str]) -> set[str]:
        if not codes:
            return set()
        return set(
            await self.session.scalars(
                select(BusinessPartnerModel.partner_code).where(
                    BusinessPartnerModel.tenant_id == tenant_id,
                    BusinessPartnerModel.partner_code.in_(codes),
                )
            )
        )

    async def find_valid_payment_term_ids(
        self, tenant_id: UUID, payment_term_ids: set[UUID]
    ) -> set[UUID]:
        if not payment_term_ids:
            return set()
        return set(
            await self.session.scalars(
                select(PaymentTermModel.id).where(
                    PaymentTermModel.tenant_id == tenant_id,
                    PaymentTermModel.id.in_(payment_term_ids),
                )
            )
        )

    async def find_valid_owner_ids(self, tenant_id: UUID, owner_ids: set[UUID]) -> set[UUID]:
        if not owner_ids:
            return set()
        return set(
            await self.session.scalars(
                select(ProfileModel.id).where(
                    ProfileModel.tenant_id == tenant_id,
                    ProfileModel.id.in_(owner_ids),
                    ProfileModel.is_active.is_(True),
                )
            )
        )

    async def search(
        self,
        criteria: CustomerSearchCriteria,
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
    ) -> CustomerPage:
        is_owner = BusinessPartnerModel.owner_user_id == actor_id
        assigned, team = self._is_assigned(actor_id), self._is_team_assigned(actor_id)
        stmt = self._base().add_columns(
            is_owner.label("is_owner"),
            assigned.label("is_assigned"),
            team.label("is_team_assigned"),
        )
        stmt = self._apply_scope(stmt, actor_id=actor_id, tenant_id=tenant_id, scope=scope)
        if not criteria.show_deleted:
            stmt = stmt.where(PartnerRoleModel.deleted_at.is_(None))
        if criteria.customer_code:
            stmt = stmt.where(
                BusinessPartnerModel.partner_code == criteria.customer_code.strip().upper()
            )
        if criteria.customer_name_prefix:
            stmt = stmt.where(
                BusinessPartnerModel.partner_name.ilike(f"{criteria.customer_name_prefix.strip()}%")
            )
        if criteria.status:
            stmt = stmt.where(BusinessPartnerModel.status == criteria.status)
        if criteria.created_at_from:
            stmt = stmt.where(BusinessPartnerModel.created_at >= criteria.created_at_from)
        if criteria.created_at_to_exclusive:
            stmt = stmt.where(BusinessPartnerModel.created_at < criteria.created_at_to_exclusive)
        if criteria.updated_at_from:
            stmt = stmt.where(BusinessPartnerModel.updated_at >= criteria.updated_at_from)
        if criteria.updated_at_to_exclusive:
            stmt = stmt.where(BusinessPartnerModel.updated_at < criteria.updated_at_to_exclusive)
        total = int(
            (
                await self.session.scalar(
                    select(func.count()).select_from(stmt.order_by(None).subquery())
                )
            )
            or 0
        )
        columns = {
            "customer_code": BusinessPartnerModel.partner_code,
            "customer_name": BusinessPartnerModel.partner_name,
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
        return CustomerPage(
            items=[
                CustomerSearchItem(
                    customer=self._to_domain(bp, role.deleted_at, role.deleted_by),
                    access=CustomerAccessFacts(bool(owner), bool(direct), bool(group)),
                )
                for bp, role, owner, direct, group in rows
            ],
            total=total,
            page=criteria.page,
            page_size=criteria.page_size,
        )

    async def get_by_id(
        self,
        customer_id: UUID,
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
        include_deleted: bool = False,
    ) -> Customer | None:
        stmt = self._base().where(BusinessPartnerModel.id == customer_id)
        stmt = self._apply_scope(stmt, actor_id=actor_id, tenant_id=tenant_id, scope=scope)
        if not include_deleted:
            stmt = stmt.where(PartnerRoleModel.deleted_at.is_(None))
        result = (await self.session.execute(stmt)).first()
        return (
            self._to_domain(result[0], result[1].deleted_at, result[1].deleted_by)
            if result
            else None
        )

    async def get_access_facts(
        self, customer_id: UUID, *, actor_id: UUID, tenant_id: UUID
    ) -> CustomerAccessFacts:
        row = (
            await self.session.execute(
                select(
                    (BusinessPartnerModel.owner_user_id == actor_id),
                    self._is_assigned(actor_id),
                    self._is_team_assigned(actor_id),
                ).where(
                    BusinessPartnerModel.id == customer_id,
                    BusinessPartnerModel.tenant_id == tenant_id,
                )
            )
        ).first()
        return (
            CustomerAccessFacts(*(bool(value) for value in row))
            if row
            else CustomerAccessFacts(False, False, False)
        )

    def _add(self, customer: Customer) -> BusinessPartnerModel:
        bp = BusinessPartnerModel(
            id=customer.id,
            tenant_id=customer.tenant_id,
            partner_code=customer.customer_code,
            partner_name=customer.customer_name,
            tax_id=customer.tax_id,
            country_code=customer.country_code,
            currency_code=customer.currency_code,
            payment_term_id=customer.payment_term_id,
            owner_user_id=customer.owner_user_id,
            status=customer.status,
            row_version=1,
        )
        bp.addresses = [
            PartnerAddressModel(
                id=a.id,
                tenant_id=customer.tenant_id,
                partner_id=customer.id,
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
            for a in customer.addresses
        ]
        self.session.add_all(
            [
                bp,
                PartnerRoleModel(
                    tenant_id=customer.tenant_id, partner_id=customer.id, role_type=CUSTOMER_ROLE
                ),
            ]
        )
        return bp

    async def create(self, customer: Customer) -> Customer:
        bp = self._add(customer)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            raise EntityConflict("Business partner code already exists in this tenant") from exc
        await self.session.refresh(bp)
        return self._to_domain(bp)

    async def create_many(self, customers: list[Customer]) -> None:
        for customer in customers:
            self._add(customer)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            raise EntityConflict("One or more business partner records conflict") from exc

    async def update(
        self,
        customer_id: UUID,
        expected_version: int,
        data: dict[str, object],
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
    ) -> Customer | None:
        if (
            await self.get_by_id(customer_id, actor_id=actor_id, tenant_id=tenant_id, scope=scope)
            is None
        ):
            return None
        values = dict(data)
        values["updated_at"] = datetime.now(UTC)
        values["row_version"] = BusinessPartnerModel.row_version + 1
        row = (
            await self.session.execute(
                update(BusinessPartnerModel)
                .where(
                    BusinessPartnerModel.id == customer_id,
                    BusinessPartnerModel.tenant_id == tenant_id,
                    BusinessPartnerModel.row_version == expected_version,
                )
                .values(**values)
                .returning(BusinessPartnerModel)
            )
        ).scalar_one_or_none()
        if row is None:
            raise VersionConflict("Customer was modified by another user")
        await self.session.flush()
        return await self.get_by_id(
            customer_id, actor_id=actor_id, tenant_id=tenant_id, scope=scope
        )

    async def _set_role_deleted(
        self,
        customer_id: UUID,
        expected_version: int,
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
        restore: bool,
    ) -> Customer | None:
        visible = await self.get_by_id(
            customer_id, actor_id=actor_id, tenant_id=tenant_id, scope=scope, include_deleted=True
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
                BusinessPartnerModel.id == customer_id,
                BusinessPartnerModel.tenant_id == tenant_id,
                BusinessPartnerModel.row_version == expected_version,
            )
            .values(row_version=BusinessPartnerModel.row_version + 1, updated_at=now)
        )
        if cast(Any, bumped).rowcount == 0:
            raise VersionConflict("Customer was modified by another user")
        await self.session.execute(
            update(PartnerRoleModel)
            .where(
                PartnerRoleModel.partner_id == customer_id,
                PartnerRoleModel.tenant_id == tenant_id,
                PartnerRoleModel.role_type == CUSTOMER_ROLE,
            )
            .values(
                deleted_at=None if restore else now,
                deleted_by=None if restore else actor_id,
                updated_at=now,
            )
        )
        await self.session.flush()
        return await self.get_by_id(
            customer_id,
            actor_id=actor_id,
            tenant_id=tenant_id,
            scope=scope,
            include_deleted=True,
        )

    async def soft_delete(
        self,
        customer_id: UUID,
        expected_version: int,
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
    ) -> Customer | None:
        return await self._set_role_deleted(
            customer_id,
            expected_version,
            actor_id=actor_id,
            tenant_id=tenant_id,
            scope=scope,
            restore=False,
        )

    async def restore(
        self,
        customer_id: UUID,
        expected_version: int,
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
    ) -> Customer | None:
        return await self._set_role_deleted(
            customer_id,
            expected_version,
            actor_id=actor_id,
            tenant_id=tenant_id,
            scope=scope,
            restore=True,
        )
