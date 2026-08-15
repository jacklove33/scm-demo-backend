from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from app.core.exceptions import EntityNotFound, PermissionDenied, ValidationFailure
from app.modules.attachments.application.commands import UploadAttachmentCommand
from app.modules.attachments.application.use_cases import AttachmentUseCases, object_key
from app.modules.attachments.domain.entities import Attachment, AttachmentEntityType
from app.modules.attachments.domain.repository import AttachmentRepository, AttachmentStorage
from app.modules.audit.application.audit_writer import AuditWriter
from app.modules.audit.domain.entities import AuditChange, AuditContext, AuditEvent
from app.modules.audit.domain.enums import AuditSource
from app.modules.audit.domain.repository import AuditRepository
from app.shared.application.unit_of_work import UnitOfWork
from app.shared.domain.current_user import CurrentUser

TENANT = UUID("11111111-1111-1111-1111-111111111111")
OTHER_TENANT = UUID("22222222-2222-2222-2222-222222222222")
ACTOR = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
PO_ID = UUID("60000000-0000-0000-0000-000000000001")


class Repository:
    def __init__(self, *, fail_create: bool = False) -> None:
        self.rows: list[Attachment] = []
        self.fail_create = fail_create

    async def list_for_entity(
        self, tenant_id: UUID, entity_type: AttachmentEntityType, entity_id: UUID
    ) -> list[Attachment]:
        return [
            row
            for row in self.rows
            if row.tenant_id == tenant_id
            and row.entity_type == entity_type
            and row.entity_id == entity_id
            and row.deleted_at is None
        ]

    async def get(self, tenant_id: UUID, attachment_id: UUID) -> Attachment | None:
        return next(
            (
                row
                for row in self.rows
                if row.tenant_id == tenant_id and row.id == attachment_id and row.deleted_at is None
            ),
            None,
        )

    async def create(self, attachment: Attachment) -> Attachment:
        if self.fail_create:
            raise RuntimeError("database failed")
        self.rows.append(attachment)
        return attachment

    async def soft_delete(
        self, tenant_id: UUID, attachment_id: UUID, expected_version: int, actor_id: UUID
    ) -> Attachment | None:
        row = await self.get(tenant_id, attachment_id)
        if row is None or row.row_version != expected_version:
            return None
        deleted = Attachment(
            **{
                **{name: getattr(row, name) for name in row.__dataclass_fields__},
                "deleted_at": datetime.now(UTC),
                "deleted_by": actor_id,
                "row_version": row.row_version + 1,
            }
        )
        self.rows[self.rows.index(row)] = deleted
        return deleted


class Storage:
    def __init__(self) -> None:
        self.uploads: list[tuple[str, bytes, str | None]] = []
        self.deletes: list[str] = []
        self.urls: list[tuple[str, int]] = []

    async def upload(self, *, object_key: str, content: bytes, content_type: str | None) -> None:
        self.uploads.append((object_key, content, content_type))

    async def delete(self, *, object_key: str) -> None:
        self.deletes.append(object_key)

    async def create_download_url(self, *, object_key: str, expires_in: int) -> str:
        self.urls.append((object_key, expires_in))
        return "https://signed.example.test/download"


class Access:
    def __init__(self, *, allowed: bool = True) -> None:
        self.allowed = allowed
        self.reads: list[tuple[AttachmentEntityType, UUID, UUID]] = []
        self.writes: list[tuple[AttachmentEntityType, UUID, UUID]] = []

    async def require_read(
        self, entity_type: AttachmentEntityType, entity_id: UUID, actor: CurrentUser
    ) -> None:
        self.reads.append((entity_type, entity_id, actor.tenant_id))
        if not self.allowed:
            raise PermissionDenied("denied")

    async def require_write(
        self, entity_type: AttachmentEntityType, entity_id: UUID, actor: CurrentUser
    ) -> None:
        self.writes.append((entity_type, entity_id, actor.tenant_id))
        if not self.allowed:
            raise PermissionDenied("denied")


class AuditStore:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def add_event(self, event: AuditEvent, changes: list[AuditChange]) -> None:
        self.events.append(event)


class EventPublisher:
    def __init__(self) -> None:
        self.uploaded_events: list[tuple[UUID, UUID, str]] = []
        self.deleted_events: list[tuple[UUID, UUID, str]] = []

    async def uploaded(
        self, attachment_id: UUID, entity_id: UUID, filename: str, context: AuditContext
    ) -> None:
        self.uploaded_events.append((attachment_id, entity_id, filename))

    async def deleted(
        self, attachment_id: UUID, entity_id: UUID, filename: str, context: AuditContext
    ) -> None:
        self.deleted_events.append((attachment_id, entity_id, filename))


class Transaction:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


def actor(tenant_id: UUID = TENANT) -> CurrentUser:
    return CurrentUser(ACTOR, tenant_id, "kevin@local.test", "Kevin Admin", True, {})


def context() -> AuditContext:
    return AuditContext(
        TENANT,
        ACTOR,
        "kevin@local.test",
        "Kevin Admin",
        AuditSource.API,
        correlation_id="correlation-1",
        request_id="request-1",
    )


