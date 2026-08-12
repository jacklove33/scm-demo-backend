# Customer PO event timeline

`customer_po_events` is an append-only, business-facing timeline. It complements rather than
replaces the authoritative `customer_po_status_events` workflow history and field-level Audit.

- Writes currently integrated: `CREATE`, `UPDATE`, `STATUS_CHANGE`, `SOFT_DELETE`, `RESTORE`.
- Future event types are controlled enums only; no email, attachment, note, or EDI operation was
  fabricated by this change.
- Categories are derived centrally from event type, never accepted from API clients.
- Actor, source, request ID, and correlation ID come from the trusted request/Audit context.
- Timeline order is newest first by `occurred_at`, then event ID for deterministic pagination.
- `GET /api/v1/customer-pos/{customer_po_id}/events` uses `customer_pos.detail.read` and the
  existing Customer PO visibility scope before reading events. Tenant ID is always taken from
  `CurrentUser`; soft-deleted POs remain readable under existing detail semantics.
- Event insertion uses the same SQLAlchemy session and unit-of-work commit as the PO mutation,
  status event, and Audit event. Failure of any write rolls the whole mutation back.
- Runtime database privileges permit only `SELECT` and `INSERT` on the event table; there are no
  event update or delete APIs.
