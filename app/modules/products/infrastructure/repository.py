from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, exists, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.exceptions import EntityConflict, VersionConflict
from app.modules.iam.infrastructure.models import ProfileModel, UserGroupModel
from app.modules.products.domain.entities import Product
from app.modules.products.domain.repository import (
    ProductAccessFacts,
    ProductPage,
    ProductSearchCriteria,
    ProductSearchItem,
)
from app.modules.products.infrastructure.models import (
    ProductGroupAssignmentModel,
    ProductModel,
    ProductUserAssignmentModel,
)
from app.shared.domain.current_user import PermissionScope


class SqlAlchemyProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _domain(row: ProductModel, owner_name: str | None) -> Product:
        values = {
            column.name: getattr(row, column.name) for column in ProductModel.__table__.columns
        }
        return Product(**values, owner_display_name=owner_name)

    @staticmethod
    def _assigned(actor_id: UUID) -> ColumnElement[bool]:
        return exists(
            select(ProductUserAssignmentModel.product_id).where(
                ProductUserAssignmentModel.product_id == ProductModel.id,
                ProductUserAssignmentModel.tenant_id == ProductModel.tenant_id,
                ProductUserAssignmentModel.user_id == actor_id,
            )
        )

    @staticmethod
    def _team(actor_id: UUID) -> ColumnElement[bool]:
        return exists(
            select(ProductGroupAssignmentModel.product_id)
            .join(UserGroupModel, UserGroupModel.group_id == ProductGroupAssignmentModel.group_id)
            .where(
                ProductGroupAssignmentModel.product_id == ProductModel.id,
                ProductGroupAssignmentModel.tenant_id == ProductModel.tenant_id,
                UserGroupModel.user_id == actor_id,
            )
        )

    def _base(self) -> Select[Any]:
        return select(ProductModel, ProfileModel.display_name).outerjoin(
            ProfileModel, ProfileModel.id == ProductModel.owner_user_id
        )

    def _scope(
        self, stmt: Select[Any], actor_id: UUID, tenant_id: UUID, scope: PermissionScope
    ) -> Select[Any]:
        stmt = stmt.where(ProductModel.tenant_id == tenant_id)
        if scope == PermissionScope.ALL:
            return stmt
        if scope == PermissionScope.OWN:
            return stmt.where(ProductModel.owner_user_id == actor_id)
        if scope == PermissionScope.ASSIGNED:
            return stmt.where(self._assigned(actor_id))
        if scope == PermissionScope.TEAM:
            return stmt.where(or_(ProductModel.owner_user_id == actor_id, self._team(actor_id)))
        return stmt.where(ProductModel.id.is_(None))

    async def find_valid_owner_ids(self, tenant_id: UUID, ids: set[UUID]) -> set[UUID]:
        if not ids:
            return set()
        return set(
            await self.session.scalars(
                select(ProfileModel.id).where(
                    ProfileModel.tenant_id == tenant_id,
                    ProfileModel.id.in_(ids),
                    ProfileModel.is_active.is_(True),
                )
            )
        )

    async def search(
        self,
        criteria: ProductSearchCriteria,
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
    ) -> ProductPage:
        own, assigned, team = (
            ProductModel.owner_user_id == actor_id,
            self._assigned(actor_id),
            self._team(actor_id),
        )
        stmt = self._scope(
            self._base().add_columns(
                own.label("own"), assigned.label("assigned"), team.label("team")
            ),
            actor_id,
            tenant_id,
            scope,
        )
        if not criteria.show_deleted:
            stmt = stmt.where(ProductModel.deleted_at.is_(None))
        if criteria.search:
            term = criteria.search.strip().replace("%", "\\%").replace("_", "\\_")
            stmt = stmt.where(
                or_(
                    ProductModel.product_code.ilike(f"%{term}%", escape="\\"),
                    ProductModel.product_name.ilike(f"%{term}%", escape="\\"),
                )
            )
        if criteria.product_code:
            stmt = stmt.where(ProductModel.product_code.ilike(f"%{criteria.product_code}%"))
        if criteria.product_name:
            stmt = stmt.where(ProductModel.product_name.ilike(f"%{criteria.product_name}%"))
        if criteria.product_type:
            stmt = stmt.where(ProductModel.product_type == criteria.product_type)
        if criteria.status:
            stmt = stmt.where(ProductModel.status == criteria.status)
        if criteria.category:
            stmt = stmt.where(ProductModel.category.ilike(f"%{criteria.category}%"))
        if criteria.owner_user_id:
            stmt = stmt.where(ProductModel.owner_user_id == criteria.owner_user_id)
        for value, column, ge in (
            (criteria.created_at_from, ProductModel.created_at, True),
            (criteria.created_at_to_exclusive, ProductModel.created_at, False),
            (criteria.updated_at_from, ProductModel.updated_at, True),
            (criteria.updated_at_to_exclusive, ProductModel.updated_at, False),
        ):
            if value:
                stmt = stmt.where(column >= value if ge else column < value)
        total = int(
            await self.session.scalar(
                select(func.count()).select_from(stmt.order_by(None).subquery())
            )
            or 0
        )
        columns = {
            "product_code": ProductModel.product_code,
            "product_name": ProductModel.product_name,
            "product_type": ProductModel.product_type,
            "status": ProductModel.status,
            "updated_at": ProductModel.updated_at,
        }
        col = columns.get(criteria.sort_field, ProductModel.updated_at)
        rows = (
            await self.session.execute(
                stmt.order_by(col.asc() if criteria.sort_direction == "asc" else col.desc())
                .offset((criteria.page - 1) * criteria.page_size)
                .limit(criteria.page_size)
            )
        ).all()
        return ProductPage(
            [
                ProductSearchItem(
                    self._domain(row, name),
                    ProductAccessFacts(bool(own_), bool(assigned_), bool(team_)),
                )
                for row, name, own_, assigned_, team_ in rows
            ],
            total,
            criteria.page,
            criteria.page_size,
        )

    async def get_by_id(
        self,
        product_id: UUID,
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
        include_deleted: bool = False,
    ) -> Product | None:
        stmt = self._scope(
            self._base().where(ProductModel.id == product_id), actor_id, tenant_id, scope
        )
        if not include_deleted:
            stmt = stmt.where(ProductModel.deleted_at.is_(None))
        row = (await self.session.execute(stmt)).first()
        return self._domain(row[0], row[1]) if row else None

    async def get_access_facts(
        self, product_id: UUID, *, actor_id: UUID, tenant_id: UUID
    ) -> ProductAccessFacts:
        row = (
            await self.session.execute(
                select(
                    ProductModel.owner_user_id == actor_id,
                    self._assigned(actor_id),
                    self._team(actor_id),
                ).where(ProductModel.id == product_id, ProductModel.tenant_id == tenant_id)
            )
        ).first()
        return (
            ProductAccessFacts(*(bool(v) for v in row))
            if row
            else ProductAccessFacts(False, False, False)
        )

    async def create(self, product: Product) -> Product:
        values = {
            column.name: getattr(product, column.name) for column in ProductModel.__table__.columns
        }
        self.session.add(ProductModel(**values))
        try:
            await self.session.flush()
        except IntegrityError as exc:
            raise EntityConflict("Product Code already exists in this tenant") from exc
        created = await self.get_by_id(
            product.id,
            actor_id=product.owner_user_id or product.created_by,
            tenant_id=product.tenant_id,
            scope=PermissionScope.ALL,
        )
        assert created is not None
        return created

    async def update(
        self,
        product_id: UUID,
        expected_version: int,
        data: dict[str, object],
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
    ) -> Product | None:
        if (
            await self.get_by_id(product_id, actor_id=actor_id, tenant_id=tenant_id, scope=scope)
            is None
        ):
            return None
        result = (
            await self.session.execute(
                update(ProductModel)
                .where(
                    ProductModel.id == product_id,
                    ProductModel.tenant_id == tenant_id,
                    ProductModel.row_version == expected_version,
                )
                .values(
                    **data,
                    updated_by=actor_id,
                    updated_at=datetime.now(UTC),
                    row_version=ProductModel.row_version + 1,
                )
                .returning(ProductModel.id)
            )
        ).scalar_one_or_none()
        if result is None:
            raise VersionConflict("Product was modified by another user")
        await self.session.flush()
        return await self.get_by_id(product_id, actor_id=actor_id, tenant_id=tenant_id, scope=scope)

    async def _deleted(
        self,
        product_id: UUID,
        expected_version: int,
        *,
        actor_id: UUID,
        tenant_id: UUID,
        scope: PermissionScope,
        restore: bool,
    ) -> Product | None:
        visible = await self.get_by_id(
            product_id, actor_id=actor_id, tenant_id=tenant_id, scope=scope, include_deleted=True
        )
        if visible is None:
            return None
        result = (
            await self.session.execute(
                update(ProductModel)
                .where(
                    ProductModel.id == product_id,
                    ProductModel.tenant_id == tenant_id,
                    ProductModel.row_version == expected_version,
                )
                .values(
                    deleted_at=None if restore else datetime.now(UTC),
                    updated_by=actor_id,
                    updated_at=datetime.now(UTC),
                    row_version=ProductModel.row_version + 1,
                )
                .returning(ProductModel.id)
            )
        ).scalar_one_or_none()
        if result is None:
            raise VersionConflict("Product was modified by another user")
        await self.session.flush()
        return await self.get_by_id(
            product_id, actor_id=actor_id, tenant_id=tenant_id, scope=scope, include_deleted=True
        )

    async def soft_delete(
        self, product_id: UUID, expected_version: int, **kwargs: Any
    ) -> Product | None:
        return await self._deleted(product_id, expected_version, restore=False, **kwargs)

    async def restore(
        self, product_id: UUID, expected_version: int, **kwargs: Any
    ) -> Product | None:
        return await self._deleted(product_id, expected_version, restore=True, **kwargs)
