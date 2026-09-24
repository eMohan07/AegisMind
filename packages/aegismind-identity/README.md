# aegismind-identity

Identity resolution, OIDC claim normalization, and principal management for AegisMind.

## Features
- **IdentityPort**: Contract for principal resolution, group membership resolution, and tenant scoping.
- **OIDC Providers**:
  - `Keycloak`: Realm and resource role mapping, group normalization, and tenant mapping.
  - `Zitadel`: Organization claim mapping (`urn:zitadel:iam:org:id`), project roles, and multi-tenant scoping.
  - `Generic OIDC`: Standard claims (`sub`, `email`, `groups`, `roles`, `tenant_id`).
- **Database Identity Store**:
  - `DatabaseIdentityAdapter`: Builtin database store managing users, group memberships, and tenant scopes.
  - `MemoryIdentityAdapter`: In-memory identity store for unit tests and local development.
