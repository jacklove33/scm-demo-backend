from dataclasses import dataclass

from app.modules.products.domain.entities import Product
from app.modules.products.domain.repository import ProductAccessFacts
from app.shared.domain.current_user import CurrentUser, PermissionScope


@dataclass(frozen=True, slots=True)
class ProductCapabilities:
    update: bool
    delete: bool
    restore: bool
    assign_owner: bool


class ProductCapabilityPolicy:
    @staticmethod
    def _allows(actor: CurrentUser, code: str, access: ProductAccessFacts) -> bool:
        scope = actor.scope_for(code)
        scoped = (
            scope == PermissionScope.ALL
            or (scope == PermissionScope.OWN and access.is_owner)
            or (scope == PermissionScope.ASSIGNED and access.is_assigned)
            or (scope == PermissionScope.TEAM and (access.is_owner or access.is_team_assigned))
        )
        return actor.can(code) and scoped

    def evaluate(
        self, product: Product, access: ProductAccessFacts, actor: CurrentUser
    ) -> ProductCapabilities:
        if product.deleted_at:
            return ProductCapabilities(
                False, False, self._allows(actor, "products.restore", access), False
            )
        update = self._allows(actor, "products.update", access)
        return ProductCapabilities(
            update,
            self._allows(actor, "products.delete", access),
            False,
            update and actor.can("products.assign_owner"),
        )
