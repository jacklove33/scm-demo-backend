import logging
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from app.core.exceptions import (
    EntityConflict,
    EntityNotFound,
    PermissionDenied,
    ValidationFailure,
    VersionConflict,
)
from app.modules.audit.application.audit_writer import AuditWriter
from app.modules.audit.application.diff_service import AuditDiffService, AuditField
from app.modules.audit.domain.entities import AuditContext, JsonValue
from app.modules.audit.domain.enums import AuditAction
from app.modules.customer_pos.application.capabilities import (
    CustomerPoCapabilities,
    capabilities,
    scope_allows,
)
from app.modules.customer_pos.application.commands import (
    ChangeCustomerPoStatusCommand,
    CreateCustomerPoCommand,
    CustomerPoLineCommand,
    UpdateCustomerPoCommand,
)
from app.modules.customer_pos.application.event_writer import CustomerPoEventWriter
from app.modules.customer_pos.domain.entities import (
    CustomerPoLine,
    CustomerPoStatusEvent,
    CustomerPurchaseOrder,
)
from app.modules.customer_pos.domain.enums import (
    CustomerPoSource,
    CustomerPoStatus,
    CustomerPoStatusEventType,
    CustomerPoStatusTransitions,
)
from app.modules.customer_pos.domain.events import (
    CustomerPoEventCategory,
    CustomerPoEventPage,
    CustomerPoEventRepository,
    CustomerPoEventType,
)
from app.modules.customer_pos.domain.repository import (
    CustomerPoPage,
    CustomerPoRepository,
    CustomerPoSearchCriteria,
)
from app.shared.application.unit_of_work import UnitOfWork
from app.shared.domain.current_user import CurrentUser

logger = logging.getLogger(__name__)


