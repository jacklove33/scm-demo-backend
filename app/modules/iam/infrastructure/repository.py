from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.iam.domain.repository import (
    GroupSummary,
    PermissionGrant,
    PermissionSummary,
    PolicyRule,
    PolicySummary,
    RoleSummary,
    UserPage,
    UserProfile,
    UserSearchCriteria,
    UserSummary,
)
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

    async def search_users(self, tenant_id: UUID, criteria: UserSearchCriteria) -> UserPage:
        conditions = ["p.tenant_id = :tenant_id"]
        parameters: dict[str, object] = {"tenant_id": tenant_id}
        if criteria.search:
            conditions.append("(p.email ILIKE :search OR p.display_name ILIKE :search)")
            parameters["search"] = f"%{criteria.search.strip()}%"
        if criteria.status:
            conditions.append("p.is_active = :is_active")
            parameters["is_active"] = criteria.status == "ACTIVE"
        if criteria.role_id:
            conditions.append("p.primary_role_id = :role_id")
            parameters["role_id"] = criteria.role_id
        if criteria.group_id:
            conditions.append(
                "EXISTS (SELECT 1 FROM user_groups f "
                "JOIN groups fg ON fg.id=f.group_id AND fg.tenant_id=p.tenant_id "
                "WHERE f.user_id=p.id AND f.group_id=:group_id)"
            )
            parameters["group_id"] = criteria.group_id
        where = " AND ".join(conditions)
        total = int(
            (
                await self.session.scalar(
                    text(f"SELECT count(*) FROM profiles p WHERE {where}"), parameters
                )
            )
            or 0
        )
        parameters.update(
            {"limit": criteria.page_size, "offset": (criteria.page - 1) * criteria.page_size}
        )
        rows = (
            (
                await self.session.execute(
                    text(
                        f"""
                        SELECT p.id, p.email, p.display_name,
                               CASE WHEN p.is_active THEN 'ACTIVE' ELSE 'INACTIVE' END status,
                               p.primary_role_id, r.name primary_role_name,
                               COALESCE(array_agg(DISTINCT g.id) FILTER (WHERE g.id IS NOT NULL),
                                        ARRAY[]::uuid[]) group_ids,
                               COALESCE(array_agg(DISTINCT g.name)
                                        FILTER (WHERE g.name IS NOT NULL),
                                        ARRAY[]::varchar[]) group_names,
                               COALESCE(array_agg(DISTINCT po.id) FILTER (WHERE po.id IS NOT NULL),
                                        ARRAY[]::uuid[]) direct_policy_ids,
                               COALESCE(array_agg(DISTINCT po.name)
                                        FILTER (WHERE po.name IS NOT NULL),
                                        ARRAY[]::varchar[]) direct_policy_names,
                               p.row_version, p.updated_at
                        FROM profiles p
                        LEFT JOIN roles r ON r.id=p.primary_role_id
                        LEFT JOIN user_groups ug ON ug.user_id=p.id
                        LEFT JOIN groups g ON g.id=ug.group_id AND g.tenant_id=p.tenant_id
                        LEFT JOIN user_policies up ON up.user_id=p.id
                        LEFT JOIN policies po ON po.id=up.policy_id
                            AND (po.tenant_id=p.tenant_id OR po.tenant_id IS NULL)
                        WHERE {where}
                        GROUP BY p.id, r.name
                        ORDER BY p.display_name, p.email, p.id
                        LIMIT :limit OFFSET :offset
                        """
                    ),
                    parameters,
                )
            )
            .mappings()
            .all()
        )
        return UserPage(
            [
                UserSummary(
                    id=row["id"],
                    email=row["email"],
                    display_name=row["display_name"],
                    status=row["status"],
                    primary_role_id=row["primary_role_id"],
                    primary_role_name=row["primary_role_name"],
                    group_ids=list(row["group_ids"]),
                    group_names=list(row["group_names"]),
                    direct_policy_ids=list(row["direct_policy_ids"]),
                    direct_policy_names=list(row["direct_policy_names"]),
                    row_version=row["row_version"],
                    updated_at=row["updated_at"],
                )
                for row in rows
            ],
            total,
            criteria.page,
            criteria.page_size,
        )

    async def list_groups(self, tenant_id: UUID) -> list[GroupSummary]:
        rows = await self._management_rows(
            """
            SELECT g.id, g.name, COALESCE(g.description, '') description,
                   count(DISTINCT member.id) member_count,
                   COALESCE(array_agg(DISTINCT po.id)
                            FILTER (WHERE po.id IS NOT NULL), ARRAY[]::uuid[]) policy_ids,
                   g.deleted_at, g.created_at, g.updated_at
            FROM groups g
            LEFT JOIN user_groups ug ON ug.group_id=g.id
            LEFT JOIN profiles member ON member.id=ug.user_id AND member.tenant_id=g.tenant_id
            LEFT JOIN group_policies gp ON gp.group_id=g.id
            LEFT JOIN policies po ON po.id=gp.policy_id
                 AND (po.tenant_id=g.tenant_id OR po.tenant_id IS NULL)
            WHERE g.tenant_id=:tenant_id
            GROUP BY g.id
            ORDER BY g.name, g.id
            """,
            tenant_id,
        )
        return [GroupSummary(**dict(row)) for row in rows]

    async def list_roles(self, tenant_id: UUID) -> list[RoleSummary]:
        rows = await self._management_rows(
            """
            SELECT r.id, r.name, COALESCE(r.description, '') description, r.is_system,
                   COALESCE(array_agg(DISTINCT rp.policy_id)
                            FILTER (WHERE po.id IS NOT NULL), ARRAY[]::uuid[]) policy_ids,
                   count(DISTINCT p.id) user_count,
                   r.deleted_at, r.created_at, r.updated_at
            FROM roles r
            LEFT JOIN role_policies rp ON rp.role_id=r.id
            LEFT JOIN policies po ON po.id=rp.policy_id
                 AND (po.tenant_id=:tenant_id OR po.tenant_id IS NULL)
            LEFT JOIN profiles p ON p.primary_role_id=r.id AND p.tenant_id=:tenant_id
            WHERE r.is_system OR p.id IS NOT NULL
            GROUP BY r.id
            ORDER BY r.name, r.id
            """,
            tenant_id,
        )
        return [RoleSummary(**dict(row)) for row in rows]

    async def list_policies(self, tenant_id: UUID) -> list[PolicySummary]:
        policies = await self._management_rows(
            """
            SELECT id, name, COALESCE(description, '') description, is_system,
                   deleted_at, created_at, updated_at
            FROM policies
            WHERE tenant_id=:tenant_id OR tenant_id IS NULL
            ORDER BY name, id
            """,
            tenant_id,
        )
        rules = await self._management_rows(
            """
            SELECT pp.policy_id, perm.code permission_code, pp.effect,
                   COALESCE(pp.scope, 'NONE') scope
            FROM policy_permissions pp
            JOIN permissions perm ON perm.id=pp.permission_id
            JOIN policies po ON po.id=pp.policy_id
            WHERE po.tenant_id=:tenant_id OR po.tenant_id IS NULL
            ORDER BY pp.policy_id, perm.code
            """,
            tenant_id,
        )
        by_policy: dict[UUID, list[PolicyRule]] = {}
        for row in rules:
            by_policy.setdefault(row["policy_id"], []).append(
                PolicyRule(row["permission_code"], row["effect"], row["scope"])
            )
        return [PolicySummary(**dict(row), rules=by_policy.get(row["id"], [])) for row in policies]

    async def list_permissions(self) -> list[PermissionSummary]:
        rows = (
            (
                await self.session.execute(
                    text(
                        "SELECT code, resource, action, COALESCE(description, '') description "
                        "FROM permissions ORDER BY resource, action, code"
                    )
                )
            )
            .mappings()
            .all()
        )
        return [PermissionSummary(**dict(row)) for row in rows]

    async def _management_rows(self, statement: str, tenant_id: UUID) -> list[RowMapping]:
        return list(
            (await self.session.execute(text(statement), {"tenant_id": tenant_id})).mappings()
        )
