# Alembic migrations

## Revision policy

- Do **not** rewrite or squash migrations that have already been applied in any environment.
- Keep each new revision focused: one logical schema change (indexes, table, column) per file when practical.
- Target **under ~200 lines** per revision so reviews stay tractable.
- Historical mega-revisions (for example `93c855aeb073_create_users_table.py`) remain as-is for lineage integrity.

## Naming

Use descriptive slugs: `{revision}_{short_purpose}.py`.

## Validation

Run `alembic upgrade head` against PostgreSQL/PostGIS before merging schema changes.
Update `backend/tests/test_migration_postgres.py` when the expected `alembic_version` head changes.
