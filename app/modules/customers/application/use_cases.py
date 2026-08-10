from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.core.exceptions import EntityNotFound, PermissionDenied
from app.modules.customers.application.capabilities import CustomerCapabilityPolicy
from app.modules.customers.application.commands import CreateCustomerCommand, UpdateCustomerCommand
from app.modules.customers.application.dto import CustomerDTO, CustomerSearchDTO
from app.modules.customers.domain.entities import Customer
from app.modules.customers.domain.repository import CustomerRepository, CustomerSearchCriteria
from app.shared.domain.current_user import CurrentUser


class CustomerUseCases:
    """No role checks here. Authorization is permission + scope only."""

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
            CustomerSearchDTO.from_domain_with_capabilities(
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

        return CustomerDTO.from_domain(customer)

    async def create(self, command: CreateCustomerCommand, actor: CurrentUser) -> CustomerDTO:
        self._require(actor, "customers.create")

        owner_user_id = command.owner_user_id
        if owner_user_id is not None and not actor.can("customers.assign_owner"):
            # A user without owner-assignment permission may only create for self.
            if owner_user_id != actor.user_id:
                raise PermissionDenied("Cannot assign customer owner")

        if owner_user_id is None:
            owner_user_id = actor.user_id

        now = datetime.now(UTC)
        customer = Customer(
            id=uuid4(),
            tenant_id=actor.tenant_id,
            customer_code=Customer.normalize_code(command.customer_code),
            customer_name=Customer.normalize_name(command.customer_name),
            owner_user_id=owner_user_id,
            status=command.status,
            deleted_at=None,
            deleted_by=None,
            row_version=1,
            created_at=now,
            updated_at=now,
        )

        return CustomerDTO.from_domain(await self.repository.create(customer))

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
                "customer_code": Customer.normalize_code(command.customer_code),
                "customer_name": Customer.normalize_name(command.customer_name),
                "owner_user_id": owner_user_id,
                "status": command.status,
            },
            actor_id=actor.user_id,
            tenant_id=actor.tenant_id,
            scope=scope,
        )
        if updated is None:
            raise EntityNotFound("Customer not found or outside allowed scope")

        return CustomerDTO.from_domain(updated)

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
