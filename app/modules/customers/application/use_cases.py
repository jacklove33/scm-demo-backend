import re
from dataclasses import asdict
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.core.exceptions import (
    EntityConflict,
    EntityNotFound,
    ImportValidationFailure,
    PermissionDenied,
    ValidationFailure,
)
from app.modules.customers.application.capabilities import CustomerCapabilityPolicy
from app.modules.customers.application.commands import (
    CreateCustomerCommand,
    CustomerImportRowCommand,
    UpdateCustomerCommand,
)
from app.modules.customers.application.dto import CustomerDTO, CustomerSearchDTO
from app.modules.customers.domain.entities import Customer, CustomerAddress
from app.modules.customers.domain.repository import (
    CustomerAccessFacts,
    CustomerRepository,
    CustomerSearchCriteria,
)
from app.shared.domain.current_user import CurrentUser


class CustomerUseCases:
    """No role checks here. Authorization is permission + scope only."""

    MAX_IMPORT_ROWS = 500
    ADDRESS_TYPES = frozenset(
        {"SOLD_TO", "SHIP_TO", "BILL_TO", "REMIT_TO", "SUPPLIER_SITE", "WAREHOUSE", "OFFICE"}
    )
    EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

    def __init__(
        self,
        repository: CustomerRepository,
        capability_policy: CustomerCapabilityPolicy | None = None,
    ) -> None:
        self.repository = repository
        self.capability_policy = capability_policy or CustomerCapabilityPolicy()

    async def search(
        self,
        criteria: CustomerSearchCriteria,
        actor: CurrentUser,
    ) -> tuple[list[CustomerSearchDTO], int]:
        self._require(actor, "customers.read")
        scope = actor.scope_for("customers.read")

        page = await self.repository.search(
            criteria,
            actor_id=actor.user_id,
            tenant_id=actor.tenant_id,
            scope=scope,
        )
        return [
            CustomerSearchDTO.from_domain(
                item.customer,
                self.capability_policy.evaluate(item.customer, item.access, actor),
            )
            for item in page.items
        ], page.total

    async def get(self, customer_id: UUID, actor: CurrentUser) -> CustomerDTO:
        self._require(actor, "customers.detail.read")
        scope = actor.scope_for("customers.detail.read")

        customer = await self.repository.get_by_id(
            customer_id,
            actor_id=actor.user_id,
            tenant_id=actor.tenant_id,
            scope=scope,
        )
        if customer is None:
            # 404 avoids leaking whether a forbidden row exists.
            raise EntityNotFound("Customer not found")

        access = await self.repository.get_access_facts(
            customer_id, actor_id=actor.user_id, tenant_id=actor.tenant_id
        )
        return CustomerDTO.from_domain(
            customer, self.capability_policy.evaluate(customer, access, actor)
        )

    async def create(self, command: CreateCustomerCommand, actor: CurrentUser) -> CustomerDTO:
        self._require(actor, "customers.create")

        owner_user_id = command.owner_user_id
        if owner_user_id is not None and not actor.can("customers.assign_owner"):
            # A user without owner-assignment permission may only create for self.
            if owner_user_id != actor.user_id:
                raise PermissionDenied("Cannot assign customer owner")

        if owner_user_id is None:
            owner_user_id = actor.user_id

        code = Customer.normalize_code(command.customer_code)
        if not Customer.is_valid_code(code):
            raise ValidationFailure(
                "Customer Code must match ^[A-Z][A-Z0-9_-]*$ and be at most 20 characters"
            )
        now = datetime.now(UTC)
        addresses: tuple[CustomerAddress, ...] = ()
        if command.default_address:
            address = command.default_address
            addresses = (CustomerAddress(id=uuid4(), **asdict(address)),)
        customer = Customer(
            id=uuid4(),
            tenant_id=actor.tenant_id,
            customer_code=code,
            customer_name=Customer.normalize_name(command.customer_name),
            tax_id=command.tax_id,
            country_code=command.country_code,
            currency_code=command.currency_code,
            payment_term_id=command.payment_term_id,
            owner_user_id=owner_user_id,
            status=command.status,
            deleted_at=None,
            deleted_by=None,
            row_version=1,
            created_at=now,
            updated_at=now,
            addresses=addresses,
        )
        created = await self.repository.create(customer)
        access = CustomerAccessFacts(
            is_owner=created.owner_user_id == actor.user_id,
            is_assigned=False,
            is_team_assigned=False,
        )
        return CustomerDTO.from_domain(
            created, self.capability_policy.evaluate(created, access, actor)
        )

    async def import_customers(
        self, rows: list[CustomerImportRowCommand], actor: CurrentUser
    ) -> int:
        self._require(actor, "customers.create")
        if not rows or len(rows) > self.MAX_IMPORT_ROWS:
            code, message = (
                ("REQUIRED", "At least one row is required")
                if not rows
                else ("MAX_ROWS", f"Maximum {self.MAX_IMPORT_ROWS} rows are allowed")
            )
            self._raise_import_errors([self._import_error(0, "rows", code, message)])

        errors: list[dict[str, object]] = []
        normalized: list[CustomerImportRowCommand] = []
        rows_by_code: dict[str, list[int]] = {}
        for row in rows:
            item, row_errors = self._normalize_import_row(row)
            normalized.append(item)
            errors.extend(row_errors)
            if item.customer_code:
                rows_by_code.setdefault(item.customer_code, []).append(item.row_number)

        for code, row_numbers in rows_by_code.items():
            if len(row_numbers) > 1:
                errors.extend(
                    self._import_error(
                        number,
                        "customer_code",
                        "DUPLICATE_IN_FILE",
                        f"Customer Code {code} is duplicated in this import",
                    )
                    for number in row_numbers
                )

        if any(row.owner_user_id not in (None, actor.user_id) for row in normalized):
            if not actor.can("customers.assign_owner"):
                raise PermissionDenied("Cannot assign customer owner")

        if errors:
            self._raise_import_errors(errors)

        codes = {row.customer_code for row in normalized if row.customer_code}
        existing = await self.repository.find_existing_codes(actor.tenant_id, codes)
        if existing:
            raise EntityConflict(
                "One or more Business Partner Codes already exist",
                details={
                    "errors": [
                        self._import_error(
                            row.row_number,
                            "customer_code",
                            "ALREADY_EXISTS",
                            f"Business Partner Code {row.customer_code} already exists",
                        )
                        for row in normalized
                        if row.customer_code in existing
                    ]
                },
            )

        payment_ids = {row.payment_term_id for row in normalized if row.payment_term_id}
        valid_payments = await self.repository.find_valid_payment_term_ids(
            actor.tenant_id, payment_ids
        )
        owner_ids = {row.owner_user_id for row in normalized if row.owner_user_id}
        valid_owners = await self.repository.find_valid_owner_ids(actor.tenant_id, owner_ids)
        for row in normalized:
            if row.payment_term_id and row.payment_term_id not in valid_payments:
                errors.append(
                    self._import_error(
                        row.row_number,
                        "payment_term_id",
                        "INVALID_REFERENCE",
                        "Payment Term does not exist in this tenant",
                    )
                )
            if row.owner_user_id and row.owner_user_id not in valid_owners:
                errors.append(
                    self._import_error(
                        row.row_number,
                        "owner_user_id",
                        "INVALID_REFERENCE",
                        "Owner is not an active user in this tenant",
                    )
                )
        if errors:
            self._raise_import_errors(errors)

        await self.repository.create_many(
            [self._import_row_to_customer(row, actor) for row in normalized]
        )
        return len(normalized)

    @staticmethod
    def _import_error(row_number: int, field: str, code: str, message: str) -> dict[str, object]:
        return {"row_number": row_number, "field": field, "code": code, "message": message}

    @staticmethod
    def _raise_import_errors(errors: list[dict[str, object]]) -> None:
        raise ImportValidationFailure(
            "Customer import validation failed", details={"errors": errors}
        )

    def _normalize_import_row(
        self, row: CustomerImportRowCommand
    ) -> tuple[CustomerImportRowCommand, list[dict[str, object]]]:
        def clean(value: str | None, *, upper: bool = False) -> str | None:
            result = value.strip() if value is not None else None
            return result.upper() if upper and result else result

        item = CustomerImportRowCommand(
            row_number=row.row_number,
            customer_code=clean(row.customer_code, upper=True),
            customer_name=clean(row.customer_name),
            tax_id=clean(row.tax_id),
            country_code=clean(row.country_code, upper=True),
            currency_code=clean(row.currency_code, upper=True),
            payment_term_id=row.payment_term_id,
            owner_user_id=row.owner_user_id,
            status=clean(row.status, upper=True) or "ACTIVE",
            address_type=clean(row.address_type, upper=True),
            address_code=clean(row.address_code, upper=True),
            contact_name=clean(row.contact_name),
            address_line1=clean(row.address_line1),
            address_line2=clean(row.address_line2),
            city=clean(row.city),
            state=clean(row.state),
            postal_code=clean(row.postal_code),
            address_country_code=clean(row.address_country_code, upper=True),
            phone=clean(row.phone),
            email=clean(row.email),
            is_default=True,
        )
        errors: list[dict[str, object]] = []

        def required(field: str, value: object, label: str) -> None:
            if not value:
                errors.append(
                    self._import_error(item.row_number, field, "REQUIRED", f"{label} is required")
                )

        required("customer_code", item.customer_code, "Customer Code")
        required("customer_name", item.customer_name, "Customer Name")
        required("address_type", item.address_type, "Address Type")
        required("address_code", item.address_code, "Address Code")
        required("address_line1", item.address_line1, "Address Line 1")
        required("address_country_code", item.address_country_code, "Address Country Code")
        if item.customer_code and not Customer.is_valid_code(item.customer_code):
            errors.append(
                self._import_error(
                    item.row_number,
                    "customer_code",
                    "INVALID_CUSTOMER_CODE",
                    "Customer Code must match ^[A-Z][A-Z0-9_-]*$ and be at most 20 characters",
                )
            )
        if item.address_type and item.address_type not in self.ADDRESS_TYPES:
            errors.append(
                self._import_error(
                    item.row_number,
                    "address_type",
                    "INVALID_VALUE",
                    "Address Type is not supported",
                )
            )
        for field, value, size, label in (
            ("country_code", item.country_code, 2, "Country Code"),
            ("currency_code", item.currency_code, 3, "Currency Code"),
            ("address_country_code", item.address_country_code, 2, "Address Country Code"),
        ):
            if value and len(value) != size:
                errors.append(
                    self._import_error(
                        item.row_number,
                        field,
                        "INVALID_VALUE",
                        f"{label} must contain {size} characters",
                    )
                )
        if item.email and not self.EMAIL_PATTERN.fullmatch(item.email):
            errors.append(
                self._import_error(
                    item.row_number, "email", "INVALID_EMAIL", "Email address is invalid"
                )
            )
        return item, errors

    @staticmethod
    def _import_row_to_customer(row: CustomerImportRowCommand, actor: CurrentUser) -> Customer:
        now = datetime.now(UTC)
        address = CustomerAddress(
            id=uuid4(),
            address_code=row.address_code or "",
            address_type=row.address_type or "",
            contact_name=row.contact_name,
            address1=row.address_line1,
            address2=row.address_line2,
            city=row.city,
            state=row.state,
            postal_code=row.postal_code,
            country_code=row.address_country_code,
            phone=row.phone,
            email=row.email,
            is_default=True,
        )
        return Customer(
            id=uuid4(),
            tenant_id=actor.tenant_id,
            customer_code=row.customer_code or "",
            customer_name=Customer.normalize_name(row.customer_name or ""),
            owner_user_id=row.owner_user_id or actor.user_id,
            status=row.status or "ACTIVE",
            deleted_at=None,
            deleted_by=None,
            row_version=1,
            created_at=now,
            updated_at=now,
            tax_id=row.tax_id,
            country_code=row.country_code,
            currency_code=row.currency_code,
            payment_term_id=row.payment_term_id,
            addresses=(address,),
        )

    async def update(self, command: UpdateCustomerCommand, actor: CurrentUser) -> CustomerDTO:
        self._require(actor, "customers.update")
        scope = actor.scope_for("customers.update")

        owner_user_id = command.owner_user_id
        if owner_user_id is not None and not actor.can("customers.assign_owner"):
            # Do not silently allow changing ownership through the generic update API.
            existing = await self.repository.get_by_id(
                command.customer_id,
                actor_id=actor.user_id,
                tenant_id=actor.tenant_id,
                scope=scope,
            )
            if existing is None:
                raise EntityNotFound("Customer not found")
            if existing.owner_user_id != owner_user_id:
                raise PermissionDenied("Cannot assign customer owner")

        updated = await self.repository.update(
            command.customer_id,
            command.expected_version,
            {
                "partner_name": Customer.normalize_name(command.customer_name),
                "tax_id": command.tax_id,
                "country_code": command.country_code,
                "currency_code": command.currency_code,
                "payment_term_id": command.payment_term_id,
                "owner_user_id": owner_user_id,
                "status": command.status,
            },
            actor_id=actor.user_id,
            tenant_id=actor.tenant_id,
            scope=scope,
        )
        if updated is None:
            raise EntityNotFound("Customer not found or outside allowed scope")

        access = await self.repository.get_access_facts(
            updated.id, actor_id=actor.user_id, tenant_id=actor.tenant_id
        )
        return CustomerDTO.from_domain(
            updated, self.capability_policy.evaluate(updated, access, actor)
        )

    async def soft_delete(
        self,
        customer_id: UUID,
        expected_version: int,
        actor: CurrentUser,
    ) -> None:
        self._require(actor, "customers.delete")
        scope = actor.scope_for("customers.delete")

        changed = await self.repository.soft_delete(
            customer_id,
            expected_version,
            actor_id=actor.user_id,
            tenant_id=actor.tenant_id,
            scope=scope,
        )
        if not changed:
            raise EntityNotFound("Customer not found or outside allowed scope")

    async def restore(
        self,
        customer_id: UUID,
        expected_version: int,
        actor: CurrentUser,
    ) -> None:
        self._require(actor, "customers.restore")
        scope = actor.scope_for("customers.restore")

        changed = await self.repository.restore(
            customer_id,
            expected_version,
            actor_id=actor.user_id,
            tenant_id=actor.tenant_id,
            scope=scope,
        )
        if not changed:
            raise EntityNotFound("Customer not found or outside allowed scope")

    @staticmethod
    def _require(actor: CurrentUser, permission_code: str) -> None:
        if not actor.can(permission_code):
            raise PermissionDenied(f"Missing permission: {permission_code}")
