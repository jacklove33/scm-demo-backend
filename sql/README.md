# Local Database Roles

Use a PostgreSQL administrator account to create the local roles:

```sql
CREATE ROLE scm_owner WITH LOGIN PASSWORD 'local_owner_password';
CREATE ROLE app_runtime WITH LOGIN PASSWORD 'local_dev_password';

GRANT CONNECT ON DATABASE scm_local TO scm_owner;
GRANT CONNECT ON DATABASE scm_local TO app_runtime;

ALTER SCHEMA public OWNER TO scm_owner;
```

Configure `.env` as follows:

```env
DATABASE_URL=postgresql+asyncpg://app_runtime:local_dev_password@localhost:5432/scm_local
MIGRATION_DATABASE_URL=postgresql+asyncpg://scm_owner:local_owner_password@localhost:5432/scm_local
```

Then run:

```bash
alembic upgrade head
```

When the migration detects that `app_runtime` already exists, it automatically grants the runtime table permissions required by the application.
