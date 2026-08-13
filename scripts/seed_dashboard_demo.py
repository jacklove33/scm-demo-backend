"""Seed deterministic local Customer PO data for Dashboard and World Map demos."""

import asyncio
import logging
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.modules.customer_pos.domain.enums import (
    CustomerPoSource,
    CustomerPoStatus,
    CustomerPoStatusEventType,
)
from app.modules.customer_pos.domain.events import (
    CustomerPoEventActorType,
    CustomerPoEventCategory,
    CustomerPoEventSource,
    CustomerPoEventType,
)
from app.modules.customer_pos.infrastructure.models import (
    CustomerPoEventModel,
    CustomerPoLineModel,
    CustomerPoModel,
    CustomerPoStatusEventModel,
)
from app.modules.customers.infrastructure.models import BusinessPartnerModel
from app.modules.iam.infrastructure.models import ProfileModel, TenantModel

logger = logging.getLogger("seed_dashboard_demo")

TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
PREFIX = "DEMO-DASH-"
ANCHOR_DATE = date(2026, 8, 1)
CUSTOMER_CODES = ("CUST001", "CUST002", "CUST003", "CUST004")
OWNER_EMAILS = (
    "kevin@local.test",
    "jack@local.test",
    "mary@local.test",
    "warehouse@local.test",
)

STATUS_VALUES = (
    [CustomerPoStatus.CONVERTED] * 15
    + [CustomerPoStatus.RECEIVED] * 7
    + [CustomerPoStatus.VALIDATING] * 5
    + [CustomerPoStatus.VALIDATED] * 5
    + [CustomerPoStatus.PROCESSING] * 5
    + [CustomerPoStatus.ON_HOLD] * 5
    + [CustomerPoStatus.DRAFT] * 2
    + [CustomerPoStatus.REJECTED] * 2
    + [CustomerPoStatus.CANCELLED] * 2
)
SOURCE_VALUES = (
    [CustomerPoSource.EDI] * 17
    + [CustomerPoSource.API] * 12
    + [CustomerPoSource.IMPORT] * 10
    + [CustomerPoSource.MANUAL] * 9
)
CUSTOMER_VALUES = ["CUST001"] * 17 + ["CUST002"] * 12 + ["CUST003"] * 11 + ["CUST004"] * 8
COUNTRY_VALUES = (
    ["US"] * 14
    + ["TW"] * 10
    + ["JP"] * 7
    + ["DE"] * 5
    + ["SG"] * 4
    + ["CN"] * 3
    + ["KR"] * 3
    + ["GB"] * 2
)
COUNTRY_DETAILS = {
    "US": ("USD", "Seattle", "United States Distribution Center"),
    "TW": ("TWD", "Taipei", "Taiwan Operations Center"),
    "JP": ("JPY", "Tokyo", "Japan Customer Center"),
    "DE": ("EUR", "Munich", "Germany Distribution Center"),
    "SG": ("USD", "Singapore", "Singapore Regional Hub"),
    "CN": ("USD", "Shanghai", "China Customer Center"),
    "KR": ("USD", "Seoul", "Korea Customer Center"),
    "GB": ("EUR", "London", "United Kingdom Customer Center"),
}


@dataclass(frozen=True, slots=True)
class DemoPoSpec:
    sequence: int
    po_number: str
    customer_code: str
    status: CustomerPoStatus
    source: CustomerPoSource
    country_code: str
    currency_code: str
    city: str
    ship_to_name: str
    po_date: date
    line_count: int


def stable_uuid(key: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"scm-demo-dashboard:{key}")


def build_specs() -> tuple[DemoPoSpec, ...]:
    specs = []
    for index in range(48):
        sequence = index + 1
        country = COUNTRY_VALUES[(index * 5) % 48]
        currency, city, ship_to_name = COUNTRY_DETAILS[country]
        specs.append(
            DemoPoSpec(
                sequence=sequence,
                po_number=f"{PREFIX}{sequence:03d}",
                customer_code=CUSTOMER_VALUES[(index * 17) % 48],
                status=STATUS_VALUES[(index * 13) % 48],
                source=SOURCE_VALUES[(index * 19) % 48],
                country_code=country,
                currency_code=currency,
                city=city,
                ship_to_name=ship_to_name,
                po_date=ANCHOR_DATE - timedelta(days=(index * 11) % 181),
                line_count=1 + index % 4,
            )
        )
    return tuple(specs)


def amount_components(spec: DemoPoSpec, line_number: int) -> tuple[Decimal, Decimal]:
    quantity = Decimal(5 + (spec.sequence * 3 + line_number * 7) % 46)
    base_prices = {
        "USD": Decimal("625"),
        "TWD": Decimal("18750"),
        "JPY": Decimal("62500"),
        "EUR": Decimal("575"),
    }
    unit_price = base_prices[spec.currency_code] + Decimal(
        (spec.sequence * 37 + line_number * 113) % 900
    )
    return quantity, unit_price


