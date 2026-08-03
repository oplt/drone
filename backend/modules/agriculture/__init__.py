"""Agriculture flight context, telemetry lineage and geospatial foundations.

Keep package import side-effect free.  ORM registration imports this package while
the database session is still being initialized, so importing services here would
create a session/model-registry cycle.
"""

__all__: list[str] = []
