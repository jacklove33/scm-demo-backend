from dataclasses import dataclass

from app.modules.customer_pos.domain.entities import CustomerPurchaseOrder
from app.modules.customer_pos.domain.enums import (
    CustomerPoStatus,
    CustomerPoStatusTransitions,
)
from app.shared.domain.current_user import CurrentUser, PermissionScope


@dataclass(frozen=True, slots=True)
class CustomerPoCapabilities:
    update: bool
    delete: bool
    restore: bool
    change_status: bool
    allowed_status_transitions: list[CustomerPoStatus]
    assign_owner: bool


def scope_allows(
    actor: CurrentUser,
    code: str,
    po: CustomerPurchaseOrder,
) -> bool:
    if not actor.can(code):
        return False

    scope = actor.scope_for(code)

    if scope == PermissionScope.ALL:
        return True

    return (
        scope in (PermissionScope.OWN, PermissionScope.TEAM) and po.owner_user_id == actor.user_id
    )


def capabilities(
    po: CustomerPurchaseOrder,
    actor: CurrentUser,
) -> CustomerPoCapabilities:

    if po.deleted_at:
        return CustomerPoCapabilities(
            update=False,
            delete=False,
            restore=scope_allows(
                actor,
                "customer_pos.restore",
                po,
            ),
            change_status=False,
            allowed_status_transitions=[],
            assign_owner=False,
        )

    update = scope_allows(
        actor,
        "customer_pos.update",
        po,
    )

    can_change_status = scope_allows(
        actor,
        "customer_pos.change_status",
        po,
    )

    transitions = list(CustomerPoStatusTransitions.allowed(po.status))

    return CustomerPoCapabilities(
        update=update,
        delete=scope_allows(
            actor,
            "customer_pos.delete",
            po,
        ),
        restore=False,
        change_status=(can_change_status and len(transitions) > 0),
        allowed_status_transitions=(transitions if can_change_status else []),
        assign_owner=(update and actor.can("customer_pos.assign_owner")),
    )
