# Customer PO dashboard

Phase 1 is a read-only SQL analytics model. Every query uses the authenticated tenant ID,
excludes soft-deleted POs, and applies the existing `OWN`, `ASSIGNED`, `TEAM`, or `ALL` scope
from `dashboard.customer_pos.read`.

- Business date: `customer_purchase_orders.customer_po_date`; POs without this business date are
  excluded consistently from every dashboard aggregation.
- Open statuses: `DRAFT`, `RECEIVED`, `VALIDATING`, `VALIDATED`, `PROCESSING`, and `ON_HOLD`.
- Monetary results: `amount_by_currency`; no FX conversion or cross-currency sum is performed.
- Percentages: share of PO count after filters (not share of mixed-currency value).
- Missing amounts are treated as zero; missing currencies use `UNSPECIFIED`.
- Country: PO snapshot `ship_to_country_code`; null country values are omitted.
- Attention: current `ON_HOLD` and `VALIDATING` counts and amounts only; the latter is exposed as
  the actionable signal code `VALIDATION_PENDING`.
- Previous period: returned when both dates are supplied, using the immediately preceding
  inclusive period of equal length.
- Weekly trend periods start on Monday (PostgreSQL `date_trunc('week', ...)`).

Existing Customer PO indexes cover tenant/date, tenant/status, tenant/customer, tenant/source,
and tenant/owner access patterns, so Phase 1 adds no speculative indexes.

The deterministic development dataset is in `sql/seed_customer_po_dashboard_demo.sql`. Run it
explicitly with the migration/owner database role after `alembic upgrade head`; it creates 120
stable records and uses `ON CONFLICT DO NOTHING`, so reruns are safe. It is never run at
application startup.
