from dataclasses import dataclass

from app.modules.customers.domain.entities import Customer
from app.modules.customers.domain.repository import CustomerAccessFacts
from app.shared.domain.current_user import CurrentUser, PermissionScope


@dataclass(frozen=True, slots=True)
class CustomerCapabilities:
    update: bool
    delete: bool
    restore: bool
    assign_owner: bool


class CustomerCapabilityPolicy:
    """Evaluates effective action scopes against facts loaded with a Customer row."""

    @staticmethod
    def _scope_allows(scope: PermissionScope, access: CustomerAccessFacts) -> bool:
        if scope == PermissionScope.ALL:
            return True
        if scope == PermissionScope.OWN:
            return access.is_owner
        if scope == PermissionScope.ASSIGNED:
            return access.is_assigned
        if scope == PermissionScope.TEAM:
            return access.is_owner or access.is_team_assigned
        return False

    def _allows(
        self,
        actor: CurrentUser,
        permission_code: str,
        access: CustomerAccessFacts,
    ) -> bool:
        return actor.can(permission_code) and self._scope_allows(
            actor.scope_for(permission_code), access
        )

    def evaluate(
        self,
        customer: Customer,
        access: CustomerAccessFacts,
        actor: CurrentUser,
    ) -> CustomerCapabilities:
        if customer.deleted_at is not None:
            restore = self._allows(actor, "customers.restore", access)
            return CustomerCapabilities(
                update=False,
                delete=False,
                restore=restore,
                assign_owner=False,
            )

        update = self._allows(actor, "customers.update", access)
        delete = self._allows(actor, "customers.delete", access)
        return CustomerCapabilities(
            update=update,
            delete=delete,
            restore=False,
            # The current update endpoint treats assign_owner as an additional,
            # unscoped permission gate after row-level update authorization.
            assign_owner=update and actor.can("customers.assign_owner"),
        )
