# Skill: Build Supplier Module from Customer Golden Reference

## Purpose

Use the existing **Customer module as the Golden Reference** to implement a complete **Supplier module** across backend and frontend.

This skill is intentionally conservative:

- Reuse the existing platform architecture.
- Do not redesign shared infrastructure.
- Do not create a parallel business-partner model.
- Do not modify Customer behavior unless a truly shared defect is discovered.
- Supplier must follow the same architectural and security rules already proven by Customer.

---

# 1. Project Roots

Backend root:

```text
/Users/jackwu/Documents/Project/backend/scm-demo-backend
```

Frontend root:

```text
/Users/jackwu/Documents/Project/frontend/scm-demo-frontend
```

If the repository is mounted elsewhere, locate the current backend/frontend roots first, then keep the same relative paths.

Do **not** scan the whole project.

Start from the existing Customer reference files listed below.

---

# 2. Customer Golden Reference — Backend

Read these files first:

```text
app/modules/customers/domain/entities.py
app/modules/customers/domain/repository.py

app/modules/customers/application/commands.py
app/modules/customers/application/dto.py
app/modules/customers/application/use_cases.py

app/modules/customers/infrastructure/models.py
app/modules/customers/infrastructure/repository.py

app/modules/customers/presentation/schemas.py
app/modules/customers/presentation/router.py

app/api/dependencies/customers.py
app/api/v1/router.py
```

Also read the relevant Customer tests only.

Do not scan unrelated modules unless one of the files above imports a shared dependency that must be understood.

---

# 3. Customer Golden Reference — Frontend

Read these files first:

```text
src/modules/customers/domain/types.ts
src/modules/customers/domain/CustomerGateway.ts

src/modules/customers/application/customerHooks.ts

src/modules/customers/infrastructure/fastapi/FastApiCustomerGateway.ts

src/modules/customers/presentation/**
```

If the current branch uses an EntityDefinition config, also read:

```text
src/modules/customers/presentation/config/**
```

Read only the shared infrastructure directly used by Customer when necessary:

```text
src/shared/entity-engine/**
src/shared/validation/**
src/platform/api/**
src/platform/errors/**
src/platform/permissions/**
```

Do not redesign these shared components.

---

# 4. Important Domain Rule

The current Customer implementation does **not** use a standalone `customers` master table.

Customer is represented as:

```text
Business Partner
+
Partner Role = CUSTOMER
```

Supplier must follow the same model:

```text
Business Partner
+
Partner Role = SUPPLIER
```

Do **not** create a duplicate master table containing another copy of:

```text
partner_name
tax_id
country_code
currency_code
payment_term_id
owner_user_id
addresses
```

unless the existing database architecture explicitly requires a Supplier-specific extension table for truly Supplier-only attributes.

The shared master data remains in the Business Partner model.

---

# 5. Existing Customer Mapping to Copy

The Customer repository currently maps approximately:

```text
Customer.customer_code
    -> BusinessPartnerModel.partner_code

Customer.customer_name
    -> BusinessPartnerModel.partner_name

Customer.tax_id
    -> BusinessPartnerModel.tax_id

Customer.country_code
    -> BusinessPartnerModel.country_code

Customer.currency_code
    -> BusinessPartnerModel.currency_code

Customer.payment_term_id
    -> BusinessPartnerModel.payment_term_id

Customer.owner_user_id
    -> BusinessPartnerModel.owner_user_id

Customer.status
    -> BusinessPartnerModel.status
```

Addresses use:

```text
PartnerAddressModel
```

Customer identity is determined by:

```text
PartnerRoleModel.role_type = "CUSTOMER"
```

Supplier must mirror this using:

```python
SUPPLIER_ROLE = "SUPPLIER"
```

and:

```text
PartnerRoleModel.role_type = "SUPPLIER"
```

---

# 6. Supplier Scope

Implement Supplier as a complete Master Data module.

Minimum required functionality:

```text
Search/List
Get Detail
Create
Update
Soft Delete
Restore
Owner
Addresses
Permissions
Capabilities
Optimistic Lock
Audit integration
Date Search
Sorting
Pagination
Tenant isolation
Frontend i18n
Frontend validation
Backend validation
Tests
```

Do not implement Purchase Orders in this task.

Do not implement Supplier dashboard analytics in this task.

Do not implement EDI in this task.

---

# 7. Supplier Domain Model

Create a Supplier domain entity following the Customer entity.

Suggested business-facing fields:

