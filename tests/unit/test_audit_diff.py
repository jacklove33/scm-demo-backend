from datetime import UTC, datetime
from uuid import UUID

from app.modules.audit.application.diff_service import AuditDiffService, AuditField
from app.modules.audit.domain.entities import AuditContext
from app.modules.audit.domain.enums import AuditActorType, AuditChangeType, AuditSource
from app.modules.customers.domain.entities import Customer, CustomerAddress


def customer(*, name: str = "ACME", city: str = "Taipei") -> Customer:
    now = datetime.now(UTC)
    return Customer(
        id=UUID("40000000-0000-0000-0000-000000000001"),
        tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        customer_code="CUST100",
        customer_name=name,
        owner_user_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        status="ACTIVE",
        deleted_at=None,
        deleted_by=None,
        row_version=1,
        created_at=now,
        updated_at=now,
        currency_code="USD",
        addresses=(
            CustomerAddress(
                id=UUID("60000000-0000-0000-0000-000000000001"),
                address_code="MAIN",
                address_type="SOLD_TO",
                address1="Road",
                city=city,
                country_code="TW",
                is_default=True,
            ),
        ),
    )


def test_customer_diff_uses_business_paths_and_omits_unchanged_values() -> None:
    service = AuditDiffService()
    before = service.customer_snapshot(customer())
    after = service.customer_snapshot(customer(name="ACME Taiwan", city="New Taipei"))

    changes = service.diff(before, after)

    assert [(change.field_path, change.old_value, change.new_value) for change in changes] == [
        ("addresses[MAIN].city", "Taipei", "New Taipei"),
        ("customer.customer_name", "ACME", "ACME Taiwan"),
    ]
    assert all(change.change_type == AuditChangeType.UPDATE for change in changes)
    assert service.diff(after, after) == []


def test_create_diff_records_adds_without_technical_fields() -> None:
    service = AuditDiffService()
    changes = service.diff(None, service.customer_snapshot(customer()))
    paths = {change.field_path for change in changes}
    assert "customer.customer_code" in paths
    assert "addresses[MAIN].city" in paths
    assert "row_version" not in " ".join(paths)
    assert all(change.old_value is None for change in changes)


def test_sensitive_policy_redacts_values_centrally() -> None:
    changes = AuditDiffService().diff(
        {"authentication.refresh_token": AuditField("Refresh Token", "old-secret")},
        {"authentication.refresh_token": AuditField("Refresh Token", "new-secret")},
    )
    assert changes[0].is_sensitive is True
    assert changes[0].old_value is None
    assert changes[0].new_value is None
    assert changes[0].old_display_value == "[REDACTED]"
    assert changes[0].new_display_value == "[REDACTED]"


def test_system_actor_context_is_independent_from_edi_source() -> None:
    context = AuditContext.for_system(
        tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        display_name="EDI_ENGINE",
        source=AuditSource.EDI,
        correlation_id="edi-1",
    )
    assert context.actor_type == AuditActorType.SYSTEM
    assert context.actor_user_id is None
    assert context.actor_display_name == "EDI_ENGINE"
    assert context.source == AuditSource.EDI