def validate_spec(spec: DemoPoSpec, total: Decimal, line_total: Decimal) -> None:
    if not spec.po_date or len(spec.country_code) != 2 or len(spec.currency_code) != 3:
        raise RuntimeError(f"Invalid required dashboard fields for {spec.po_number}")
    if spec.status not in CustomerPoStatus or spec.source not in CustomerPoSource:
        raise RuntimeError(f"Invalid enum value for {spec.po_number}")
    if total != line_total:
        raise RuntimeError(f"Header and line totals differ for {spec.po_number}")


async def resolve_fixtures(
    session: AsyncSession,
) -> tuple[dict[str, BusinessPartnerModel], list[ProfileModel]]:
    if await session.get(TenantModel, TENANT_ID) is None:
        raise RuntimeError(f"Required demo tenant does not exist: {TENANT_ID}")
    customers = (
        await session.scalars(
            select(BusinessPartnerModel).where(
                BusinessPartnerModel.tenant_id == TENANT_ID,
                BusinessPartnerModel.partner_code.in_(CUSTOMER_CODES),
                BusinessPartnerModel.deleted_at.is_(None),
            )
        )
    ).all()
    by_code = {customer.partner_code: customer for customer in customers}
    missing = sorted(set(CUSTOMER_CODES) - by_code.keys())
    if missing:
        raise RuntimeError(f"Required demo customers do not exist: {', '.join(missing)}")
    owners = (
        await session.scalars(
            select(ProfileModel)
            .where(
                ProfileModel.tenant_id == TENANT_ID,
                ProfileModel.email.in_(OWNER_EMAILS),
                ProfileModel.is_active.is_(True),
            )
            .order_by(ProfileModel.email)
        )
    ).all()
    if len(owners) < 2:
        raise RuntimeError("At least two active canonical demo owners are required")
    return by_code, list(owners)


def build_models(
    spec: DemoPoSpec, customer: BusinessPartnerModel, owner: ProfileModel
) -> tuple[
    CustomerPoModel,
    list[CustomerPoLineModel],
    CustomerPoStatusEventModel,
    CustomerPoEventModel,
]:
    po_id = stable_uuid(spec.po_number)
    occurred_at = datetime.combine(spec.po_date, datetime.min.time(), tzinfo=UTC) + timedelta(
        hours=9
    )
    delivery_date = spec.po_date + timedelta(days=14 + spec.sequence % 14)
    lines = []
    total = Decimal("0")
    for line_index in range(spec.line_count):
        line_number = (line_index + 1) * 10
        quantity, unit_price = amount_components(spec, line_number)
        line_amount = quantity * unit_price
        total += line_amount
        lines.append(
            CustomerPoLineModel(
                id=stable_uuid(f"{spec.po_number}:line:{line_number}"),
                tenant_id=TENANT_ID,
                customer_po_id=po_id,
                line_number=line_number,
                customer_item_number=f"DEMO-{spec.sequence:03d}-{line_number}",
                item_description=f"Dashboard demo product {1 + line_index}",
                ordered_quantity=quantity,
                unit_of_measure="EA",
                unit_price=unit_price,
                line_amount=line_amount,
                currency_code=spec.currency_code,
                requested_delivery_date=delivery_date,
                row_version=1,
                created_at=occurred_at,
                updated_at=occurred_at,
            )
        )
    validate_spec(spec, total, sum((line.line_amount or Decimal("0") for line in lines), Decimal()))
    po = CustomerPoModel(
        id=po_id,
        tenant_id=TENANT_ID,
        customer_id=customer.id,
        customer_po_number=spec.po_number,
        customer_po_date=spec.po_date,
        received_at=occurred_at if spec.source != CustomerPoSource.MANUAL else None,
        requested_ship_date=spec.po_date + timedelta(days=7 + spec.sequence % 7),
        requested_delivery_date=delivery_date,
        currency_code=spec.currency_code,
        ship_to_name=spec.ship_to_name,
        ship_to_city=spec.city,
        ship_to_country_code=spec.country_code,
        status=spec.status.value,
        source=spec.source.value,
        owner_user_id=owner.id,
        total_amount=total,
        row_version=1,
        created_at=occurred_at,
        updated_at=occurred_at,
        created_by=owner.id,
        updated_by=owner.id,
        edi_transaction_type="850" if spec.source == CustomerPoSource.EDI else None,
        edi_standard="X12" if spec.source == CustomerPoSource.EDI else None,
        edi_version="004010" if spec.source == CustomerPoSource.EDI else None,
        edi_sender_id=f"DEMO-SENDER-{spec.sequence:03d}"
        if spec.source == CustomerPoSource.EDI
        else None,
        edi_receiver_id="SCM-DEMO" if spec.source == CustomerPoSource.EDI else None,
        edi_interchange_control_number=f"{spec.sequence:09d}"
        if spec.source == CustomerPoSource.EDI
        else None,
        edi_group_control_number=f"{spec.sequence:06d}"
        if spec.source == CustomerPoSource.EDI
        else None,
        edi_transaction_control_number=f"{spec.sequence:04d}"
        if spec.source == CustomerPoSource.EDI
        else None,
        edi_received_at=occurred_at if spec.source == CustomerPoSource.EDI else None,
    )
    status_event = CustomerPoStatusEventModel(
        id=stable_uuid(f"{spec.po_number}:status"),
        tenant_id=TENANT_ID,
        customer_po_id=po_id,
        from_status=None,
        to_status=spec.status.value,
        event_type=CustomerPoStatusEventType.CREATED.value,
        actor_user_id=owner.id,
        source=spec.source.value,
        correlation_id=f"seed:{spec.po_number}",
        metadata_json={"seed": "dashboard_demo"},
        occurred_at=occurred_at,
    )
    business_event = CustomerPoEventModel(
        id=stable_uuid(f"{spec.po_number}:event:create"),
        tenant_id=TENANT_ID,
        customer_po_id=po_id,
        event_type=CustomerPoEventType.CREATE.value,
        event_category=CustomerPoEventCategory.GENERAL.value,
        title="Customer PO created",
        description=f"PO {spec.po_number} was created.",
        actor_type=CustomerPoEventActorType.USER.value,
        actor_user_id=owner.id,
        actor_display_name=owner.display_name,
        source=CustomerPoEventSource.SYSTEM.value,
        correlation_id=f"seed:{spec.po_number}",
        request_id=None,
        metadata_json={"source": spec.source.value, "seed": "dashboard_demo"},
        occurred_at=occurred_at,
        created_at=occurred_at,
    )
    return po, lines, status_event, business_event


