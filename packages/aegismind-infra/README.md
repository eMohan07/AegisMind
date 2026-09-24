# aegismind-infra

Infrastructure package for AegisMind, providing ports and adapters for secret management and object storage.

## Features
- **Envelope Encryption**: AES-256-GCM envelope encryption with per-record Data Encryption Keys (DEKs) wrapped by Key Encryption Keys (KEKs).
- **Secret Storage**:
  - `PostgresEnvelopeSecretStore`: Envelope-encrypted secret store for database persistence.
  - `OpenBaoSecretStore`: REST adapter for OpenBao / Vault secrets engine.
  - `MemorySecretStore`: Fast in-memory secret store for testing and local development.
- **Object Storage**:
  - `S3CompatibleObjectStore`: S3-compatible storage adapter for AWS S3, Garage, SeaweedFS, and MinIO.
  - `MemoryObjectStore`: In-memory object store for isolated hermetic tests.