```text
id
tenant_id

supplier_code
supplier_name

tax_id
country_code
currency_code
payment_term_id
owner_user_id

status

deleted_at
deleted_by

row_version
created_at
updated_at

addresses
```

Use the actual Customer fields as the source of truth.

Do not invent Supplier-only fields in this first pass.

If the database already contains Supplier-specific fields, report them before implementing them.

---

# 8. Supplier Repository Contract

Create:

```text
app/modules/suppliers/domain/repository.py
```

Mirror the Customer repository contract.

Expected concepts:

```python
SupplierSearchCriteria
SupplierAccessFacts
SupplierSearchItem
SupplierPage
SupplierRepository(Protocol)
```

The repository should expose equivalents of:

```text
find_existing_codes
find_valid_payment_term_ids
find_valid_owner_ids

search
get_by_id
get_access_facts

create
create_many

update
soft_delete
restore
```

Do not remove the Protocol pattern.

The concrete SQLAlchemy implementation does not need explicit Python inheritance from the Protocol if the current Customer architecture uses structural typing.

---

# 9. Supplier SQLAlchemy Repository

Create:

```text
app/modules/suppliers/infrastructure/repository.py
```

Use the Customer `SqlAlchemyCustomerRepository` as the direct implementation reference.

Create:

```python
class SqlAlchemySupplierRepository:
```

The critical difference is:

```python
SUPPLIER_ROLE = "SUPPLIER"
```

The Supplier base query must conceptually be:

```text
BusinessPartnerModel
JOIN PartnerRoleModel
WHERE role_type = SUPPLIER
```

Do not query Customer role.

---

# 10. Supplier Create Mapping

When creating a Supplier:

1. Create/reuse one `BusinessPartnerModel`.
2. Create Supplier addresses through `PartnerAddressModel`.
3. Add a `PartnerRoleModel` with:

```python
role_type="SUPPLIER"
```

Conceptually:

```python
bp = BusinessPartnerModel(
    id=supplier.id,
    tenant_id=supplier.tenant_id,
    partner_code=supplier.supplier_code,
    partner_name=supplier.supplier_name,
    tax_id=supplier.tax_id,
    country_code=supplier.country_code,
    currency_code=supplier.currency_code,
    payment_term_id=supplier.payment_term_id,
    owner_user_id=supplier.owner_user_id,
    status=supplier.status,
    row_version=1,
)
```

and:

```python
PartnerRoleModel(
    tenant_id=supplier.tenant_id,
    partner_id=supplier.id,
    role_type=SUPPLIER_ROLE,
)
```

---

# 11. Critical Existing-Partner Rule

Before blindly copying Customer create logic, inspect how the current database handles a Business Partner that already exists with another role.

Important scenario:

```text
ABC Corp already exists as CUSTOMER
and now must also become SUPPLIER
```

The desired business model should ideally support:

```text
one BusinessPartnerModel
+
CUSTOMER role
+
SUPPLIER role
```

Do not create duplicate Business Partners merely because a Supplier role is added.

First inspect:

```text
BusinessPartnerModel unique constraints
PartnerRoleModel unique constraints
existing use cases
existing migrations
```

Then report whether the current Customer implementation already supports multi-role partners.

If the architecture does **not** yet support safely attaching a second role, do not silently redesign it.

Report:

```text
MULTI_ROLE_GAP
```

with the exact affected files and recommended minimal change.

---

# 12. Permission Scope

Supplier must use the same permission-scope behavior as Customer.

Reuse:

```text
PermissionScope.ALL
PermissionScope.OWN
PermissionScope.ASSIGNED
PermissionScope.TEAM
```

Do not create a second scope system.

Supplier repository queries must always enforce:

```text
tenant_id
+
permission scope
```

Never trust tenant ID from frontend request bodies.

---

# 13. Supplier Assignment Tables

Inspect the current Customer implementation:

```text
CustomerUserAssignmentModel
CustomerGroupAssignmentModel
```

Do not automatically copy these tables under new names until checking the existing DB design.

Determine whether Supplier should use:

A. Supplier-specific assignment tables, or  
B. Generic Business Partner assignment tables if they already exist.

If only Customer-specific assignment tables exist today, report the architectural gap before adding Supplier assignments.

Do not quietly overload Customer assignment tables for Supplier records.

---

# 14. Backend API

Create Supplier REST endpoints following Customer endpoint conventions.

Expected routes:

```text
GET    /api/v1/suppliers
GET    /api/v1/suppliers/{id}
POST   /api/v1/suppliers
PUT/PATCH /api/v1/suppliers/{id}
DELETE /api/v1/suppliers/{id}
POST   /api/v1/suppliers/{id}/restore
```

