from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.customer_pos.domain.entities import (
    CustomerPoLine,
    CustomerPoStatusEvent,
    CustomerPurchaseOrder,
)
from app.modules.customer_pos.domain.enums import (
    CustomerPoSource,
    CustomerPoStatus,
    CustomerPoStatusEventType,
)
from app.modules.customer_pos.domain.repository import CustomerPoPage, CustomerPoSearchCriteria
from app.modules.customer_pos.infrastructure.models import (
    CustomerPoLineModel,
    CustomerPoModel,
    CustomerPoStatusEventModel,
)
from app.modules.customers.infrastructure.models import (
    BusinessPartnerModel,
    CustomerGroupAssignmentModel,
    CustomerUserAssignmentModel,
    PartnerRoleModel,
)
from app.modules.iam.infrastructure.models import ProfileModel, UserGroupModel
from app.shared.domain.current_user import PermissionScope


class SqlAlchemyCustomerPoRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def customer_exists(self, tenant_id: UUID, customer_id: UUID) -> bool:
        return bool(
            await self.session.scalar(
                select(func.count())
                .select_from(BusinessPartnerModel)
                .join(
                    PartnerRoleModel,
                    and_(
                        PartnerRoleModel.partner_id == BusinessPartnerModel.id,
                        PartnerRoleModel.tenant_id == BusinessPartnerModel.tenant_id,
                        PartnerRoleModel.role_type == "CUSTOMER",
                        PartnerRoleModel.deleted_at.is_(None),
                    ),
                )
                .where(
                    BusinessPartnerModel.id == customer_id,
                    BusinessPartnerModel.tenant_id == tenant_id,
                    BusinessPartnerModel.deleted_at.is_(None),
                )
            )
        )

    async def owner_exists(self, tenant_id: UUID, owner_id: UUID) -> bool:
        return bool(
            await self.session.scalar(
                select(func.count())
                .select_from(ProfileModel)
                .where(
                    ProfileModel.id == owner_id,
                    ProfileModel.tenant_id == tenant_id,
                    ProfileModel.is_active.is_(True),
                )
            )
        )

    async def find_edi_by_external_message(
        self, tenant_id: UUID, sender_id: str, external_message_id: str
    ) -> UUID | None:
        return cast(
            UUID | None,
            await self.session.scalar(
                select(CustomerPoModel.id).where(
                    CustomerPoModel.tenant_id == tenant_id,
                    CustomerPoModel.source == CustomerPoSource.EDI.value,
                    CustomerPoModel.edi_sender_id == sender_id,
                    CustomerPoModel.external_message_id == external_message_id,
                )
            ),
        )

    def _scope(self, statement: Any, scope: PermissionScope, actor_id: UUID) -> Any:
        if scope == PermissionScope.ALL:
            return statement
        if scope == PermissionScope.OWN:
            return statement.where(CustomerPoModel.owner_user_id == actor_id)
        assigned = select(CustomerUserAssignmentModel.customer_id).where(
            CustomerUserAssignmentModel.user_id == actor_id
        )
        if scope == PermissionScope.ASSIGNED:
            return statement.where(CustomerPoModel.customer_id.in_(assigned))
        if scope == PermissionScope.TEAM:
            groups = select(UserGroupModel.group_id).where(UserGroupModel.user_id == actor_id)
            team = select(CustomerGroupAssignmentModel.customer_id).where(
                CustomerGroupAssignmentModel.group_id.in_(groups)
            )
            return statement.where(
                or_(
                    CustomerPoModel.owner_user_id == actor_id, CustomerPoModel.customer_id.in_(team)
                )
            )
        return statement.where(False)

    def _base(self, tenant_id: UUID) -> Any:
        return (
            select(CustomerPoModel)
            .where(CustomerPoModel.tenant_id == tenant_id)
            .options(selectinload(CustomerPoModel.lines))
        )

    async def search(
        self,
        criteria: CustomerPoSearchCriteria,
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
    ) -> CustomerPoPage:
        statement = self._scope(self._base(tenant_id), scope, actor_id)
        if not criteria.show_deleted:
            statement = statement.where(CustomerPoModel.deleted_at.is_(None))
        filters = (
            (
                criteria.customer_po_number,
                CustomerPoModel.customer_po_number.ilike(f"%{criteria.customer_po_number}%")
                if criteria.customer_po_number
                else None,
            ),
            (criteria.customer_id, CustomerPoModel.customer_id == criteria.customer_id),
            (
                criteria.status,
                CustomerPoModel.status == criteria.status.value if criteria.status else None,
            ),
            (
                criteria.source,
                CustomerPoModel.source == criteria.source.value if criteria.source else None,
            ),
            (
                criteria.customer_po_date_from,
                CustomerPoModel.customer_po_date >= criteria.customer_po_date_from
                if criteria.customer_po_date_from
                else None,
            ),
            (
                criteria.customer_po_date_to,
                CustomerPoModel.customer_po_date <= criteria.customer_po_date_to
                if criteria.customer_po_date_to
                else None,
            ),
            (
                criteria.requested_delivery_date_from,
                CustomerPoModel.requested_delivery_date >= criteria.requested_delivery_date_from
                if criteria.requested_delivery_date_from
                else None,
            ),
            (
                criteria.requested_delivery_date_to,
                CustomerPoModel.requested_delivery_date <= criteria.requested_delivery_date_to
                if criteria.requested_delivery_date_to
                else None,
            ),
            (criteria.owner_user_id, CustomerPoModel.owner_user_id == criteria.owner_user_id),
            (criteria.edi_message_id, CustomerPoModel.edi_message_id == criteria.edi_message_id),
            (criteria.sales_order_id, CustomerPoModel.sales_order_id == criteria.sales_order_id),
        )
        for value, condition in filters:
            if value is not None and condition is not None:
                statement = statement.where(condition)
        count = select(func.count()).select_from(statement.order_by(None).options().subquery())
        total = int(await self.session.scalar(count) or 0)
        statement = (
            statement.add_columns(
                BusinessPartnerModel.partner_code,
                BusinessPartnerModel.partner_name,
                ProfileModel.display_name,
            )
            .join(BusinessPartnerModel, BusinessPartnerModel.id == CustomerPoModel.customer_id)
            .outerjoin(ProfileModel, ProfileModel.id == CustomerPoModel.owner_user_id)
        )
        sort_columns = {
            "created_at": CustomerPoModel.created_at,
            "customer_po_number": CustomerPoModel.customer_po_number,
            "customer_po_date": CustomerPoModel.customer_po_date,
            "requested_delivery_date": CustomerPoModel.requested_delivery_date,
            "status": CustomerPoModel.status,
        }
        column = sort_columns.get(criteria.sort_field, CustomerPoModel.created_at)
        statement = (
            statement.order_by(
                column.asc() if criteria.sort_direction == "asc" else column.desc(),
                CustomerPoModel.id.desc(),
            )
            .offset((criteria.page - 1) * criteria.page_size)
            .limit(criteria.page_size)
        )
        rows = (await self.session.execute(statement)).all()
        return CustomerPoPage(
            [self._entity(row, code, name, owner) for row, code, name, owner in rows],
            total,
            criteria.page,
            criteria.page_size,
        )

    async def get(
        self,
        customer_po_id: UUID,
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
        include_deleted: bool = False,
    ) -> CustomerPurchaseOrder | None:
        statement = self._scope(
            self._base(tenant_id).where(CustomerPoModel.id == customer_po_id), scope, actor_id
        )
        if not include_deleted:
            statement = statement.where(CustomerPoModel.deleted_at.is_(None))
        row = await self.session.scalar(statement)
        return await self._enrich(row) if row else None

    async def create(
        self, po: CustomerPurchaseOrder, event: CustomerPoStatusEvent
    ) -> CustomerPurchaseOrder:
        row = self._model(po)
        self.session.add(row)
        self.session.add(self._event_model(event))
        await self.session.flush()
        return await self._enrich(row)

    async def update(
        self, po: CustomerPurchaseOrder, expected_version: int
    ) -> CustomerPurchaseOrder | None:
        row = await self.session.scalar(
            self._base(po.tenant_id).where(
                CustomerPoModel.id == po.id,
                CustomerPoModel.row_version == expected_version,
                CustomerPoModel.deleted_at.is_(None),
            )
        )
        if row is None:
            return None
        protected = {
            "id",
            "tenant_id",
            "customer_id",
            "customer_po_number",
            "customer_po_revision",
            "source",
            "status",
            "created_at",
            "created_by",
            "edi_message_id",
            "edi_transaction_type",
            "edi_standard",
            "edi_version",
            "edi_sender_id",
            "edi_receiver_id",
            "edi_interchange_control_number",
            "edi_group_control_number",
            "edi_transaction_control_number",
            "edi_document_id",
            "edi_received_at",
            "external_message_id",
            "source_document_hash",
            "sales_order_id",
            "conversion_status",
            "converted_at",
            "lines",
            "customer_code",
            "customer_name",
            "owner_display_name",
            "deleted_at",
            "deleted_by",
            "row_version",
        }
        for name in po.__dataclass_fields__:
            if name not in protected:
                setattr(row, name, getattr(po, name))
        row.row_version += 1
        row.updated_at = datetime.now(UTC)
        row.lines.clear()
        await self.session.flush()
        row.lines = [self._line_model(po.tenant_id, po.id, line) for line in po.lines]
        await self.session.flush()
        return await self._enrich(row)

    async def change_status(
        self,
        customer_po_id: UUID,
        expected_version: int,
        status: CustomerPoStatus,
        actor_id: UUID,
        event: CustomerPoStatusEvent,
    ) -> CustomerPurchaseOrder | None:
        result = await self.session.execute(
            update(CustomerPoModel)
            .where(
                CustomerPoModel.id == customer_po_id,
                CustomerPoModel.tenant_id == event.tenant_id,
                CustomerPoModel.row_version == expected_version,
                CustomerPoModel.deleted_at.is_(None),
            )
            .values(
                status=status.value,
                updated_by=actor_id,
                updated_at=datetime.now(UTC),
                row_version=CustomerPoModel.row_version + 1,
            )
            .returning(CustomerPoModel.id)
        )
        if result.scalar_one_or_none() is None:
            return None
        self.session.add(self._event_model(event))
        await self.session.flush()
        row = await self.session.scalar(
            self._base(event.tenant_id).where(CustomerPoModel.id == customer_po_id)
        )
        return await self._enrich(row) if row else None

    async def soft_delete(
        self, customer_po_id: UUID, expected_version: int, actor_id: UUID
    ) -> CustomerPurchaseOrder | None:
        return await self._set_deleted(customer_po_id, expected_version, actor_id, False)

    async def restore(
        self, customer_po_id: UUID, expected_version: int, actor_id: UUID
    ) -> CustomerPurchaseOrder | None:
        return await self._set_deleted(customer_po_id, expected_version, actor_id, True)

    async def _set_deleted(
        self, customer_po_id: UUID, expected_version: int, actor_id: UUID, restore: bool
    ) -> CustomerPurchaseOrder | None:
        now = datetime.now(UTC)
        condition = (
            CustomerPoModel.deleted_at.is_not(None)
            if restore
            else CustomerPoModel.deleted_at.is_(None)
        )
        result = await self.session.execute(
            update(CustomerPoModel)
            .where(
                CustomerPoModel.id == customer_po_id,
                CustomerPoModel.row_version == expected_version,
                condition,
            )
            .values(
                deleted_at=None if restore else now,
                deleted_by=None if restore else actor_id,
                updated_by=actor_id,
                updated_at=now,
                row_version=CustomerPoModel.row_version + 1,
            )
            .returning(CustomerPoModel.tenant_id)
        )
        tenant_id = result.scalar_one_or_none()
        if tenant_id is None:
            return None
        await self.session.flush()
        row = await self.session.scalar(
            self._base(tenant_id).where(CustomerPoModel.id == customer_po_id)
        )
        return await self._enrich(row) if row else None

    async def status_history(
        self, customer_po_id: UUID, tenant_id: UUID
    ) -> list[CustomerPoStatusEvent]:
        rows = (
            await self.session.scalars(
                select(CustomerPoStatusEventModel)
                .where(
                    CustomerPoStatusEventModel.customer_po_id == customer_po_id,
                    CustomerPoStatusEventModel.tenant_id == tenant_id,
                )
                .order_by(
                    CustomerPoStatusEventModel.occurred_at.desc(),
                    CustomerPoStatusEventModel.id.desc(),
                )
            )
        ).all()
        return [self._event(row) for row in rows]

    async def _enrich(self, row: CustomerPoModel) -> CustomerPurchaseOrder:
        display = (
            await self.session.execute(
                select(
                    BusinessPartnerModel.partner_code,
                    BusinessPartnerModel.partner_name,
                    ProfileModel.display_name,
                )
                .outerjoin(ProfileModel, ProfileModel.id == row.owner_user_id)
                .where(BusinessPartnerModel.id == row.customer_id)
            )
        ).one()
        return self._entity(row, *display)

    @staticmethod
    def _line_model(tenant_id: UUID, po_id: UUID, line: CustomerPoLine) -> CustomerPoLineModel:
        return CustomerPoLineModel(
            tenant_id=tenant_id,
            customer_po_id=po_id,
            **{name: getattr(line, name) for name in line.__dataclass_fields__},
        )

    def _model(self, po: CustomerPurchaseOrder) -> CustomerPoModel:
        values = {
            name: getattr(po, name)
            for name in po.__dataclass_fields__
            if name not in {"lines", "customer_code", "customer_name", "owner_display_name"}
        }
        row = CustomerPoModel(**values)
        row.lines = [self._line_model(po.tenant_id, po.id, line) for line in po.lines]
        return row

    @staticmethod
    def _entity(
        row: CustomerPoModel,
        customer_code: str | None = None,
        customer_name: str | None = None,
        owner_display_name: str | None = None,
    ) -> CustomerPurchaseOrder:
        values = {
            name: getattr(row, name)
            for name in CustomerPurchaseOrder.__dataclass_fields__
            if name not in {"lines", "customer_code", "customer_name", "owner_display_name"}
        }
        values["status"] = CustomerPoStatus(row.status)
        values["source"] = CustomerPoSource(row.source)
        values["lines"] = tuple(
            CustomerPoLine(
                **{name: getattr(line, name) for name in CustomerPoLine.__dataclass_fields__}
            )
            for line in row.lines
        )
        return CustomerPurchaseOrder(
            **values,
            customer_code=customer_code,
            customer_name=customer_name,
            owner_display_name=owner_display_name,
        )

    @staticmethod
    def _event_model(event: CustomerPoStatusEvent) -> CustomerPoStatusEventModel:
        return CustomerPoStatusEventModel(
            id=event.id,
            tenant_id=event.tenant_id,
            customer_po_id=event.customer_po_id,
            from_status=event.from_status.value if event.from_status else None,
            to_status=event.to_status.value,
            event_type=event.event_type.value,
            reason=event.reason,
            actor_user_id=event.actor_user_id,
            source=event.source.value,
            correlation_id=event.correlation_id,
            edi_message_id=event.edi_message_id,
            metadata_json=event.metadata,
            occurred_at=event.occurred_at,
        )

    @staticmethod
    def _event(row: CustomerPoStatusEventModel) -> CustomerPoStatusEvent:
        return CustomerPoStatusEvent(
            row.id,
            row.tenant_id,
            row.customer_po_id,
            CustomerPoStatus(row.from_status) if row.from_status else None,
            CustomerPoStatus(row.to_status),
            CustomerPoStatusEventType(row.event_type),
            row.reason,
            row.actor_user_id,
            CustomerPoSource(row.source),
            row.correlation_id,
            row.edi_message_id,
            row.metadata_json,
            row.occurred_at,
        )
