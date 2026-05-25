from backend.core.database.session import Session
from backend.modules.missions.repository.reads import MissionRuntimeReadMixin
from backend.modules.missions.repository.writes import MissionRuntimeWriteMixin


class MissionRuntimeRepository(MissionRuntimeReadMixin, MissionRuntimeWriteMixin):
    def __init__(self, session_factory: type[Session] = Session) -> None:
        self._sf = session_factory


mission_runtime_repo = MissionRuntimeRepository()

__all__ = ["MissionRuntimeRepository", "mission_runtime_repo"]
