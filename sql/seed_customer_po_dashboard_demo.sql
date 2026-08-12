-- Development-only, deterministic and idempotent dashboard data.
-- Run explicitly after `alembic upgrade head`; this is never executed at startup.
WITH demo AS (
    SELECT
        n,
        (
            substr(md5('dashboard-po-' || n), 1, 8) || '-' ||
            substr(md5('dashboard-po-' || n), 9, 4) || '-' ||
            substr(md5('dashboard-po-' || n), 13, 4) || '-' ||
            substr(md5('dashboard-po-' || n), 17, 4) || '-' ||
            substr(md5('dashboard-po-' || n), 21, 12)
        )::uuid AS id,
        (ARRAY[
            '40000000-0000-0000-0000-000000000001',
            '40000000-0000-0000-0000-000000000002',
            '40000000-0000-0000-0000-000000000003',
            '40000000-0000-0000-0000-000000000004'
        ])[1 + (n - 1) % 4]::uuid AS customer_id,
        (ARRAY[
            'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
            'cccccccc-cccc-cccc-cccc-cccccccccccc'
        ])[1 + (n - 1) % 2]::uuid AS owner_id,
        (ARRAY['DRAFT','RECEIVED','VALIDATING','VALIDATED','PROCESSING',
               'ON_HOLD','CONVERTED','REJECTED','CANCELLED'])[1 + (n - 1) % 9] AS status,
        (ARRAY['MANUAL','IMPORT','API','EDI'])[1 + (n - 1) % 4] AS source,
        (ARRAY['TWD','USD'])[1 + (n - 1) % 2] AS currency,
        (ARRAY['TW','US','JP','DE','SG'])[1 + (n - 1) % 5] AS country
    FROM generate_series(1, 120) AS n
)
INSERT INTO customer_purchase_orders (
    id, tenant_id, customer_id, customer_po_number, customer_po_date,
    currency_code, ship_to_country_code, status, source, owner_user_id,
    total_amount, row_version, created_by, updated_by
)
SELECT
    id,
    '11111111-1111-1111-1111-111111111111'::uuid,
    customer_id,
    'DASH-' || lpad(n::text, 4, '0'),
    DATE '2026-08-01' - (((n - 1) * 3) % 330),
    currency,
    country,
    status,
    source,
    owner_id,
    (5000 + n * 1375)::numeric(20, 6),
    1,
    owner_id,
    owner_id
FROM demo
ON CONFLICT DO NOTHING;
