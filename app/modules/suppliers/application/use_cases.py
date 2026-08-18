import logging
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
from app.modules.audit.application.audit_writer import AuditWriter
from app.modules.audit.application.diff_service import AuditDiffService
from app.modules.audit.domain.entities import AuditContext
from app.modules.audit.domain.enums import AuditAction
from app.modules.suppliers.application.capabilities import SupplierCapabilityPolicy
from app.modules.suppliers.application.commands import (
    CreateSupplierCommand,
    SupplierImportRowCommand,
    UpdateSupplierCommand,
)
from app.modules.suppliers.application.dto import SupplierDTO
from app.modules.suppliers.domain.entities import Supplier, SupplierAddress
from app.modules.suppliers.domain.repository import (
    SupplierAccessFacts,
    SupplierRepository,
    SupplierSearchCriteria,
)
from app.shared.application.unit_of_work import UnitOfWork
from app.shared.domain.current_user import CurrentUser

logger = logging.getLogger(__name__)


class SupplierUseCases:
    MAX_IMPORT_ROWS = 500
    ADDRESS_TYPES = frozenset(
        {"SOLD_TO", "SHIP_TO", "BILL_TO", "REMIT_TO", "SUPPLIER_SITE", "WAREHOUSE", "OFFICE"}
    )
    EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

    def __init__(
        self,
        repository: SupplierRepository,
        capability_policy: SupplierCapabilityPolicy | None = None,
        audit_writer: AuditWriter | None = None,
        audit_diff: AuditDiffService | None = None,
        unit_of_work: UnitOfWork | None = None,
    ) -> None:
        self.repository = repository
        self.capability_policy = capability_policy or SupplierCapabilityPolicy()
        self.audit_writer = audit_writer
        self.audit_diff = audit_diff or AuditDiffService()
        self.unit_of_work = unit_of_work

    async def search(
        self, criteria: SupplierSearchCriteria, actor: CurrentUser
    ) -> tuple[list[SupplierDTO], int]:
        self._require(actor, "suppliers.read")
        page = await self.repository.search(
            criteria,
            actor_id=actor.user_id,
            tenant_id=actor.tenant_id,
            scope=actor.scope_for("suppliers.read"),
        )
        return [
            SupplierDTO.from_domain(
                item.supplier, self.capability_policy.evaluate(item.supplier, item.access, actor)
            )
            for item in page.items
        ], page.total

    async def list_payment_terms(self, actor: CurrentUser) -> list[tuple[UUID, str, str]]:
        if not (actor.can("suppliers.read") or actor.can("suppliers.create")):
            raise PermissionDenied("Missing Supplier read/create permission")
        return await self.repository.list_payment_terms(actor.tenant_id)

    async def get(self, supplier_id: UUID, actor: CurrentUser) -> SupplierDTO:
        self._require(actor, "suppliers.detail.read")
        supplier = await self.repository.get_by_id(
            supplier_id,
            actor_id=actor.user_id,
            tenant_id=actor.tenant_id,
            scope=actor.scope_for("suppliers.detail.read"),
        )
        if supplier is None:
            raise EntityNotFound("Supplier not found")
        access = await self.repository.get_access_facts(
            supplier_id, actor_id=actor.user_id, tenant_id=actor.tenant_id
        )
        return SupplierDTO.from_domain(
            supplier, self.capability_policy.evaluate(supplier, access, actor)
        )

    async def _validate_references(
        self, actor: CurrentUser, payment_term_id: UUID | None, owner_user_id: UUID | None
    ) -> None:
        if (
            payment_term_id
            and payment_term_id
            not in await self.repository.find_valid_payment_term_ids(
                actor.tenant_id, {payment_term_id}
            )
        ):
            raise ValidationFailure("Payment Term does not exist in this tenant")
        if owner_user_id and owner_user_id not in await self.repository.find_valid_owner_ids(
            actor.tenant_id, {owner_user_id}
        ):
            raise ValidationFailure("Owner is not an active user in this tenant")

    async def create(
        self,
        command: CreateSupplierCommand,
        actor: CurrentUser,
        context: AuditContext | None = None,
    ) -> SupplierDTO:
        self._require(actor, "suppliers.create")
        code = Supplier.normalize_code(command.supplier_code)
        partner_exists, existing_owner_id = await self.repository.find_existing_partner_owner(
            actor.tenant_id, code
        )
        owner_id = command.owner_user_id
        if owner_id is None:
            owner_id = existing_owner_id if partner_exists else actor.user_id
        if (
            command.owner_user_id is not None
            and owner_id != actor.user_id
            and not actor.can("suppliers.assign_owner")
        ):
            raise PermissionDenied("Cannot assign supplier owner")
        if not Supplier.is_valid_code(code):
            raise ValidationFailure(
                "Supplier Code must match ^[A-Z][A-Z0-9_-]*$ and be at most 20 characters"
            )
        await self._validate_references(actor, command.payment_term_id, owner_id)
        now = datetime.now(UTC)
        addresses = (
            (SupplierAddress(id=uuid4(), **asdict(command.default_address)),)
            if command.default_address
            else ()
        )
        value = Supplier(
            uuid4(),
            actor.tenant_id,
            code,
            Supplier.normalize_name(command.supplier_name),
            owner_id,
            actor.display_name if owner_id == actor.user_id else None,
            command.status,
            None,
            None,
            1,
            now,
            now,
            command.tax_id,
            command.country_code,
            command.currency_code,
            command.payment_term_id,
            addresses,
        )
        try:
            created = await self.repository.create(value)
            await self._audit(context, AuditAction.CREATE, None, created)
            await self._commit()
        except Exception:
            await self._rollback()
            raise
        access = SupplierAccessFacts(created.owner_user_id == actor.user_id, False, False)
        logger.info(
            "Supplier created",
            extra={
                "business_module": "supplier",
                "entity_type": "supplier",
                "entity_id": str(created.id),
                "entity_code": created.supplier_code,
            },
        )
        return SupplierDTO.from_domain(
            created, self.capability_policy.evaluate(created, access, actor)
        )

    async def import_suppliers(
        self,
        rows: list[SupplierImportRowCommand],
        actor: CurrentUser,
        context: AuditContext | None = None,
    ) -> int:
        self._require(actor, "suppliers.create")
        if not rows or len(rows) > self.MAX_IMPORT_ROWS:
            message = "At least one row is required" if not rows else "Maximum 500 rows are allowed"
            raise ImportValidationFailure(
                "Supplier import validation failed",
                details={"errors": [self._import_error(0, "rows", "INVALID_SIZE", message)]},
            )
        normalized: list[SupplierImportRowCommand] = []
        errors: list[dict[str, object]] = []
        codes: dict[str, list[int]] = {}
        for row in rows:
            item, item_errors = self._normalize_import_row(row)
            normalized.append(item)
            errors.extend(item_errors)
            if item.supplier_code:
                codes.setdefault(item.supplier_code, []).append(item.row_number)
        for code, numbers in codes.items():
            if len(numbers) > 1:
                errors.extend(
                    self._import_error(
                        n,
                        "supplier_code",
                        "DUPLICATE_IN_FILE",
                        f"Supplier Code {code} is duplicated in this import",
                    )
                    for n in numbers
                )
        if any(
            row.owner_user_id not in (None, actor.user_id) for row in normalized
        ) and not actor.can("suppliers.assign_owner"):
            raise PermissionDenied("Cannot assign supplier owner")
        payment_ids = {row.payment_term_id for row in normalized if row.payment_term_id}
        owner_ids = {row.owner_user_id for row in normalized if row.owner_user_id}
        valid_payments = await self.repository.find_valid_payment_term_ids(
            actor.tenant_id, payment_ids
        )
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
            raise ImportValidationFailure(
                "Supplier import validation failed", details={"errors": errors}
            )
        created: list[Supplier] = []
        try:
            for row in normalized:
                try:
                    created.append(
                        await self.repository.create(self._import_row_to_supplier(row, actor))
                    )
                except EntityConflict as exc:
                    raise ImportValidationFailure(
                        "Supplier import validation failed",
                        details={
                            "errors": [
                                self._import_error(
                                    row.row_number,
                                    "supplier_code",
                                    "BUSINESS_PARTNER_CONFLICT",
                                    exc.message,
                                )
                            ]
                        },
                    ) from exc
            batch_id = uuid4()
            for supplier in created:
                await self._audit(context, AuditAction.IMPORT, None, supplier, batch_id=batch_id)
            await self._commit()
        except Exception:
            await self._rollback()
            raise
        logger.info(
            "Supplier import completed",
            extra={"business_module": "supplier", "imported_count": len(created)},
        )
        return len(created)

    @staticmethod
    def _import_error(row_number: int, field: str, code: str, message: str) -> dict[str, object]:
        return {"row_number": row_number, "field": field, "code": code, "message": message}

    def _normalize_import_row(
        self, row: SupplierImportRowCommand
    ) -> tuple[SupplierImportRowCommand, list[dict[str, object]]]:
        def clean(value: str | None, *, upper: bool = False) -> str | None:
            result = value.strip() if value is not None else None
            return result.upper() if upper and result else result

        item = SupplierImportRowCommand(
            row.row_number,
            clean(row.supplier_code, upper=True),
            clean(row.supplier_name),
            clean(row.tax_id),
            clean(row.country_code, upper=True),
            clean(row.currency_code, upper=True),
            row.payment_term_id,
            row.owner_user_id,
            clean(row.status, upper=True) or "ACTIVE",
            clean(row.address_type, upper=True),
            clean(row.address_code, upper=True),
            clean(row.contact_name),
            clean(row.address_line1),
            clean(row.address_line2),
            clean(row.city),
            clean(row.state),
            clean(row.postal_code),
            clean(row.address_country_code, upper=True),
            clean(row.phone),
            clean(row.email),
            True,
        )
        errors: list[dict[str, object]] = []
        for field, value, label in (
            ("supplier_code", item.supplier_code, "Supplier Code"),
            ("supplier_name", item.supplier_name, "Supplier Name"),
            ("address_type", item.address_type, "Address Type"),
            ("address_code", item.address_code, "Address Code"),
            ("address_line1", item.address_line1, "Address Line 1"),
            ("address_country_code", item.address_country_code, "Address Country Code"),
        ):
            if not value:
                errors.append(
                    self._import_error(item.row_number, field, "REQUIRED", f"{label} is required")
                )
        if item.supplier_code and not Supplier.is_valid_code(item.supplier_code):
            errors.append(
                self._import_error(
                    item.row_number,
                    "supplier_code",
                    "INVALID_SUPPLIER_CODE",
                    "Supplier Code format is invalid",
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
        for field, value, size in (
            ("country_code", item.country_code, 2),
            ("currency_code", item.currency_code, 3),
            ("address_country_code", item.address_country_code, 2),
        ):
            if value and len(value) != size:
                errors.append(
                    self._import_error(
                        item.row_number, field, "INVALID_VALUE", f"Must contain {size} characters"
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
    def _import_row_to_supplier(row: SupplierImportRowCommand, actor: CurrentUser) -> Supplier:
        now = datetime.now(UTC)
        address = SupplierAddress(
            uuid4(),
            row.address_code or "",
            row.address_type or "",
            row.contact_name,
            row.address_line1,
            row.address_line2,
            row.city,
            row.state,
            row.postal_code,
            row.address_country_code,
            row.phone,
            row.email,
            True,
        )
        return Supplier(
            uuid4(),
            actor.tenant_id,
            row.supplier_code or "",
            Supplier.normalize_name(row.supplier_name or ""),
            row.owner_user_id or actor.user_id,
            actor.display_name if row.owner_user_id in (None, actor.user_id) else None,
            row.status or "ACTIVE",
            None,
            None,
            1,
            now,
            now,
            row.tax_id,
            row.country_code,
            row.currency_code,
            row.payment_term_id,
            (address,),
        )

    async def update(
        self,
        command: UpdateSupplierCommand,
        actor: CurrentUser,
        context: AuditContext | None = None,
    ) -> SupplierDTO:
        self._require(actor, "suppliers.update")
        scope = actor.scope_for("suppliers.update")
        before = await self.repository.get_by_id(
            command.supplier_id, actor_id=actor.user_id, tenant_id=actor.tenant_id, scope=scope
        )
        if before is None:
            raise EntityNotFound("Supplier not found")
        if command.owner_user_id != before.owner_user_id and not actor.can(
            "suppliers.assign_owner"
        ):
            raise PermissionDenied("Cannot assign supplier owner")
        await self._validate_references(actor, command.payment_term_id, command.owner_user_id)
        try:
            changed = await self.repository.update(
                command.supplier_id,
                command.expected_version,
                {
                    "partner_name": Supplier.normalize_name(command.supplier_name),
                    "tax_id": command.tax_id,
                    "country_code": command.country_code,
                    "currency_code": command.currency_code,
                    "payment_term_id": command.payment_term_id,
                    "owner_user_id": command.owner_user_id,
                    "status": command.status,
                },
                actor_id=actor.user_id,
                tenant_id=actor.tenant_id,
                scope=scope,
            )
            if changed is None:
                raise EntityNotFound("Supplier not found or outside allowed scope")
            await self._audit(context, AuditAction.UPDATE, before, changed)
            await self._commit()
        except Exception:
            await self._rollback()
            raise
        access = await self.repository.get_access_facts(
            changed.id, actor_id=actor.user_id, tenant_id=actor.tenant_id
        )
        return SupplierDTO.from_domain(
            changed, self.capability_policy.evaluate(changed, access, actor)
        )

    async def soft_delete(
        self,
        supplier_id: UUID,
        expected_version: int,
        actor: CurrentUser,
        context: AuditContext | None = None,
    ) -> None:
        await self._change_deleted(supplier_id, expected_version, actor, context, restore=False)

    async def restore(
        self,
        supplier_id: UUID,
        expected_version: int,
        actor: CurrentUser,
        context: AuditContext | None = None,
    ) -> None:
        await self._change_deleted(supplier_id, expected_version, actor, context, restore=True)

    async def _change_deleted(
        self,
        supplier_id: UUID,
        expected_version: int,
        actor: CurrentUser,
        context: AuditContext | None,
        *,
        restore: bool,
    ) -> None:
        code = "suppliers.restore" if restore else "suppliers.delete"
        self._require(actor, code)
        scope = actor.scope_for(code)
        before = await self.repository.get_by_id(
            supplier_id,
            actor_id=actor.user_id,
            tenant_id=actor.tenant_id,
            scope=scope,
            include_deleted=restore,
        )
        if before is None:
            raise EntityNotFound("Supplier not found or outside allowed scope")
        try:
            method = self.repository.restore if restore else self.repository.soft_delete
            changed = await method(
                supplier_id,
                expected_version,
                actor_id=actor.user_id,
                tenant_id=actor.tenant_id,
                scope=scope,
            )
            if changed is None:
                raise EntityNotFound("Supplier not found or outside allowed scope")
            await self._audit(
                context, AuditAction.RESTORE if restore else AuditAction.DELETE, before, changed
            )
            await self._commit()
        except Exception:
            await self._rollback()
            raise

    async def _audit(
        self,
        context: AuditContext | None,
        action: AuditAction,
        before: Supplier | None,
        after: Supplier,
        batch_id: UUID | None = None,
    ) -> None:
        if not self.audit_writer or not context:
            return
        changes = self.audit_diff.diff(
            self.audit_diff.supplier_snapshot(before) if before else None,
            self.audit_diff.supplier_snapshot(after),
        )
        await self.audit_writer.write_event(
            context=context,
            action=action,
            module="SUPPLIER",
            batch_id=batch_id,
            entity_type="SUPPLIER",
            entity_id=after.id,
            entity_code=after.supplier_code,
            entity_display_name=after.supplier_name,
            changes=changes,
        )

    async def _commit(self) -> None:
        if self.unit_of_work:
            await self.unit_of_work.commit()

    async def _rollback(self) -> None:
        if self.unit_of_work:
            await self.unit_of_work.rollback()

    @staticmethod
    def _require(actor: CurrentUser, code: str) -> None:
        if not actor.can(code):
            raise PermissionDenied(f"Missing permission: {code}")
