from dataclasses import dataclass

from app.modules.suppliers.domain.entities import Supplier
from app.modules.suppliers.domain.repository import SupplierAccessFacts
from app.shared.domain.current_user import CurrentUser, PermissionScope


@dataclass(frozen=True, slots=True)
class SupplierCapabilities:
    update: bool
    delete: bool
    restore: bool
    assign_owner: bool


class SupplierCapabilityPolicy:
    @staticmethod
    def _scope_allows(scope: PermissionScope, access: SupplierAccessFacts) -> bool:
        return (
            scope == PermissionScope.ALL
            or (scope == PermissionScope.OWN and access.is_owner)
            or (scope == PermissionScope.ASSIGNED and access.is_assigned)
            or (scope == PermissionScope.TEAM and (access.is_owner or access.is_team_assigned))
        )

    def _allows(self, actor: CurrentUser, code: str, access: SupplierAccessFacts) -> bool:
        return actor.can(code) and self._scope_allows(actor.scope_for(code), access)

    def evaluate(
        self, supplier: Supplier, access: SupplierAccessFacts, actor: CurrentUser
    ) -> SupplierCapabilities:
        if supplier.deleted_at is not None:
            return SupplierCapabilities(
                False, False, self._allows(actor, "suppliers.restore", access), False
            )
        update = self._allows(actor, "suppliers.update", access)
        return SupplierCapabilities(
            update,
            self._allows(actor, "suppliers.delete", access),
            False,
            update and actor.can("suppliers.assign_owner"),
        )