async def seed(
    session: AsyncSession,
) -> tuple[int, int, tuple[DemoPoSpec, ...], list[ProfileModel]]:
    customers, owners = await resolve_fixtures(session)
    specs = build_specs()
    existing = set(
        await session.scalars(
            select(CustomerPoModel.customer_po_number).where(
                CustomerPoModel.tenant_id == TENANT_ID,
                CustomerPoModel.customer_po_number.in_(spec.po_number for spec in specs),
            )
        )
    )
    created = 0
    pending_lines: list[CustomerPoLineModel] = []
    pending_status_events: list[CustomerPoStatusEventModel] = []
    pending_business_events: list[CustomerPoEventModel] = []
    for index, spec in enumerate(specs):
        if spec.po_number in existing:
            continue
        po, lines, status_event, business_event = build_models(
            spec, customers[spec.customer_code], owners[index % len(owners)]
        )
        session.add(po)
        pending_lines.extend(lines)
        pending_status_events.append(status_event)
        pending_business_events.append(business_event)
        created += 1
    # These models intentionally have no ORM relationships; explicit stages guarantee FK order.
    await session.flush()
    session.add_all(pending_lines)
    await session.flush()
    session.add_all(pending_status_events)
    session.add_all(pending_business_events)
    await session.flush()
    eligible = int(
        await session.scalar(
            select(CustomerPoModel)
            .where(
                CustomerPoModel.tenant_id == TENANT_ID,
                CustomerPoModel.customer_po_number.like(f"{PREFIX}%"),
                CustomerPoModel.deleted_at.is_(None),
                CustomerPoModel.customer_po_date.is_not(None),
            )
            .with_only_columns(func.count())
        )
        or 0
    )
    country_eligible = int(
        await session.scalar(
            select(CustomerPoModel)
            .where(
                CustomerPoModel.tenant_id == TENANT_ID,
                CustomerPoModel.customer_po_number.like(f"{PREFIX}%"),
                CustomerPoModel.deleted_at.is_(None),
                CustomerPoModel.customer_po_date.is_not(None),
                CustomerPoModel.ship_to_country_code.is_not(None),
            )
            .with_only_columns(func.count())
        )
        or 0
    )
    if eligible != 48 or country_eligible != 48:
        raise RuntimeError(
            f"Seed verification failed: dashboard={eligible}, world_map={country_eligible}"
        )
    return created, len(specs) - created, specs, owners


def distribution(specs: tuple[DemoPoSpec, ...], field: str) -> str:
    normalized = []
    for spec in specs:
        value = getattr(spec, field)
        normalized.append(str(value.value if hasattr(value, "value") else value))
    values = Counter(normalized)
    return ", ".join(f"{key}={values[key]}" for key in sorted(values))


async def run() -> None:
    if settings.app_env != "local":
        raise RuntimeError("Dashboard demo seed is restricted to APP_ENV=local")
    database_url = settings.migration_database_url or settings.database_url
    engine = create_async_engine(database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session, session.begin():
            created, skipped, specs, owners = await seed(session)
        logger.info("Dashboard demo seed complete")
        logger.info("Tenant: %s", TENANT_ID)
        logger.info("Created: %s POs", created)
        logger.info("Skipped existing: %s", skipped)
        logger.info("Owners: %s", ", ".join(owner.display_name for owner in owners))
        for label, field in (
            ("By status", "status"),
            ("By source", "source"),
            ("By country", "country_code"),
            ("By currency", "currency_code"),
        ):
            logger.info("%s: %s", label, distribution(specs, field))
    finally:
        await engine.dispose()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    asyncio.run(run())


if __name__ == "__main__":
    main()
