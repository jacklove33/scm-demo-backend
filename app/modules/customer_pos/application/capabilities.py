from dataclasses import dataclass

from app.modules.customer_pos.domain.entities import CustomerPurchaseOrder
from app.shared.domain.current_user import CurrentUser, PermissionScope


@dataclass(frozen=True, slots=True)
class CustomerPoCapabilities:
    update: bool
    delete: bool
    restore: bool
    change_status: bool
    assign_owner: bool


def scope_allows(actor: CurrentUser, code: str, po: CustomerPurchaseOrder) -> bool:
    if not actor.can(code):
        return False
    scope = actor.scope_for(code)
    if scope == PermissionScope.ALL:
        return True
    return (
        scope in (PermissionScope.OWN, PermissionScope.TEAM) and po.owner_user_id == actor.user_id
    )


def capabilities(po: CustomerPurchaseOrder, actor: CurrentUser) -> CustomerPoCapabilities:
    if po.deleted_at:
        return CustomerPoCapabilities(
            False, False, scope_allows(actor, "customer_pos.restore", po), False, False
        )
    update = scope_allows(actor, "customer_pos.update", po)
    return CustomerPoCapabilities(
        update,
        scope_allows(actor, "customer_pos.delete", po),
        False,
        scope_allows(actor, "customer_pos.change_status", po),
        update and actor.can("customer_pos.assign_owner"),
    )