Use the exact method conventions already used by Customer.

Do not invent a different CRUD style.

---

# 15. Supplier Search

Mirror Customer search.

Support at least:

```text
page
page_size

supplier_code
supplier_name_prefix
status

created_date_from
created_date_to
updated_date_from
updated_date_to

show_deleted
sort_field
sort_direction
```

Use the same date-range convention already proven by Customer:

```text
from = inclusive
to = exclusive next-day boundary
```

Example:

```text
updated_date_from=2026-08-15
updated_date_to=2026-08-15
```

must query conceptually:

```text
updated_at >= 2026-08-15 00:00
updated_at <  2026-08-16 00:00
```

Reuse the same maximum date-range rule if Customer currently enforces one.

Do not invent a different Supplier date-search rule.

---

# 16. Backend Validation

Use Customer schemas as the validation baseline.

Before coding, produce:

```text
CUSTOMER -> SUPPLIER VALIDATION MATRIX
```

For each field show:

```text
Customer backend rule
Supplier proposed rule
Same / intentionally different
```

Default policy:

```text
Supplier = Customer validation
```

unless there is a documented Supplier-specific reason.

Keep:

```python
extra="forbid"
```

if Customer create/update currently uses it.

---

# 17. Read Model vs Write Model

Follow the pattern proven in Customer PO.

Read models may contain enriched display fields:

```text
owner_user_id
owner_display_name
```

Frontend:

```text
ownerUserId
ownerDisplayName
```

Write models should contain only writable IDs:

```text
ownerUserId
```

API payload:

```text
owner_user_id
```

Do not submit:

```text
owner_display_name
```

The same principle applies to any:

```text
paymentTermName
countryName
createdByDisplayName
```

Read enrichment must not leak into update payloads.

---

# 18. Optimistic Lock

Supplier must use the same optimistic locking mechanism as Customer.

Expected concept:

```text
row_version
```

Update:

```text
WHERE id = supplier_id
AND tenant_id = tenant_id
AND row_version = expected_version
```

then:

```text
row_version = row_version + 1
```

Conflict:

```text
409 VersionConflict
```

Do not create last-write-wins behavior.

---

# 19. Soft Delete / Restore

Mirror Customer behavior.

If Customer soft delete is role-based:

```text
PartnerRoleModel.deleted_at
PartnerRoleModel.deleted_by
```

Supplier should also soft-delete only the Supplier role, not destroy the entire Business Partner.

This is especially important if a partner is both:

```text
CUSTOMER
and
SUPPLIER
```

Deleting Supplier must not remove the Customer role.

---

# 20. Frontend Supplier Module

Create:

```text
src/modules/suppliers/
```

Follow Customer module structure exactly.

Expected structure:

```text
domain/
  types.ts
  SupplierGateway.ts

application/
  supplierHooks.ts
  or the current Customer equivalent

infrastructure/
  fastapi/
    FastApiSupplierGateway.ts

presentation/
  SuppliersPage.tsx
  SupplierForm.tsx
  SupplierStatusChip.tsx
  config/
    supplier.entity.tsx
```

Use the actual current Customer structure as the source of truth.

Do not create a new frontend architectural pattern.

---

# 21. Frontend Types

Create separate read/write types.

Example concept:

```ts
export interface Supplier {
  id: string;
  supplierCode: string;
  supplierName: string;

  ownerUserId?: string | null;
  ownerDisplayName?: string | null;

  rowVersion: number;
  createdAt: string;
  updatedAt: string;

  capabilities: SupplierCapabilities;
}
```

Create:

```ts
CreateSupplierInput
UpdateSupplierInput
SupplierFilters
```

Do not spread the read model into write inputs.

---

# 22. FastApiSupplierGateway

Reuse the shared:

```text
apiClient / apiFetch
AppError
request ID
correlation ID
```

Do not create Supplier-specific HTTP infrastructure.

Gateway responsibilities:

```text
API DTO -> frontend read model
frontend write model -> API payload
```

Use explicit whitelist mapping.

Do not write:

```ts
snakeCaseKeys({ ...supplier })
```

for update.

---

# 23. EntityDefinition

Supplier must use the same Entity Engine as Customer.

Create a Supplier definition analogous to Customer.

Expected list columns:

```text
supplierCode
supplierName
ownerDisplayName
status
updatedAt
```

Expected filters:

