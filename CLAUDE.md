# AegisMind Engineering Guide

AegisMind is an open-source, self-hostable, modular enterprise knowledge platform with document-level access control (Zanzibar and SpiceDB) enforced strictly at retrieval time.

## Architectural Foundation

AegisMind enforces a strict Ports and Adapters (hexagonal) architecture across all workspace packages and connectors:
- **Core Domain and Ports**: Core packages define abstract interfaces (ports) and business domain logic. Core modules never import concrete adapters directly.
- **Dynamic Adapter Resolution**: Concrete adapters register via Python entry points and are dynamically discovered via `aegismind_core.registry`.
- **Bring Your Own Model (BYOM)**: Pluggable embedders, vector storage backends, and rerankers can be swapped without touching core retrieval logic.

## Non-Negotiable Engineering Rules

1. **Writing Convention**:
   - No em dashes anywhere in code, docstrings, markdown docs, or git commit messages.
   - Use commas, periods, colons, or parentheses instead.

2. **Permission Correctness is Sacred**:
   - Permissions must be evaluated at retrieval time, not after generation.
   - The retrieval pipeline must overfetch candidates by a multiplier between 3x and 5x of requested top_k.
   - The retrieval pipeline must invoke `authz.bulk_check` using consistency level `at_least_as_fresh`.
   - Only explicitly permitted documents and chunks are retained.
   - The permitted candidate set is then reranked to yield the final top_k results.

3. **Python Standards**:
   - Python 3.12 or newer.
   - Every module must begin with `from __future__ import annotations`.
   - Strict static typing with complete type annotations.
   - Pydantic v2 schemas for all data models, queries, and permissions.
   - No bare `except` clauses.
   - No `print` statements (use structured logging with `logging.getLogger(__name__)`).

4. **Git and Commit Hygiene**:
   - Conventional Commits format (`feat:`, `fix:`, `docs:`, `test:`, `chore:`).
   - Atomic commits grouped by major component.

## Workspace Organization

- `packages/*`: Core domain, ports, authorization engine, API service, and core utilities.
- `connectors/*`: Data ingestion connectors for enterprise document sources.
- `tests/*`: Unit, integration, conformance, and security guardrail test suites.

## Common Development Commands

```powershell
# Sync workspace virtual environment and dependencies
uv sync --all-groups

# Run linting and code formatting checks
uv run ruff check .
uv run ruff format --check .

# Run type checker
uv run mypy .

# Run test suite
uv run pytest -v

# Run permission-specific tests
uv run pytest -m permission
```
