# Local DB roles

建議用 PostgreSQL admin 帳號建立角色：

```sql
CREATE ROLE scm_owner WITH LOGIN PASSWORD 'local_owner_password';
CREATE ROLE app_runtime WITH LOGIN PASSWORD 'local_dev_password';

GRANT CONNECT ON DATABASE scm_local TO scm_owner;
GRANT CONNECT ON DATABASE scm_local TO app_runtime;

ALTER SCHEMA public OWNER TO scm_owner;
```

`.env`：

```env
DATABASE_URL=postgresql+asyncpg://app_runtime:local_dev_password@localhost:5432/scm_local
MIGRATION_DATABASE_URL=postgresql+asyncpg://scm_owner:local_owner_password@localhost:5432/scm_local
```

再執行：

```bash
alembic upgrade head
```

Migration 會在偵測到 `app_runtime` 已存在時自動授予 runtime 所需 table 權限。