```text
supplierCode
supplierNamePrefix
status
createdDateFrom
createdDateTo
updatedDateFrom
updatedDateTo
```

Use the same date validation primitives and cross-field date-range validation already used by Customer.

---

# 24. Supplier Form

Mirror Customer Form behavior.

Important ID/display rules:

```text
Owner:
value = ownerUserId
label = ownerDisplayName

Payment Term:
value = paymentTermId
label = payment term display name
```

Do not store display labels as relationship identifiers.

If addresses are part of Customer create/edit, Supplier should reuse the same address UX pattern.

---

# 25. Frontend Validation

Do not invent stronger validation than backend.

First compare Customer backend/frontend validation.

Supplier frontend should mirror Supplier backend.

For each field:

```text
required
min/max length
pattern
enum
date format
```

must align.

Backend remains authoritative.

Frontend validation is UX only.

---

# 26. Capabilities

Reuse the Customer capability pattern.

Expected concepts may include:

```text
read
update
delete
restore
assignOwner
```

Use the actual Customer capability structure.

Frontend should use backend-returned capabilities.

Do not hardcode role names:

```ts
if (role === 'ADMIN')
```

---

# 27. Permissions

Create Supplier permissions following Customer naming conventions.

Example only:

```text
suppliers.read
suppliers.create
suppliers.update
suppliers.delete
suppliers.restore
```

Use the project’s actual singular/plural naming convention.

If permission records/seeds are required, create them using the existing IAM migration/seed pattern.

Do not create another permission engine.

---

# 28. Audit

Reuse existing audit infrastructure.

Supplier events should follow Customer event patterns:

```text
CREATE
UPDATE
DELETE
RESTORE
```

Do not create Supplier-specific audit storage.

---

# 29. i18n

No hard-coded user-facing English text.

Add Supplier translation keys to the existing i18n resources.

Expected concepts:

```text
suppliers.title
suppliers.subtitle

suppliers.supplierCode
suppliers.supplierName
suppliers.owner
suppliers.status

suppliers.create
suppliers.edit
```

Reuse common keys where possible:

```text
common.status
common.updatedAt
common.view
common.edit
common.delete
common.restore
```

---

# 30. Import / Export

If Customer currently has production-ready Import/Export and Supplier is intended to support it in this phase, mirror it.

If Customer Import includes:

```text
ImportDefinition
headerKey
i18n template headers
validation
batch submit
```

reuse the exact architecture.

If Supplier Import/Export is outside this sprint, do not implement partial placeholders.

Report it as:

```text
DEFERRED
```

---

# 31. Database Migration

Do not create a Supplier master table if the existing Business Partner design can represent Supplier.

Migration may still be required for:

```text
permission seeds
role constraints
supplier assignment tables
supplier-specific extension fields
indexes
```

Before creating a migration, explain why it is necessary.

If no DB schema change is needed, explicitly report:

```text
Supplier master data reuses existing Business Partner tables.
No Supplier master-table migration required.
```

---

# 32. Router / Dependency Wiring

This is critical.

Do not stop after creating Protocol + concrete repository.

Find the Customer dependency wiring.

Create the Supplier equivalent that connects:

```text
SqlAlchemySupplierRepository(session)
        ↓
SupplierRepository Protocol expectation
        ↓
Supplier use cases
        ↓
Supplier router
```

Also register the Supplier router under the existing API v1 router.

The module is not complete until the runtime wiring exists.

---

# 33. Tests — Backend

Mirror Customer tests.

At minimum:

```text
search supplier
get supplier
create supplier
update supplier
soft delete
restore

tenant isolation
permission scope ALL
permission scope OWN
permission scope ASSIGNED
permission scope TEAM

owner validation
payment term validation

duplicate supplier/partner code behavior
optimistic lock conflict

date search
sorting
pagination

extra field forbidden
```

Also test multi-role behavior if the architecture supports:

```text
same Business Partner = CUSTOMER + SUPPLIER
```

---

# 34. Tests — Frontend

At minimum:

```text
Supplier gateway response mapping
Supplier create serialization
Supplier update serialization

read-only display fields excluded from write payload

Owner:
value = UUID
label = display name

search filters
date filters
pagination

create form validation
edit form validation

capability visibility
delete / restore actions

409 mapping
422 field errors
403 permission behavior
```

---

# 35. Protected Areas

Do not modify these unless a verified shared defect blocks Supplier:

Backend:

```text
app/core/**
app/shared/**
auth core
IAM core
logging core
database/session core
```

Frontend:

