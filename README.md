# FastAPI IAM + Customer Clean Architecture Example

這是一個可直接拿來理解與測試的範例專案，架構延續原本 Customer API 專案的分層方式，
但把授權模型改成正式版 IAM：

`User -> Primary Role / Groups / Direct Policies -> Policies -> Permission + Effect + Scope -> Effective Permissions`

Customer 是第一個真正驗證 Data Scope 的 Business Module。

## 這個範例刻意解決的舊問題

- 不再使用 `if actor.role == "sales"` / `if actor.role == "admin"` 做授權。
- Permission 統一使用 `resource.action`，例如 `customers.read`。
- `CurrentUser.permissions` 不再只是 `frozenset[str]`，而是 `permission -> effect/scope/sources`。
- Explicit DENY 永遠優先。
- Customer Repository 接收已解析好的 Data Scope，不在每筆 row 重算 IAM。
- 所有正常刪除都是 Soft Delete。
- 使用 `row_version` 做 Optimistic Lock。
- Router / Application / Domain / Infrastructure 責任分離。
- Local Swagger 可以不用 Supabase，直接用 `X-Dev-User-Id` 模擬登入者。
- Production 可以把 Auth Provider 換成 Supabase JWT / 其他 IdP，而 IAM Domain 不需要改。

## 主要目錄

```text
app/
├── api/dependencies/
├── core/
├── infrastructure/database/
├── modules/
│   ├── iam/
│   │   ├── domain/
│   │   ├── application/
│   │   ├── infrastructure/
│   │   └── presentation/
│   └── customers/
│       ├── domain/
│       ├── application/
│       ├── infrastructure/
│       └── presentation/
└── shared/domain/
```

## IAM 資料表

- tenants
- profiles
- roles
- groups
- user_groups
- permissions
- policies
- policy_permissions
- role_policies
- group_policies
- user_policies
- audit_logs

Customer Data Scope：

- customers.owner_user_id -> OWN
- customer_user_assignments -> ASSIGNED
- customer_group_assignments -> TEAM
- ALL -> tenant 內全部 Customer

## 本機啟動

### 1. 建立 venv

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. 建立 `.env`

```bash
cp .env.example .env
```

### 3. PostgreSQL

假設你已建立：

- DB: `scm_local`
- migration role: `scm_owner`
- runtime role: `app_runtime`

執行 migration：

```bash
alembic upgrade head
```

### 4. 啟動

```bash
uvicorn app.main:app --reload
```

Swagger：

`http://127.0.0.1:8000/docs`

## Local Dev Authentication

Authentication is selected explicitly with `AUTH_MODE=dev_header` or
`AUTH_MODE=jwt`. JWT mode never accepts `X-Dev-User-Id` as a fallback.

After migration `0003`, establish a local password without storing plaintext
credentials in migrations or source control:

```bash
APP_ENV=local .venv/bin/python scripts/set_dev_password.py jack@local.test
```

JWT mode requires a random `JWT_SECRET` of at least 32 bytes. Token lifetimes
use `ACCESS_TOKEN_EXPIRE_MINUTES` and `REFRESH_TOKEN_EXPIRE_DAYS`.

`APP_ENV=local` 且 `AUTH_MODE=dev_header` 時，Swagger 每支 API 可傳：

```text
X-Dev-User-Id
```

Seed user UUID：

```text
Kevin Admin:
aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa

Jack Sales:
bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb

Mary Sales:
cccccccc-cccc-cccc-cccc-cccccccccccc

Warehouse User:
dddddddd-dddd-dddd-dddd-dddddddddddd
```

### Jack 範例 Effective Permission

Jack：

- Primary Role = SALES
- Groups = TW_SALES + KEY_ACCOUNT
- Direct Policy = NO_CUSTOMER_EXPORT

最後：

```text
customers.read         ALLOW TEAM
customers.detail.read  ALLOW TEAM
customers.create       ALLOW ALL
customers.update       ALLOW OWN
customers.export       DENY
```

## 建議測試順序

1. `GET /api/v1/iam/me/effective-permissions`
2. `GET /api/v1/customers`
3. 用 Jack 看 TEAM Customer
4. 嘗試更新 Jack 自己的 Customer -> 成功
5. 嘗試更新 Mary 的 Customer -> 404（不洩漏存在性）
6. `POST /customers/{id}/soft-delete`
7. `GET /customers?show_deleted=true`
8. `POST /customers/{id}/restore`
9. 用 Warehouse User 呼叫 Customer API -> 403

## 權限效能原則

每個 HTTP request：

1. Auth 解析一次 user id
2. IAM Resolver 解析一次 Effective Permissions
3. `CurrentUser` 放在 request dependency cache 中
4. Customer Use Case 只取得 `scope_for("customers.read")`
5. Repository 把 Scope 轉成 SQL filter

**禁止每一筆 Customer 重新 JOIN IAM tables。**

正式大量流量時，可在 IAM Repository 之外增加 Effective Permission Cache；
Domain / Use Case 不需要修改。
