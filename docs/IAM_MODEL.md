# IAM Model

```text
User
├── Primary Role ──> Role Policies ──┐
├── Groups ────────> Group Policies ─┼─> Policies
└── Direct Policies ─────────────────┘      │
                                            ▼
                                  Policy Permissions
                                  Permission + Effect + Scope
                                            │
                                            ▼
                                  Effective Permissions
```

Conflict rules:

1. Explicit DENY wins.
2. No ALLOW = deny by default.
3. Multiple ALLOW grants merge scope.
4. Phase 1 scope precedence: NONE < OWN < ASSIGNED < TEAM < ALL.

Data scope is enforced in repositories, not React and not role hardcoding.
