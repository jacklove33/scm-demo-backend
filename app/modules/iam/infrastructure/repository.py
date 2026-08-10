from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.iam.domain.repository import PermissionGrant, UserProfile
from app.shared.domain.current_user import PermissionEffect, PermissionScope


class SqlAlchemyIamRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_profile(self, user_id: UUID) -> UserProfile | None:
        row = (
            (
                await self.session.execute(
                    text(
                        """
                    SELECT id, tenant_id, email, display_name, is_active
                    FROM profiles
                    WHERE id = :user_id
                    """
                    ),
                    {"user_id": user_id},
                )
            )
            .mappings()
            .one_or_none()
        )

        if row is None:
            return None

        return UserProfile(
            id=row["id"],
            tenant_id=row["tenant_id"],
            email=row["email"],
            display_name=row["display_name"],
            is_active=row["is_active"],
        )

    async def get_permission_grants(self, user_id: UUID) -> list[PermissionGrant]:
        # One SQL statement resolves all raw grants for this request.
        # The merge rule remains in the Application layer.
        rows = (
            (
                await self.session.execute(
                    text(
                        """
                    WITH user_ctx AS (
                        SELECT id, tenant_id, primary_role_id
                        FROM profiles
                        WHERE id = :user_id
                    ),
                    role_grants AS (
                        SELECT
                            p.code AS permission_code,
                            'ROLE'::text AS source_type,
                            r.code AS source_name,
                            po.code AS policy_code,
                            pp.effect,
                            pp.scope
                        FROM user_ctx u
                        JOIN roles r ON r.id = u.primary_role_id AND r.deleted_at IS NULL
                        JOIN role_policies rp ON rp.role_id = r.id
                        JOIN policies po ON po.id = rp.policy_id AND po.deleted_at IS NULL
                        JOIN policy_permissions pp ON pp.policy_id = po.id
                        JOIN permissions p ON p.id = pp.permission_id
                    ),
                    group_grants AS (
                        SELECT
                            p.code AS permission_code,
                            'GROUP'::text AS source_type,
                            g.code AS source_name,
                            po.code AS policy_code,
                            pp.effect,
                            pp.scope
                        FROM user_ctx u
                        JOIN user_groups ug ON ug.user_id = u.id
                        JOIN groups g ON g.id = ug.group_id
                            AND g.tenant_id = u.tenant_id
                            AND g.deleted_at IS NULL
                        JOIN group_policies gp ON gp.group_id = g.id
                        JOIN policies po ON po.id = gp.policy_id AND po.deleted_at IS NULL
                        JOIN policy_permissions pp ON pp.policy_id = po.id
                        JOIN permissions p ON p.id = pp.permission_id
                    ),
                    direct_grants AS (
                        SELECT
                            p.code AS permission_code,
                            'DIRECT'::text AS source_type,
                            u.id::text AS source_name,
                            po.code AS policy_code,
                            pp.effect,
                            pp.scope
                        FROM user_ctx u
                        JOIN user_policies up ON up.user_id = u.id
                        JOIN policies po ON po.id = up.policy_id AND po.deleted_at IS NULL
                        JOIN policy_permissions pp ON pp.policy_id = po.id
                        JOIN permissions p ON p.id = pp.permission_id
                    )
                    SELECT * FROM role_grants
                    UNION ALL
                    SELECT * FROM group_grants
                    UNION ALL
                    SELECT * FROM direct_grants
                    ORDER BY permission_code, source_type, policy_code
                    """
                    ),
                    {"user_id": user_id},
                )
            )
            .mappings()
            .all()
        )

        return [
            PermissionGrant(
                permission_code=row["permission_code"],
                source_type=row["source_type"],
                source_name=row["source_name"],
                policy_code=row["policy_code"],
                effect=PermissionEffect(row["effect"]),
                scope=PermissionScope(row["scope"]) if row["scope"] else None,
            )
            for row in rows
        ]
