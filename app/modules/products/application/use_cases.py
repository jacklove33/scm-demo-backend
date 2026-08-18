from dataclasses import asdict
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.core.exceptions import (
    EntityNotFound,
    ImportValidationFailure,
    PermissionDenied,
    ValidationFailure,
)
from app.modules.audit.application.audit_writer import AuditWriter
from app.modules.audit.application.diff_service import AuditDiffService
from app.modules.audit.domain.entities import AuditContext
from app.modules.audit.domain.enums import AuditAction
from app.modules.products.application.capabilities import ProductCapabilityPolicy
from app.modules.products.application.commands import (
    CreateProductCommand,
    ProductFieldsCommand,
    ProductImportRowCommand,
    UpdateProductCommand,
)
from app.modules.products.application.dto import ProductDTO
from app.modules.products.domain.entities import PRODUCT_STATUSES, PRODUCT_TYPES, Product
from app.modules.products.domain.repository import (
    ProductAccessFacts,
    ProductRepository,
    ProductSearchCriteria,
)
from app.shared.application.unit_of_work import UnitOfWork
from app.shared.domain.current_user import CurrentUser


class ProductUseCases:
    def __init__(
        self,
        repository: ProductRepository,
        capability_policy: ProductCapabilityPolicy | None = None,
        audit_writer: AuditWriter | None = None,
        audit_diff: AuditDiffService | None = None,
        unit_of_work: UnitOfWork | None = None,
    ) -> None:
        self.repository = repository
        self.policy = capability_policy or ProductCapabilityPolicy()
        self.audit_writer = audit_writer
        self.audit_diff = audit_diff or AuditDiffService()
        self.unit_of_work = unit_of_work

    @staticmethod
    def _require(actor: CurrentUser, permission: str) -> None:
        if not actor.can(permission):
            raise PermissionDenied(f"Missing permission: {permission}")

    async def search(
        self, criteria: ProductSearchCriteria, actor: CurrentUser
    ) -> tuple[list[ProductDTO], int]:
        self._require(actor, "products.read")
        page = await self.repository.search(
            criteria,
            actor_id=actor.user_id,
            tenant_id=actor.tenant_id,
            scope=actor.scope_for("products.read"),
        )
        return [
            ProductDTO.from_domain(
                item.product, self.policy.evaluate(item.product, item.access, actor)
            )
            for item in page.items
        ], page.total

    async def get(self, product_id: UUID, actor: CurrentUser) -> ProductDTO:
        self._require(actor, "products.detail.read")
        product = await self.repository.get_by_id(
            product_id,
            actor_id=actor.user_id,
            tenant_id=actor.tenant_id,
            scope=actor.scope_for("products.detail.read"),
        )
        if product is None:
            raise EntityNotFound("Product not found")
        access = await self.repository.get_access_facts(
            product_id, actor_id=actor.user_id, tenant_id=actor.tenant_id
        )
        return ProductDTO.from_domain(product, self.policy.evaluate(product, access, actor))

    async def _validate(self, fields: ProductFieldsCommand, actor: CurrentUser) -> UUID:
        if fields.product_type not in PRODUCT_TYPES:
            raise ValidationFailure("Invalid Product Type")
        if fields.status not in PRODUCT_STATUSES:
            raise ValidationFailure("Invalid Product Status")
        owner = fields.owner_user_id or actor.user_id
        if (
            fields.owner_user_id
            and owner != actor.user_id
            and not actor.can("products.assign_owner")
        ):
            raise PermissionDenied("Cannot assign Product owner")
        if owner not in await self.repository.find_valid_owner_ids(actor.tenant_id, {owner}):
            raise ValidationFailure("Owner is not an active user in this tenant")
        return owner

    async def create(
        self, command: CreateProductCommand, actor: CurrentUser, context: AuditContext | None = None
    ) -> ProductDTO:
        self._require(actor, "products.create")
        if not Product.valid_code(command.product_code):
            raise ValidationFailure("Invalid Product Code")
        owner = await self._validate(command, actor)
        now = datetime.now(UTC)
        data = asdict(command)
        data.pop("product_code")
        data["owner_user_id"] = owner
        product = Product(
            id=uuid4(),
            tenant_id=actor.tenant_id,
            product_code=Product.normalize_code(command.product_code),
            owner_display_name=actor.display_name if owner == actor.user_id else None,
            created_by=actor.user_id,
            updated_by=actor.user_id,
            created_at=now,
            updated_at=now,
            deleted_at=None,
            row_version=1,
            **data,
        )
        created = await self.repository.create(product)
        await self._audit(context, AuditAction.CREATE, None, created)
        await self._commit()
        return ProductDTO.from_domain(
            created,
            self.policy.evaluate(
                created, ProductAccessFacts(owner == actor.user_id, False, False), actor
            ),
        )

    async def update(
        self, command: UpdateProductCommand, actor: CurrentUser, context: AuditContext | None = None
    ) -> ProductDTO:
        self._require(actor, "products.update")
        before = await self.repository.get_by_id(
            command.product_id,
            actor_id=actor.user_id,
            tenant_id=actor.tenant_id,
            scope=actor.scope_for("products.update"),
        )
        if before is None:
            raise EntityNotFound("Product not found")
        owner = await self._validate(command, actor)
        data = asdict(command)
        data.pop("product_id")
        data.pop("expected_version")
        data["owner_user_id"] = owner
        updated = await self.repository.update(
            command.product_id,
            command.expected_version,
            data,
            actor_id=actor.user_id,
            tenant_id=actor.tenant_id,
            scope=actor.scope_for("products.update"),
        )
        if updated is None:
            raise EntityNotFound("Product not found")
        await self._audit(context, AuditAction.UPDATE, before, updated)
        await self._commit()
        access = await self.repository.get_access_facts(
            updated.id, actor_id=actor.user_id, tenant_id=actor.tenant_id
        )
        return ProductDTO.from_domain(updated, self.policy.evaluate(updated, access, actor))

    async def _lifecycle(
        self,
        product_id: UUID,
        version: int,
        actor: CurrentUser,
        context: AuditContext | None,
        restore: bool,
    ) -> None:
        permission = "products.restore" if restore else "products.delete"
        self._require(actor, permission)
        before = await self.repository.get_by_id(
            product_id,
            actor_id=actor.user_id,
            tenant_id=actor.tenant_id,
            scope=actor.scope_for(permission),
            include_deleted=True,
        )
        if before is None:
            raise EntityNotFound("Product not found")
        method = self.repository.restore if restore else self.repository.soft_delete
        after = await method(
            product_id,
            version,
            actor_id=actor.user_id,
            tenant_id=actor.tenant_id,
            scope=actor.scope_for(permission),
        )
        if after is None:
            raise EntityNotFound("Product not found")
        await self._audit(
            context, AuditAction.RESTORE if restore else AuditAction.DELETE, before, after
        )
        await self._commit()

    async def soft_delete(
        self,
        product_id: UUID,
        version: int,
        actor: CurrentUser,
        context: AuditContext | None = None,
    ) -> None:
        await self._lifecycle(product_id, version, actor, context, False)

    async def restore(
        self,
        product_id: UUID,
        version: int,
        actor: CurrentUser,
        context: AuditContext | None = None,
    ) -> None:
        await self._lifecycle(product_id, version, actor, context, True)

    async def import_products(
        self,
        rows: list[ProductImportRowCommand],
        actor: CurrentUser,
        context: AuditContext | None = None,
    ) -> int:
        self._require(actor, "products.create")
        if not rows or len(rows) > 500:
            raise ImportValidationFailure(
                "Product import validation failed",
                details={
                    "errors": [
                        {
                            "row_number": 0,
                            "field": "rows",
                            "code": "INVALID_SIZE",
                            "message": "1 to 500 rows required",
                        }
                    ]
                },
            )
        seen: set[str] = set()
        for row in rows:
            code = Product.normalize_code(row.product_code)
            if code in seen:
                raise ImportValidationFailure(
                    "Product import validation failed",
                    details={
                        "errors": [
                            {
                                "row_number": row.row_number,
                                "field": "product_code",
                                "code": "DUPLICATE_IN_FILE",
                                "message": "Duplicate Product Code",
                            }
                        ]
                    },
                )
            seen.add(code)
            values = asdict(row)
            values.pop("row_number")
            await self.create(CreateProductCommand(**values), actor, context)
        return len(rows)

    async def _audit(
        self,
        context: AuditContext | None,
        action: AuditAction,
        before: Product | None,
        after: Product | None,
    ) -> None:
        if not context or not self.audit_writer:
            return
        snapshot = self.audit_diff.product_snapshot
        product = after or before
        assert product is not None
        await self.audit_writer.write_event(
            context=context,
            action=action,
            module="PRODUCT",
            entity_type="PRODUCT",
            entity_id=product.id,
            entity_code=product.product_code,
            entity_display_name=product.product_name,
            changes=self.audit_diff.diff(
                snapshot(before) if before else None, snapshot(after) if after else None
            ),
        )

    async def _commit(self) -> None:
        if self.unit_of_work:
            await self.unit_of_work.commit()
