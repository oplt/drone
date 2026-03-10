from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from backend.ml.patrol.models import Track, GeoPoint, AnomalyEvent
from backend.ml.patrol.zones import ZoneEngine


@dataclass
class _TrackEventState:
    last_seen_at: datetime
    current_restricted_zones: set[str] = field(default_factory=set)

    intrusion_emitted: bool = False
    loitering_emitted: bool = False

    last_restricted_zone_entry_at: datetime | None = None
    last_loitering_at: datetime | None = None


class AnomalyScorer:
    """
    Stateful anomaly scorer.

    Design goals:
    - do not emit intrusion_detected every frame
    - only emit intrusion_detected when a person first enters a restricted zone
    - only emit restricted_zone_entry on zone-entry edge
    - only emit loitering once per track lifetime (or after cooldown if you later extend it)
    - clean up state for tracks that disappeared
    """

    def __init__(
            self,
            zone_engine: ZoneEngine,
            loitering_seconds: int = 12,
            person_min_confidence: float = 0.60,
            vehicle_min_confidence: float = 0.60,
    ):
        self.zone_engine = zone_engine
        self.loitering_seconds = int(loitering_seconds)
        self._loitering_fired: set[int] = set()
        self.person_min_confidence = float(person_min_confidence)
        self.vehicle_min_confidence = float(vehicle_min_confidence)

        self._track_state: dict[int, _TrackEventState] = {}

    def _cleanup_missing_tracks(self, active_track_ids: set[int]) -> None:
        stale_ids = [tid for tid in self._track_state.keys() if tid not in active_track_ids]
        for tid in stale_ids:
            self._track_state.pop(tid, None)

    def _get_state(self, track: Track, now: datetime) -> _TrackEventState:
        state = self._track_state.get(track.track_id)
        if state is None:
            state = _TrackEventState(last_seen_at=now)
            self._track_state[track.track_id] = state
        else:
            state.last_seen_at = now
        return state

    def score(
            self,
            tracks: Iterable[Track],
            gps_lookup: dict[int, GeoPoint],
            now: datetime,
    ) -> list[AnomalyEvent]:
        out: list[AnomalyEvent] = []

        tracks = list(tracks)
        active_track_ids = {t.track_id for t in tracks}
        self._cleanup_missing_tracks(active_track_ids)

        for track in tracks:
            point = gps_lookup.get(track.track_id)
            if point is None:
                continue

            state = self._get_state(track, now)

            zone_hits = self.zone_engine.find_zone_hits(point)
            restricted_zone_names = {
                z.name for z in zone_hits if getattr(z, "restricted", False)
            }

            entered_restricted_zones = restricted_zone_names - state.current_restricted_zones
            state.current_restricted_zones = restricted_zone_names

            # 1) restricted_zone_entry: emit only when entering a restricted zone
            if entered_restricted_zones and track.label in {
                "person", "car", "truck", "motorcycle", "bicycle"
            }:
                min_conf = (
                    self.person_min_confidence
                    if track.label == "person"
                    else self.vehicle_min_confidence
                )

                if track.confidence >= min_conf:
                    entered_sorted = sorted(entered_restricted_zones)
                    out.append(
                        AnomalyEvent(
                            event_type="restricted_zone_entry",
                            confidence=min(0.99, max(0.50, track.confidence)),
                            location=point,
                            payload={
                                "track_id": track.track_id,
                                "label": track.label,
                                "zones": entered_sorted,
                                "bbox": track.bbox,
                            },
                        )
                    )
                    state.last_restricted_zone_entry_at = now

            # 2) intrusion_detected:
            # only for person + only in restricted zone + only once per track lifetime
            if (
                    track.label == "person"
                    and restricted_zone_names
                    and not state.loitering_emitted
                    and track.first_seen is not None
                    and (now - track.first_seen).total_seconds() >= self.loitering_seconds
            ):
                out.append(
                    AnomalyEvent(
                        event_type="intrusion_detected",
                        confidence=track.confidence,
                        location=point,
                        payload={
                            "track_id": track.track_id,
                            "label": track.label,
                            "zones": sorted(restricted_zone_names),
                            "bbox": track.bbox,
                        },
                    )
                )
                state.loitering_emitted = True

            # 3) loitering:
            # only once per track and only if the track is in a restricted zone
            if (
                    restricted_zone_names
                    and not state.loitering_emitted
                    and track.first_seen is not None
                    and (now - track.first_seen).total_seconds() >= self.loitering_seconds
            ):
                out.append(
                    AnomalyEvent(
                        event_type="loitering",
                        confidence=min(0.95, max(0.50, track.confidence)),
                        location=point,
                        payload={
                            "track_id": track.track_id,
                            "label": track.label,
                            "zones": sorted(restricted_zone_names),
                            "seconds_visible": int((now - track.first_seen).total_seconds()),
                            "bbox": track.bbox,
                        },
                    )
                )
                state.loitering_emitted = True
                state.last_loitering_at = now

        return out