class CustomerPoUseCases:
    def __init__(
        self,
        repository: CustomerPoRepository,
        audit_writer: AuditWriter,
        event_repository: CustomerPoEventRepository,
        unit_of_work: UnitOfWork,
    ) -> None:
        self.repository = repository
        self.audit_writer = audit_writer
        self.event_repository = event_repository
        self.event_writer = CustomerPoEventWriter(event_repository)
        self.unit_of_work = unit_of_work
        self.diff = AuditDiffService()

    @staticmethod
    def _require(actor: CurrentUser, code: str) -> None:
        if not actor.can(code):
            raise PermissionDenied(f"Missing permission: {code}")

    async def search(
        self, criteria: CustomerPoSearchCriteria, actor: CurrentUser
    ) -> CustomerPoPage:
        self._require(actor, "customer_pos.read")
        return await self.repository.search(
            criteria,
            actor_id=actor.user_id,
            tenant_id=actor.tenant_id,
            scope=actor.scope_for("customer_pos.read"),
        )

    async def get(
        self, po_id: UUID, actor: CurrentUser, *, include_deleted: bool = False
    ) -> tuple[CustomerPurchaseOrder, CustomerPoCapabilities]:
        self._require(actor, "customer_pos.detail.read")
        po = await self.repository.get(
            po_id,
            actor_id=actor.user_id,
            tenant_id=actor.tenant_id,
            scope=actor.scope_for("customer_pos.detail.read"),
            include_deleted=include_deleted,
        )
        if po is None:
            raise EntityNotFound("Customer PO not found")
        return po, capabilities(po, actor)

    async def create(
        self, command: CreateCustomerPoCommand, actor: CurrentUser, context: AuditContext
    ) -> tuple[CustomerPurchaseOrder, CustomerPoCapabilities]:
        self._require(actor, "customer_pos.create")
        if not await self.repository.customer_exists(actor.tenant_id, command.customer_id):
            raise ValidationFailure("Customer does not exist")
        owner_id = command.owner_user_id or actor.user_id
        if owner_id != actor.user_id and not actor.can("customer_pos.assign_owner"):
            raise PermissionDenied("Cannot assign Customer PO owner")
        if not await self.repository.owner_exists(actor.tenant_id, owner_id):
            raise ValidationFailure("Owner does not exist")
        lines = self._lines(command.lines, command.currency_code)
        now = datetime.now(UTC)
        status = (
            CustomerPoStatus.DRAFT
            if command.source == CustomerPoSource.MANUAL
            else CustomerPoStatus.RECEIVED
        )
        po = CustomerPurchaseOrder(
            id=uuid4(),
            tenant_id=actor.tenant_id,
            customer_id=command.customer_id,
            customer_po_number=command.customer_po_number.strip(),
            customer_po_revision=command.customer_po_revision.strip()
            if command.customer_po_revision
            else None,
            customer_po_date=command.customer_po_date,
            received_at=command.received_at,
            requested_ship_date=command.requested_ship_date,
            requested_delivery_date=command.requested_delivery_date,
            currency_code=self._upper(command.currency_code),
            payment_term_id=command.payment_term_id,
            ship_to_code=command.ship_to_code,
            bill_to_code=command.bill_to_code,
            ship_to_name=command.ship_to_name,
            ship_to_address1=command.ship_to_address1,
            ship_to_address2=command.ship_to_address2,
            ship_to_city=command.ship_to_city,
            ship_to_state=command.ship_to_state,
            ship_to_postal_code=command.ship_to_postal_code,
            ship_to_country_code=self._upper(command.ship_to_country_code),
            customer_contact_name=command.customer_contact_name,
            customer_contact_email=command.customer_contact_email,
            buyer_name=command.buyer_name,
            buyer_email=command.buyer_email,
            customer_notes=command.customer_notes,
            internal_notes=command.internal_notes,
            status=status,
            source=command.source,
            owner_user_id=owner_id,
            total_amount=self._total(lines),
            row_version=1,
            deleted_at=None,
            deleted_by=None,
            created_at=now,
            updated_at=now,
            created_by=actor.user_id,
            updated_by=actor.user_id,
            edi_log_id=command.edi_log_id,
            edi_transaction_type=command.edi_transaction_type,
            edi_standard=command.edi_standard,
            edi_version=command.edi_version,
            edi_sender_id=command.edi_sender_id,
            edi_receiver_id=command.edi_receiver_id,
            edi_interchange_control_number=command.edi_interchange_control_number,
            edi_group_control_number=command.edi_group_control_number,
            edi_transaction_control_number=command.edi_transaction_control_number,
            edi_document_id=command.edi_document_id,
            edi_received_at=command.edi_received_at,
            external_message_id=command.external_message_id,
            source_document_hash=command.source_document_hash,
            lines=lines,
        )
        event = self._status_event(
            po, None, status, CustomerPoStatusEventType.CREATED, actor, context, None
        )
        try:
            created = await self.repository.create(po, event)
            await self.event_writer.write(
                tenant_id=created.tenant_id,
                customer_po_id=created.id,
                event_type=CustomerPoEventType.CREATE,
                context=context,
                title="Customer PO created",
                description=f"PO {created.customer_po_number} was created.",
                metadata={"source": created.source.value},
            )
            await self._audit(context, AuditAction.CREATE, None, created)
            await self.unit_of_work.commit()
            logger.info(
                "Customer PO created",
                extra={
                    "business_module": "customer_po",
                    "entity_type": "customer_po",
                    "entity_id": str(created.id),
                    "entity_code": created.customer_po_number,
                },
            )
        except IntegrityError as error:
            await self.unit_of_work.rollback()
            raise EntityConflict("Duplicate Customer PO or line number") from error
        except Exception:
            await self.unit_of_work.rollback()
            raise
        return created, capabilities(created, actor)

    async def update(
        self, command: UpdateCustomerPoCommand, actor: CurrentUser, context: AuditContext
    ) -> tuple[CustomerPurchaseOrder, CustomerPoCapabilities]:
        self._require(actor, "customer_pos.update")
        before = await self._load_for(command.customer_po_id, actor, "customer_pos.update")
        owner_id = command.owner_user_id or before.owner_user_id
        if owner_id != before.owner_user_id and not actor.can("customer_pos.assign_owner"):
            raise PermissionDenied("Cannot assign Customer PO owner")
        if owner_id and not await self.repository.owner_exists(actor.tenant_id, owner_id):
            raise ValidationFailure("Owner does not exist")
        lines = self._lines(command.lines, command.currency_code)
        after = replace(
            before,
            requested_ship_date=command.requested_ship_date,
            requested_delivery_date=command.requested_delivery_date,
            currency_code=self._upper(command.currency_code),
            payment_term_id=command.payment_term_id,
            ship_to_code=command.ship_to_code,
            bill_to_code=command.bill_to_code,
            ship_to_name=command.ship_to_name,
            ship_to_address1=command.ship_to_address1,
            ship_to_address2=command.ship_to_address2,
            ship_to_city=command.ship_to_city,
            ship_to_state=command.ship_to_state,
            ship_to_postal_code=command.ship_to_postal_code,
            ship_to_country_code=self._upper(command.ship_to_country_code),
            customer_contact_name=command.customer_contact_name,
            customer_contact_email=command.customer_contact_email,
            buyer_name=command.buyer_name,
            buyer_email=command.buyer_email,
            customer_notes=command.customer_notes,
            internal_notes=command.internal_notes,
            owner_user_id=owner_id,
            total_amount=self._total(lines),
            updated_by=actor.user_id,
            lines=lines,
        )
        try:
            changed = await self.repository.update(after, command.expected_version)
            if changed is None:
                raise VersionConflict("Customer PO version conflict")
            await self.event_writer.write(
                tenant_id=changed.tenant_id,
                customer_po_id=changed.id,
                event_type=CustomerPoEventType.UPDATE,
                context=context,
                title="Customer PO updated",
            )
            await self._audit(context, AuditAction.UPDATE, before, changed)
            await self.unit_of_work.commit()
            logger.info(
                "Customer PO updated",
                extra={
                    "business_module": "customer_po",
                    "entity_type": "customer_po",
                    "entity_id": str(changed.id),
                    "entity_code": changed.customer_po_number,
                },
            )
        except IntegrityError as error:
            await self.unit_of_work.rollback()
            raise EntityConflict("Duplicate Customer PO line number") from error
        except Exception:
            await self.unit_of_work.rollback()
            raise
        return changed, capabilities(changed, actor)

    async def change_status(
        self, command: ChangeCustomerPoStatusCommand, actor: CurrentUser, context: AuditContext
    ) -> tuple[CustomerPurchaseOrder, CustomerPoCapabilities]:
        self._require(actor, "customer_pos.change_status")
        before = await self._load_for(command.customer_po_id, actor, "customer_pos.change_status")
        CustomerPoStatusTransitions.require(before.status, command.status)
        if command.status != CustomerPoStatus.DRAFT and not before.lines:
            raise ValidationFailure("Customer PO requires at least one line")
        event = self._status_event(
            before,
            before.status,
            command.status,
            CustomerPoStatusTransitions.event_type(command.status),
            actor,
            context,
            command.reason,
        )
        try:
            changed = await self.repository.change_status(
                before.id, command.expected_version, command.status, actor.user_id, event
            )
            if changed is None:
                raise VersionConflict("Customer PO version conflict")
            metadata: dict[str, JsonValue] = {
                "from_status": before.status.value,
                "to_status": changed.status.value,
            }
            if command.reason:
                metadata["reason"] = command.reason
            await self.event_writer.write(
                tenant_id=changed.tenant_id,
                customer_po_id=changed.id,
                event_type=CustomerPoEventType.STATUS_CHANGE,
                context=context,
                title="Status changed",
                description=f"{before.status.value} → {changed.status.value}",
                metadata=metadata,
            )
            await self._audit(
                context, AuditAction.STATUS_CHANGE, before, changed, reason=command.reason
            )
            await self.unit_of_work.commit()
            logger.info(
                "Customer PO status changed",
                extra={
                    "business_module": "customer_po",
                    "entity_type": "customer_po",
                    "entity_id": str(changed.id),
                    "entity_code": changed.customer_po_number,
                    "from_status": before.status.value,
                    "to_status": changed.status.value,
                },
            )
        except Exception:
            await self.unit_of_work.rollback()
            raise
        return changed, capabilities(changed, actor)

    async def soft_delete(
        self, po_id: UUID, expected_version: int, actor: CurrentUser, context: AuditContext
    ) -> None:
        before = await self._load_for(po_id, actor, "customer_pos.delete")
        try:
            after = await self.repository.soft_delete(po_id, expected_version, actor.user_id)
            if after is None:
                raise VersionConflict("Customer PO version conflict")
            await self.event_writer.write(
                tenant_id=after.tenant_id,
                customer_po_id=after.id,
                event_type=CustomerPoEventType.SOFT_DELETE,
                context=context,
                title="Customer PO deleted",
            )
            await self._audit(context, AuditAction.DELETE, before, after)
            await self.unit_of_work.commit()
            logger.info(
                "Customer PO deleted",
                extra={
                    "business_module": "customer_po",
                    "entity_type": "customer_po",
                    "entity_id": str(after.id),
                    "entity_code": after.customer_po_number,
                },
            )
        except Exception:
            await self.unit_of_work.rollback()
            raise

    async def restore(
        self, po_id: UUID, expected_version: int, actor: CurrentUser, context: AuditContext
    ) -> None:
        self._require(actor, "customer_pos.restore")
        po = await self.repository.get(
            po_id,
            actor_id=actor.user_id,
            tenant_id=actor.tenant_id,
            scope=actor.scope_for("customer_pos.restore"),
            include_deleted=True,
        )
        if po is None:
            raise EntityNotFound("Customer PO not found")
        try:
            after = await self.repository.restore(po_id, expected_version, actor.user_id)
            if after is None:
                raise VersionConflict("Customer PO version conflict")
            await self.event_writer.write(
                tenant_id=after.tenant_id,
                customer_po_id=after.id,
                event_type=CustomerPoEventType.RESTORE,
                context=context,
                title="Customer PO restored",
            )
            await self._audit(context, AuditAction.RESTORE, po, after)
            await self.unit_of_work.commit()
            logger.info(
                "Customer PO restored",
                extra={
                    "business_module": "customer_po",
                    "entity_type": "customer_po",
                    "entity_id": str(after.id),
                    "entity_code": after.customer_po_number,
                },
            )
        except Exception:
            await self.unit_of_work.rollback()
            raise

    async def status_history(self, po_id: UUID, actor: CurrentUser) -> list[CustomerPoStatusEvent]:
        await self.get(po_id, actor, include_deleted=True)
        return await self.repository.status_history(po_id, actor.tenant_id)

    async def event_timeline(
        self,
        po_id: UUID,
        actor: CurrentUser,
        *,
        page: int,
        page_size: int,
        event_type: CustomerPoEventType | None = None,
        category: CustomerPoEventCategory | None = None,
    ) -> CustomerPoEventPage:
        await self.get(po_id, actor, include_deleted=True)
        return await self.event_repository.list_for_po(
            actor.tenant_id, po_id, page, page_size, event_type, category
        )

    async def _load_for(
        self, po_id: UUID, actor: CurrentUser, permission: str
    ) -> CustomerPurchaseOrder:
        self._require(actor, permission)
        po = await self.repository.get(
            po_id,
            actor_id=actor.user_id,
            tenant_id=actor.tenant_id,
            scope=actor.scope_for(permission),
        )
        if po is None:
            raise EntityNotFound("Customer PO not found")
        if not scope_allows(actor, permission, po):
            raise PermissionDenied("Customer PO outside allowed scope")
        return po

    @staticmethod
    def _upper(value: str | None) -> str | None:
        return value.strip().upper() if value else None

    def _lines(
        self, commands: tuple[CustomerPoLineCommand, ...], header_currency: str | None
    ) -> tuple[CustomerPoLine, ...]:
        if not commands:
            raise ValidationFailure("At least one Customer PO line is required")
        if len({line.line_number for line in commands}) != len(commands):
            raise ValidationFailure("Duplicate line numbers")
        result = []
        for line in commands:
            if line.line_number <= 0 or line.ordered_quantity <= 0:
                raise ValidationFailure("Line number and ordered quantity must be positive")
            if line.unit_price is not None and line.unit_price < 0:
                raise ValidationFailure("Unit price cannot be negative")
            amount = (
                line.ordered_quantity * line.unit_price if line.unit_price is not None else None
            )
            result.append(
                CustomerPoLine(
                    id=line.id or uuid4(),
                    line_number=line.line_number,
                    customer_line_number=line.customer_line_number,
                    customer_item_number=line.customer_item_number,
                    product_id=line.product_id,
                    internal_item_number=line.internal_item_number,
                    item_description=line.item_description,
                    ordered_quantity=line.ordered_quantity,
                    unit_of_measure=self._upper(line.unit_of_measure),
                    unit_price=line.unit_price,
                    line_amount=amount,
                    currency_code=self._upper(line.currency_code or header_currency),
                    requested_ship_date=line.requested_ship_date,
                    requested_delivery_date=line.requested_delivery_date,
                    ship_to_code=line.ship_to_code,
                    status=line.status,
                    customer_notes=line.customer_notes,
                    edi_line_reference=line.edi_line_reference,
                )
            )
        return tuple(result)

    @staticmethod
    def _total(lines: tuple[CustomerPoLine, ...]) -> Decimal | None:
        amounts = [line.line_amount for line in lines if line.line_amount is not None]
        return sum(amounts, Decimal("0")) if amounts else None

    @staticmethod
    def _status_event(
        po: CustomerPurchaseOrder,
        before: CustomerPoStatus | None,
        after: CustomerPoStatus,
        event_type: CustomerPoStatusEventType,
        actor: CurrentUser,
        context: AuditContext,
        reason: str | None,
    ) -> CustomerPoStatusEvent:
        return CustomerPoStatusEvent(
            uuid4(),
            po.tenant_id,
            po.id,
            before,
            after,
            event_type,
            reason,
            actor.user_id,
            po.source,
            context.correlation_id,
            po.edi_log_id,
            {},
            datetime.now(UTC),
        )

    def _snapshot(self, po: CustomerPurchaseOrder | None) -> dict[str, AuditField] | None:
        if po is None:
            return None
        values = {
            "customer_po.customer_po_number": ("Customer PO Number", po.customer_po_number),
            "customer_po.customer_po_date": ("Customer PO Date", po.customer_po_date),
            "customer_po.requested_ship_date": ("Requested Ship Date", po.requested_ship_date),
            "customer_po.requested_delivery_date": (
                "Requested Delivery Date",
                po.requested_delivery_date,
            ),
            "customer_po.currency_code": ("Currency", po.currency_code),
            "customer_po.status": ("Status", po.status.value),
            "customer_po.owner_user_id": ("Owner", po.owner_user_id),
            "customer_po.customer_notes": ("Customer Notes", po.customer_notes),
            "customer_po.relationship_active": ("Relationship Active", po.deleted_at is None),
            "customer_po.total_amount": ("Total Amount", po.total_amount),
        }
        for line in po.lines:
            prefix = f"lines[{line.line_number}]"
            for name, label in (
                ("customer_item_number", "Customer Item Number"),
                ("product_id", "Product"),
                ("ordered_quantity", "Ordered Quantity"),
                ("unit_price", "Unit Price"),
                ("line_amount", "Line Amount"),
                ("requested_delivery_date", "Requested Delivery Date"),
            ):
                values[f"{prefix}.{name}"] = (label, getattr(line, name))

        def json(value: object) -> object:
            if isinstance(value, (UUID, Decimal)):
                return str(value)
            if isinstance(value, (date, datetime)):
                return value.isoformat()
            return value

        return {path: AuditField(label, json(value)) for path, (label, value) in values.items()}

    async def _audit(
        self,
        context: AuditContext,
        action: AuditAction,
        before: CustomerPurchaseOrder | None,
        after: CustomerPurchaseOrder,
        *,
        reason: str | None = None,
    ) -> None:
        await self.audit_writer.write_event(
            context=context,
            action=action,
            module="CUSTOMER_PO",
            entity_type="CUSTOMER_PO",
            entity_id=after.id,
            entity_code=after.customer_po_number,
            entity_display_name=after.customer_po_number,
            changes=self.diff.diff(self._snapshot(before), self._snapshot(after)),
            reason=reason,
        )
