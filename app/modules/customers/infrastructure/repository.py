from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, and_, exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import VersionConflict
from app.modules.customers.domain.entities import Customer
from app.modules.customers.domain.repository import CustomerPage, CustomerSearchCriteria
from app.modules.customers.infrastructure.models import (
    CustomerGroupAssignmentModel,
    CustomerModel,
    CustomerUserAssignmentModel,
)
from app.modules.iam.infrastructure.models import UserGroupModel
from app.shared.domain.current_user import PermissionScope


class SqlAlchemyCustomerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _to_domain(row: CustomerModel) -> Customer:
        return Customer(
            id=row.id,
            tenant_id=row.tenant_id,
            customer_code=row.customer_code,
            customer_name=row.customer_name,
            owner_user_id=row.owner_user_id,
            status=row.status,
            deleted_at=row.deleted_at,
            deleted_by=row.deleted_by,
            row_version=row.row_version,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _apply_scope(
        self,
        stmt: Select,
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
    ) -> Select:
        stmt = stmt.where(CustomerModel.tenant_id == tenant_id)

        if scope == PermissionScope.ALL:
            return stmt

        if scope == PermissionScope.OWN:
            return stmt.where(CustomerModel.owner_user_id == actor_id)

        if scope == PermissionScope.ASSIGNED:
            assignment_exists = exists(
                select(CustomerUserAssignmentModel.customer_id).where(
                    CustomerUserAssignmentModel.customer_id == CustomerModel.id,
                    CustomerUserAssignmentModel.user_id == actor_id,
                )
            )
            return stmt.where(assignment_exists)

        if scope == PermissionScope.TEAM:
            team_exists = exists(
                select(CustomerGroupAssignmentModel.customer_id)
                .join(
                    UserGroupModel,
                    UserGroupModel.group_id == CustomerGroupAssignmentModel.group_id,
                )
                .where(
                    CustomerGroupAssignmentModel.customer_id == CustomerModel.id,
                    UserGroupModel.user_id == actor_id,
                )
            )
            return stmt.where(
                or_(
                    CustomerModel.owner_user_id == actor_id,
                    team_exists,
                )
            )

        # NONE is default deny and returns zero rows.
        return stmt.where(False)

    async def search(
        self,
        criteria: CustomerSearchCriteria,
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
    ) -> CustomerPage:
        stmt = select(CustomerModel)
        stmt = self._apply_scope(stmt, actor_id=actor_id, tenant_id=tenant_id, scope=scope)

        if not criteria.show_deleted:
            stmt = stmt.where(CustomerModel.deleted_at.is_(None))

        # Structured search: no global %keyword% scan.
        if criteria.customer_code:
            stmt = stmt.where(CustomerModel.customer_code == criteria.customer_code.strip().upper())

        if criteria.customer_name_prefix:
            prefix = criteria.customer_name_prefix.strip()
            stmt = stmt.where(CustomerModel.customer_name.ilike(f"{prefix}%"))

        if criteria.status:
            stmt = stmt.where(CustomerModel.status == criteria.status)

        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = int((await self.session.scalar(count_stmt)) or 0)

        sort_columns = {
            "customer_code": CustomerModel.customer_code,
            "customer_name": CustomerModel.customer_name,
            "created_at": CustomerModel.created_at,
            "updated_at": CustomerModel.updated_at,
            "status": CustomerModel.status,
        }
        sort_column = sort_columns.get(criteria.sort_field, CustomerModel.created_at)
        ordering = sort_column.asc() if criteria.sort_direction == "asc" else sort_column.desc()

        stmt = (
            stmt.order_by(ordering)
            .offset((criteria.page - 1) * criteria.page_size)
            .limit(criteria.page_size)
        )

        rows = (await self.session.scalars(stmt)).all()
        return CustomerPage(
            items=[self._to_domain(row) for row in rows],
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
        stmt = select(CustomerModel).where(CustomerModel.id == customer_id)
        stmt = self._apply_scope(stmt, actor_id=actor_id, tenant_id=tenant_id, scope=scope)

        if not include_deleted:
            stmt = stmt.where(CustomerModel.deleted_at.is_(None))

        row = await self.session.scalar(stmt)
        return self._to_domain(row) if row else None

    async def create(self, customer: Customer) -> Customer:
        row = CustomerModel(
            id=customer.id,
            tenant_id=customer.tenant_id,
            customer_code=customer.customer_code,
            customer_name=customer.customer_name,
            owner_user_id=customer.owner_user_id,
            status=customer.status,
            deleted_at=None,
            deleted_by=None,
            row_version=1,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return self._to_domain(row)

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
        visible = await self.get_by_id(
            customer_id,
            actor_id=actor_id,
            tenant_id=tenant_id,
            scope=scope,
        )
        if visible is None:
            return None

        values = dict(data)
        values["updated_at"] = datetime.now(UTC)
        values["row_version"] = CustomerModel.row_version + 1

        stmt = (
            update(CustomerModel)
            .where(
                CustomerModel.id == customer_id,
                CustomerModel.tenant_id == tenant_id,
                CustomerModel.row_version == expected_version,
                CustomerModel.deleted_at.is_(None),
            )
            .values(**values)
            .returning(CustomerModel)
        )
        row = (await self.session.execute(stmt)).scalar_one_or_none()

        if row is None:
            await self.session.rollback()
            raise VersionConflict("Customer was modified by another user")

        await self.session.commit()
        return self._to_domain(row)

    async def soft_delete(
        self,
        customer_id: UUID,
        expected_version: int,
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
    ) -> bool:
        visible = await self.get_by_id(
            customer_id,
            actor_id=actor_id,
            tenant_id=tenant_id,
            scope=scope,
        )
        if visible is None:
            return False

        stmt = (
            update(CustomerModel)
            .where(
                CustomerModel.id == customer_id,
                CustomerModel.tenant_id == tenant_id,
                CustomerModel.row_version == expected_version,
                CustomerModel.deleted_at.is_(None),
            )
            .values(
                deleted_at=datetime.now(UTC),
                deleted_by=actor_id,
                updated_at=datetime.now(UTC),
                row_version=CustomerModel.row_version + 1,
            )
        )
        result = await self.session.execute(stmt)
        if result.rowcount == 0:
            await self.session.rollback()
            raise VersionConflict("Customer was modified by another user")

        await self.session.commit()
        return True

    async def restore(
        self,
        customer_id: UUID,
        expected_version: int,
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
    ) -> bool:
        # Include deleted is intentional for restore authorization.
        visible = await self.get_by_id(
            customer_id,
            actor_id=actor_id,
            tenant_id=tenant_id,
            scope=scope,
            include_deleted=True,
        )
        if visible is None or visible.deleted_at is None:
            return False

        stmt = (
            update(CustomerModel)
            .where(
                CustomerModel.id == customer_id,
                CustomerModel.tenant_id == tenant_id,
                CustomerModel.row_version == expected_version,
                CustomerModel.deleted_at.is_not(None),
            )
            .values(
                deleted_at=None,
                deleted_by=None,
                updated_at=datetime.now(UTC),
                row_version=CustomerModel.row_version + 1,
            )
        )
        result = await self.session.execute(stmt)
        if result.rowcount == 0:
            await self.session.rollback()
            raise VersionConflict("Customer was modified by another user")

        await self.session.commit()
        return True
