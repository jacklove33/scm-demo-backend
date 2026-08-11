from dataclasses import replace
from typing import Any, cast
from uuid import UUID

import pytest

from app.modules.audit.application.audit_writer import AuditWriter
from app.modules.audit.domain.entities import AuditChange, AuditContext, AuditEvent
from app.modules.audit.domain.enums import AuditAction, AuditActorType, AuditSource
from app.modules.audit.domain.repository import AuditRepository
from app.modules.customers.application.commands import CreateCustomerCommand, UpdateCustomerCommand
from app.modules.customers.application.use_cases import CustomerUseCases
from app.modules.customers.domain.entities import Customer
from app.modules.customers.domain.repository import CustomerAccessFacts, CustomerRepository
from app.shared.application.unit_of_work import UnitOfWork
from app.shared.domain.current_user import (
    CurrentUser,
    EffectivePermission,
    PermissionEffect,
    PermissionScope,
)


class CustomerStore:
    def __init__(self, *, fail_create: bool = False) -> None:
        self.created: list[Customer] = []
        self.current: Customer | None = None
        self.fail_create = fail_create

    async def create(self, customer: Customer) -> Customer:
        if self.fail_create:
            raise RuntimeError("forced customer failure")
        self.created.append(customer)
        self.current = customer
        return customer

    async def get_by_id(self, *_args: object, **_kwargs: object) -> Customer | None:
        return self.current

    async def get_access_facts(self, *_args: object, **_kwargs: object) -> CustomerAccessFacts:
        return CustomerAccessFacts(is_owner=True, is_assigned=False, is_team_assigned=False)

    async def update(self, *_args: object, **_kwargs: object) -> Customer | None:
        assert self.current is not None
        data = cast(dict[str, object], _args[2])
        self.current = replace(
            self.current,
            customer_name=cast(str, data["partner_name"]),
            owner_user_id=cast(UUID | None, data["owner_user_id"]),
            status=cast(str, data["status"]),
            row_version=self.current.row_version + 1,
        )
        return self.current


class AuditStore:
    def __init__(self, *, fail: bool = False) -> None:
        self.events: list[tuple[AuditEvent, list[AuditChange]]] = []
        self.fail = fail

    async def add_event(self, event: AuditEvent, changes: list[AuditChange]) -> None:
        if self.fail:
            raise RuntimeError("forced audit failure")
        self.events.append((event, changes))


class Transaction:
    def __init__(self, customer_store: CustomerStore, audit_store: AuditStore) -> None:
        self.customer_store = customer_store
        self.audit_store = audit_store
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1
        self.customer_store.created.clear()
        self.audit_store.events.clear()


def actor() -> CurrentUser:
    permissions = {
        action: EffectivePermission(action, PermissionEffect.ALLOW, PermissionScope.ALL, ())
        for action in ("customers.create", "customers.update")
    }
    return CurrentUser(
        user_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        email="jack@local.test",
        display_name="Jack Sales",
        is_active=True,
        permissions=permissions,
    )


def context(user: CurrentUser) -> AuditContext:
    return AuditContext(
        tenant_id=user.tenant_id,
        actor_user_id=user.user_id,
        actor_email=user.email,
        actor_display_name=user.display_name,
        source=AuditSource.API,
        correlation_id="corr-1",
        request_method="POST",
        request_path="/api/v1/customers",
    )


@pytest.mark.asyncio
async def test_customer_and_audit_commit_once_with_actor_snapshot() -> None:
    customers, audits = CustomerStore(), AuditStore()
    transaction = Transaction(customers, audits)
    use_cases = CustomerUseCases(
        cast(CustomerRepository, cast(Any, customers)),
        audit_writer=AuditWriter(cast(AuditRepository, cast(Any, audits))),
        unit_of_work=cast(UnitOfWork, transaction),
    )
    user = actor()

    await use_cases.create(CreateCustomerCommand("CUST100", "ACME", None), user, context(user))

    assert transaction.commits == 1
    assert transaction.rollbacks == 0
    event, changes = audits.events[0]
    assert event.action == AuditAction.CREATE
    assert event.actor_user_id == user.user_id
    assert event.actor_email == user.email
    assert event.actor_display_name == user.display_name
    assert event.actor_type == AuditActorType.USER
    assert event.module == "CUSTOMER"
    assert event.entity_type == "CUSTOMER"
    assert event.entity_code == "CUST100"
    assert event.source == AuditSource.API
    assert any(change.field_path == "customer.customer_name" for change in changes)


@pytest.mark.asyncio
async def test_customer_update_audits_exactly_the_changed_business_field() -> None:
    customers, audits = CustomerStore(), AuditStore()
    transaction = Transaction(customers, audits)
    use_cases = CustomerUseCases(
        cast(CustomerRepository, cast(Any, customers)),
        audit_writer=AuditWriter(cast(AuditRepository, cast(Any, audits))),
        unit_of_work=cast(UnitOfWork, transaction),
    )
    user = actor()
    created = await use_cases.create(
        CreateCustomerCommand("CUST100", "ACME", None), user, context(user)
    )
    audits.events.clear()

    await use_cases.update(
        UpdateCustomerCommand(
            customer_id=created.id,
            expected_version=created.row_version,
            customer_name="ACME Taiwan",
            owner_user_id=user.user_id,
            status="ACTIVE",
        ),
        user,
        replace(
            context(user), request_method="PUT", request_path=f"/api/v1/customers/{created.id}"
        ),
    )

    event, changes = audits.events[0]
    assert event.action == AuditAction.UPDATE
    assert [(change.field_path, change.old_value, change.new_value) for change in changes] == [
        ("customer.customer_name", "ACME", "ACME Taiwan")
    ]
    assert transaction.commits == 2


@pytest.mark.asyncio
async def test_audit_failure_rolls_back_customer_mutation() -> None:
    customers, audits = CustomerStore(), AuditStore(fail=True)
    transaction = Transaction(customers, audits)
    use_cases = CustomerUseCases(
        cast(CustomerRepository, cast(Any, customers)),
        audit_writer=AuditWriter(cast(AuditRepository, cast(Any, audits))),
        unit_of_work=cast(UnitOfWork, transaction),
    )
    user = actor()

    with pytest.raises(RuntimeError, match="forced audit failure"):
        await use_cases.create(CreateCustomerCommand("CUST100", "ACME", None), user, context(user))

    assert transaction.commits == 0
    assert transaction.rollbacks == 1
    assert customers.created == []
    assert audits.events == []


@pytest.mark.asyncio
async def test_customer_failure_does_not_stage_or_commit_audit() -> None:
    customers, audits = CustomerStore(fail_create=True), AuditStore()
    transaction = Transaction(customers, audits)
    use_cases = CustomerUseCases(
        cast(CustomerRepository, cast(Any, customers)),
        audit_writer=AuditWriter(cast(AuditRepository, cast(Any, audits))),
        unit_of_work=cast(UnitOfWork, transaction),
    )
    user = actor()

    with pytest.raises(RuntimeError, match="forced customer failure"):
        await use_cases.create(CreateCustomerCommand("CUST100", "ACME", None), user, context(user))

    assert transaction.commits == 0
    assert transaction.rollbacks == 1
    assert audits.events == []
