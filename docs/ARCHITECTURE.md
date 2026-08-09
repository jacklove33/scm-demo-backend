# Architecture

```text
HTTP
 ↓
FastAPI Router
 ↓
Authentication Dependency
 ↓
CurrentUserService
 ↓
IAM Repository ────────┐
 ↓                     │
EffectivePermissionResolver
 ↓
CurrentUser(permission -> effect/scope)
 ↓
Customer Use Case
 ↓
Customer Repository
 ↓
PostgreSQL
```

## Clean Architecture

- Domain: pure business types + repository protocols.
- Application: authorization orchestration and use cases.
- Infrastructure: SQLAlchemy/PostgreSQL.
- Presentation: FastAPI schemas/router.

No business module is allowed to hardcode role names for authorization.