def service(
    repository: Repository | None = None,
    storage: Storage | None = None,
    access: Access | None = None,
) -> tuple[AttachmentUseCases, Repository, Storage, Access, AuditStore, Transaction]:
    repo = repository or Repository()
    store = storage or Storage()
    gate = access or Access()
    audit = AuditStore()
    transaction = Transaction()
    use_cases = AttachmentUseCases(
        cast(AttachmentRepository, cast(Any, repo)),
        cast(AttachmentStorage, cast(Any, store)),
        gate,
        EventPublisher(),
        AuditWriter(cast(AuditRepository, cast(Any, audit))),
        cast(UnitOfWork, transaction),
        bucket_name="private-dev-bucket",
        max_size_bytes=10,
        download_expire_seconds=300,
    )
    return use_cases, repo, store, gate, audit, transaction


def command(
    filename: str = "purchase order.pdf", content: bytes = b"PDF"
) -> UploadAttachmentCommand:
    return UploadAttachmentCommand(
        AttachmentEntityType.CUSTOMER_PO,
        PO_ID,
        filename,
        "application/pdf" if filename.endswith(".pdf") else "application/vnd.ms-excel",
        content,
    )


@pytest.mark.asyncio
async def test_upload_validates_access_uploads_then_persists_and_audits() -> None:
    use_cases, repository, storage, access, audit, transaction = service()
    attachment = await use_cases.upload(command("../PO final.pdf"), actor(), context())

    assert repository.rows == [attachment]
    assert storage.uploads[0][0].startswith(f"{TENANT}/customer-po/{PO_ID}/{attachment.id}/")
    assert storage.uploads[0][0].endswith("PO_final.pdf")
    assert ".." not in storage.uploads[0][0]
    assert access.writes == [(AttachmentEntityType.CUSTOMER_PO, PO_ID, TENANT)]
    assert attachment.uploaded_by == ACTOR
    assert attachment.uploaded_by_display_name == "Kevin Admin"
    assert len(audit.events) == 1
    assert transaction.commits == 1


@pytest.mark.asyncio
async def test_valid_excel_and_file_validation() -> None:
    use_cases, *_ = service()
    excel = await use_cases.upload(command("report.xls", b"123"), actor(), context())
    assert excel.content_type == "application/vnd.ms-excel"

    with pytest.raises(ValidationFailure, match="maximum"):
        await use_cases.upload(command(content=b"12345678901"), actor(), context())
    with pytest.raises(ValidationFailure, match="extension"):
        await use_cases.upload(command("malware.exe"), actor(), context())
    with pytest.raises(ValidationFailure, match="content type"):
        await use_cases.upload(
            UploadAttachmentCommand(
                AttachmentEntityType.CUSTOMER_PO,
                PO_ID,
                "fake.pdf",
                "image/png",
                b"123",
            ),
            actor(),
            context(),
        )


@pytest.mark.asyncio
async def test_upload_without_entity_access_is_rejected_before_storage() -> None:
    use_cases, _, storage, *_ = service(access=Access(allowed=False))
    with pytest.raises(PermissionDenied):
        await use_cases.upload(command(), actor(), context())
    assert storage.uploads == []


@pytest.mark.asyncio
async def test_database_failure_attempts_s3_compensation() -> None:
    use_cases, _, storage, _, _, transaction = service(repository=Repository(fail_create=True))
    with pytest.raises(RuntimeError, match="database failed"):
        await use_cases.upload(command(), actor(), context())
    assert len(storage.uploads) == 1
    assert storage.deletes == [storage.uploads[0][0]]
    assert transaction.rollbacks == 1


@pytest.mark.asyncio
async def test_list_is_tenant_scoped_and_requires_entity_read() -> None:
    use_cases, repository, _, access, _, _ = service()
    own = await use_cases.upload(command(), actor(), context())
    other_values = {name: getattr(own, name) for name in own.__dataclass_fields__}
    other_values.update(id=uuid4(), tenant_id=OTHER_TENANT)
    repository.rows.append(Attachment(**other_values))
    items = await use_cases.list(AttachmentEntityType.CUSTOMER_PO, PO_ID, actor())
    assert items == [own]
    assert access.reads[-1] == (AttachmentEntityType.CUSTOMER_PO, PO_ID, TENANT)


@pytest.mark.asyncio
async def test_download_authorizes_and_returns_short_lived_url() -> None:
    use_cases, _, storage, *_ = service()
    attachment = await use_cases.upload(command(), actor(), context())
    url, expires = await use_cases.download(attachment.id, actor())
    assert url == "https://signed.example.test/download"
    assert expires == 300
    assert storage.urls == [(attachment.object_key, 300)]

    with pytest.raises(EntityNotFound):
        await use_cases.download(attachment.id, actor(OTHER_TENANT))


@pytest.mark.asyncio
async def test_delete_removes_storage_and_soft_deletes_metadata() -> None:
    use_cases, repository, storage, access, audit, transaction = service()
    attachment = await use_cases.upload(command(), actor(), context())
    await use_cases.delete(attachment.id, 1, actor(), context())

    assert storage.deletes == [attachment.object_key]
    assert await repository.get(TENANT, attachment.id) is None
    assert await repository.list_for_entity(TENANT, AttachmentEntityType.CUSTOMER_PO, PO_ID) == []
    assert access.writes[-1] == (AttachmentEntityType.CUSTOMER_PO, PO_ID, TENANT)
    assert len(audit.events) == 2
    assert transaction.commits == 2


def test_object_key_is_tenant_partitioned_and_sanitized() -> None:
    attachment_id = uuid4()
    key = object_key(
        TENANT, AttachmentEntityType.CUSTOMER_PO, PO_ID, attachment_id, "../../a b.pdf"
    )
    assert key == f"{TENANT}/customer-po/{PO_ID}/{attachment_id}/a_b.pdf"
