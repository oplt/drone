# Migration safety

`93c855aeb073_create_users_table.py` is the original applied baseline migration.
It contains the first production schema and is intentionally large; it must not
be rewritten or reformatted after deployment. Its provenance is the schema
bootstrap used by the first release of the application.

Future migrations must be small, single-purpose, reversible where feasible, and
must include indexes for new high-volume query paths. Before release:

1. Run `alembic -c backend/alembic.ini upgrade head` against PostgreSQL/PostGIS.
2. Run the migration smoke tests with `make backend-integration-tests`.
3. Verify `alembic ... current` is the single expected head and inspect the
   query plans for livestock risk, analytics overview, and alert polling.

Applied migrations are immutable. A corrective migration is required for every
post-release schema change, including index changes and data backfills.