```text
src/platform/api/**
src/platform/logging/**
src/platform/auth/**
src/platform/permissions/**
src/shared/entity-engine/**
```

If a shared change appears necessary, stop that specific change and report:

```text
SHARED_PLATFORM_CHANGE_REQUIRED
```

with:

```text
why
affected file
minimal proposed change
Customer regression risk
```

Do not casually refactor the platform.

---

# 36. Implementation Order

Follow this sequence.

## Phase A — Reference Audit

1. Read Customer backend reference.
2. Read Customer frontend reference.
3. Identify actual DB tables.
4. Identify permission/capability patterns.
5. Identify dependency wiring.
6. Identify test patterns.
7. Produce a short Supplier implementation plan.

## Phase B — Backend

8. Domain entity.
9. Repository Protocol.
10. Commands / DTO.
11. Use cases.
12. SQLAlchemy repository.
13. Schemas.
14. Router.
15. Dependency wiring.
16. API v1 router registration.
17. Permissions/audit integration.
18. Backend tests.

## Phase C — Frontend

19. Domain types.
20. SupplierGateway.
21. FastApiSupplierGateway.
22. React Query/application hooks.
23. EntityDefinition.
24. SupplierForm.
25. Page/routes.
26. i18n.
27. Frontend tests.

## Phase D — Verification

28. Run backend tests.
29. Run backend typecheck/lint.
30. Run frontend typecheck.
31. Run frontend lint.
32. Run frontend tests.
33. Run frontend build.
34. Review Network payloads for create/update.

---

# 37. Completion Gate

Supplier is complete only when:

```text
Backend search works
Backend detail works
Backend create works
Backend update works
Backend soft delete works
Backend restore works

Supplier uses Business Partner + SUPPLIER role
No duplicate Supplier master table was introduced

Tenant isolation passes
Permission scope passes
Capabilities pass
Optimistic locking passes
Audit passes

Frontend list works
Frontend create works
Frontend edit works
Frontend search works
Frontend date search works
Frontend owner display/write contract works

Read/write models remain separated

Backend tests pass
Backend typecheck/lint pass

Frontend typecheck passes
Frontend tests pass
Frontend build passes
```

---

# 38. Final Review

Before declaring completion, inspect:

```bash
git status --short
```

Then review every modified/added Supplier-related file.

Do not leave accidental Customer changes.

Do not leave unrelated platform refactors.

---

# 39. Final Report Format

Return:

```text
SUPPLIER IMPLEMENTATION
=======================

Customer reference files reviewed:
- ...

Supplier files created:
- ...

Supplier files changed:
- ...

DATABASE MODEL
--------------
Business Partner reuse:
PASS / FAIL

SUPPLIER role:
PASS / FAIL

New Supplier master table created:
YES / NO

Multi-role CUSTOMER + SUPPLIER:
SUPPORTED / GAP / NOT TESTED

BACKEND
-------
Domain:
PASS / FAIL

Repository Protocol:
PASS / FAIL

SQLAlchemy Repository:
PASS / FAIL

Use Cases:
PASS / FAIL

Schemas:
PASS / FAIL

Router:
PASS / FAIL

Dependency Wiring:
PASS / FAIL

Tenant Isolation:
PASS / FAIL

Permission Scope:
PASS / FAIL

Optimistic Lock:
PASS / FAIL

Soft Delete / Restore:
PASS / FAIL

Audit:
PASS / FAIL

FRONTEND
--------
Types:
PASS / FAIL

Gateway:
PASS / FAIL

Hooks:
PASS / FAIL

EntityDefinition:
PASS / FAIL

Form:
PASS / FAIL

Validation:
PASS / FAIL

Owner Contract:
PASS / FAIL

i18n:
PASS / FAIL

TESTS
-----
Backend tests:
PASS / FAIL

Backend typecheck:
PASS / FAIL

Backend lint:
PASS / FAIL

Frontend typecheck:
PASS / FAIL

Frontend lint:
PASS / FAIL

Frontend tests:
PASS / FAIL

Frontend build:
PASS / FAIL

REMAINING GAPS
--------------
- ...
```

---

# 40. Guiding Principle

Do not ask:

> "How would I design a Supplier module from scratch?"

Ask:

> "How does the existing Customer Golden Reference solve this, and what is the smallest Supplier-specific difference?"

The expected relationship is:

```text
Customer
    = Business Partner + CUSTOMER role

Supplier
    = Business Partner + SUPPLIER role
```

Supplier should feel like a sibling of Customer, not a second architecture.
