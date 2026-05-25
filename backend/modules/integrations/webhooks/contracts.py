VALID_WEBHOOK_EVENTS: frozenset[str] = frozenset(
    {
        "mission.completed",
        "mapping.ready",
        "deliverable.ready",
        "export.ready",
        "alert.triggered",
        "fmis.field_update",
    }
)
