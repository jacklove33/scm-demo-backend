from decimal import Decimal
from typing import Any, cast
from uuid import UUID

import pytest

from app.core.exceptions import EntityConflict, PermissionDenied, ValidationFailure
from app.modules.audit.application.audit_writer import AuditWriter
from app.modules.audit.domain.entities import AuditChange, AuditContext, AuditEvent
from app.modules.audit.domain.enums import AuditAction, AuditActorType, AuditSource
from app.modules.audit.domain.repository import AuditRepository
from app.modules.customer_pos.application.commands import (
    CreateCustomerPoCommand,
    CustomerPoLineCommand,
)
from app.modules.customer_pos.application.use_cases import CustomerPoUseCases
from app.modules.customer_pos.domain.entities import CustomerPoStatusEvent, CustomerPurchaseOrder
from app.modules.customer_pos.domain.enums import (
    CustomerPoSource,
    CustomerPoStatus,
    CustomerPoStatusTransitions,
)
from app.modules.customer_pos.domain.repository import CustomerPoRepository
from app.shared.application.unit_of_work import UnitOfWork
from app.shared.domain.current_user import (
    CurrentUser,
    EffectivePermission,
    PermissionEffect,
    PermissionScope,
)

TENANT = UUID("11111111-1111-1111-1111-111111111111")
KEVIN = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
CUSTOMER = UUID("40000000-0000-0000-0000-000000000001")


class PoStore:
    def __init__(self) -> None:
        self.po: CustomerPurchaseOrder | None = None
        self.status_events: list[CustomerPoStatusEvent] = []

    async def customer_exists(self, tenant_id: UUID, customer_id: UUID) -> bool:
        return tenant_id == TENANT and customer_id == CUSTOMER

    async def owner_exists(self, tenant_id: UUID, owner_id: UUID) -> bool:
        return tenant_id == TENANT and owner_id == KEVIN

    async def create(
        self, po: CustomerPurchaseOrder, event: CustomerPoStatusEvent
    ) -> CustomerPurchaseOrder:
        self.po = po
        self.status_events.append(event)
        return po


class AuditStore:
    def __init__(self, fail: bool = False) -> None:
        self.events: list[tuple[AuditEvent, list[AuditChange]]] = []
        self.fail = fail

    async def add_event(self, event: AuditEvent, changes: list[AuditChange]) -> None:
        if self.fail:
            raise RuntimeError("audit failed")
        self.events.append((event, changes))


class Transaction:
    def __init__(self, po: PoStore, audit: AuditStore) -> None:
        self.po = po
        self.audit = audit
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1
        self.po.po = None
        self.po.status_events.clear()
        self.audit.events.clear()


def actor(*, allowed: bool = True) -> CurrentUser:
    permissions = {}
    if allowed:
        permissions["customer_pos.create"] = EffectivePermission(
            "customer_pos.create", PermissionEffect.ALLOW, PermissionScope.ALL, ()
        )
    return CurrentUser(KEVIN, TENANT, "kevin@local.test", "Kevin Admin", True, permissions)


def context() -> AuditContext:
    return AuditContext(
        TENANT,
        KEVIN,
        "kevin@local.test",
        "Kevin Admin",
        AuditSource.API,
        correlation_id="po-test",
    )


def command() -> CreateCustomerPoCommand:
    return CreateCustomerPoCommand(
        customer_id=CUSTOMER,
        customer_po_number="PO-10001",
        source=CustomerPoSource.MANUAL,
        currency_code="usd",
        lines=(
            CustomerPoLineCommand(10, Decimal("10"), unit_price=Decimal("2.50")),
            CustomerPoLineCommand(20, Decimal("4"), unit_price=Decimal("1.25")),
        ),
    )


def use_cases(po: PoStore, audit: AuditStore, transaction: Transaction) -> CustomerPoUseCases:
    return CustomerPoUseCases(
        cast(CustomerPoRepository, cast(Any, po)),
        AuditWriter(cast(AuditRepository, cast(Any, audit))),
        cast(UnitOfWork, transaction),
    )


def test_status_transition_rules_accept_valid_and_reject_terminal_transition() -> None:
    CustomerPoStatusTransitions.require(CustomerPoStatus.DRAFT, CustomerPoStatus.RECEIVED)
    with pytest.raises(EntityConflict, match="Invalid Customer PO status transition"):
        CustomerPoStatusTransitions.require(CustomerPoStatus.CANCELLED, CustomerPoStatus.RECEIVED)


@pytest.mark.asyncio
async def test_create_computes_amounts_stages_status_and_field_audit_then_commits_once() -> None:
    po, audit = PoStore(), AuditStore()
    transaction = Transaction(po, audit)

    created, _ = await use_cases(po, audit, transaction).create(command(), actor(), context())

    assert created.status == CustomerPoStatus.DRAFT
    assert [line.line_amount for line in created.lines] == [Decimal("25.00"), Decimal("5.00")]
    assert created.total_amount == Decimal("30.00")
    assert len(po.status_events) == 1
    assert po.status_events[0].to_status == CustomerPoStatus.DRAFT
    event, changes = audit.events[0]
    assert event.action == AuditAction.CREATE
    assert event.actor_type == AuditActorType.USER
    assert event.actor_user_id == KEVIN
    assert event.actor_display_name == "Kevin Admin"
    assert event.actor_email == "kevin@local.test"
    assert event.module == "CUSTOMER_PO"
    assert event.entity_type == "CUSTOMER_PO"
    assert event.entity_code == "PO-10001"
    assert event.source == AuditSource.API
    assert "lines[10].ordered_quantity" in {change.field_path for change in changes}
    assert transaction.commits == 1
    assert transaction.rollbacks == 0


@pytest.mark.asyncio
async def test_audit_failure_rolls_back_po_and_status_event() -> None:
    po, audit = PoStore(), AuditStore(fail=True)
    transaction = Transaction(po, audit)

    with pytest.raises(RuntimeError, match="audit failed"):
        await use_cases(po, audit, transaction).create(command(), actor(), context())

    assert transaction.commits == 0
    assert transaction.rollbacks == 1
    assert po.po is None
    assert po.status_events == []


@pytest.mark.asyncio
async def test_create_requires_permission_and_rejects_duplicate_lines() -> None:
    po, audit = PoStore(), AuditStore()
    transaction = Transaction(po, audit)
    service = use_cases(po, audit, transaction)
    with pytest.raises(PermissionDenied):
        await service.create(command(), actor(allowed=False), context())

    invalid = command()
    invalid = CreateCustomerPoCommand(
        customer_id=invalid.customer_id,
        customer_po_number=invalid.customer_po_number,
        lines=(
            CustomerPoLineCommand(10, Decimal("1")),
            CustomerPoLineCommand(10, Decimal("2")),
        ),
    )
    with pytest.raises(ValidationFailure, match="Duplicate line numbers"):
        await service.create(invalid, actor(), context())
