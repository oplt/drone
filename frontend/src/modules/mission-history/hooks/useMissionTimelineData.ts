import { useQueries } from "@tanstack/react-query";

import {
  fetchMissionCommands,
  fetchMissionCompliance,
  fetchMissionDetail,
  fetchMissionEvents,
  fetchMissionPreflight,
  fetchMissionTransitions,
} from "../api/missionHistoryApi";
import type { TimelineEntry } from "../missionTimelineTypes";

type MissionDetail = {
  mission_name?: string;
  mission_type?: string;
  state?: string;
  created_at?: number;
  updated_at?: number;
  preflight_run_id?: string;
  last_error?: string;
};

type TimelineQuery = {
  isError: boolean;
  isFetching: boolean;
  error: unknown;
  refetch: () => Promise<unknown>;
};

export function useMissionTimelineData(flightId: string | undefined) {
  const [missionQ, preflightQ, transitionsQ, commandsQ, eventsQ, complianceQ] = useQueries({
    queries: [
      {
        queryKey: ["mission", flightId],
        queryFn: () => fetchMissionDetail<MissionDetail>(flightId!),
        enabled: Boolean(flightId),
      },
      {
        queryKey: ["mission-preflight", flightId],
        queryFn: () => fetchMissionPreflight(flightId!),
        enabled: Boolean(flightId),
        retry: false,
      },
      {
        queryKey: ["mission-transitions", flightId],
        queryFn: () => fetchMissionTransitions<Array<Record<string, unknown>>>(flightId!),
        enabled: Boolean(flightId),
      },
      {
        queryKey: ["mission-commands", flightId],
        queryFn: () => fetchMissionCommands<Array<Record<string, unknown>>>(flightId!),
        enabled: Boolean(flightId),
      },
      {
        queryKey: ["mission-events", flightId],
        queryFn: () => fetchMissionEvents<Array<Record<string, unknown>>>(flightId!),
        enabled: Boolean(flightId),
      },
      {
        queryKey: ["mission-compliance", flightId],
        queryFn: () => fetchMissionCompliance(flightId!),
        enabled: Boolean(flightId),
        retry: false,
      },
    ],
  });

  const loading =
    missionQ.isLoading || transitionsQ.isLoading || commandsQ.isLoading || eventsQ.isLoading;

  const entries: TimelineEntry[] = [];

  (transitionsQ.data ?? []).forEach((item) => {
    entries.push({ kind: "transition", ts: Number(item.entered_at ?? 0), data: item });
  });
  (commandsQ.data ?? []).forEach((item) => {
    entries.push({ kind: "command", ts: Number(item.requested_at ?? 0), data: item });
  });
  (eventsQ.data ?? []).forEach((item) => {
    entries.push({ kind: "event", ts: Number(item.created_at ?? 0), data: item });
  });

  entries.sort((a, b) => a.ts - b.ts);

  const timelineQueries: Array<{ section: string; query: TimelineQuery }> = [
    { section: "Transitions", query: transitionsQ },
    { section: "Commands", query: commandsQ },
    { section: "Events", query: eventsQ },
  ];
  const timelineHasErrors = timelineQueries.some(({ query }) => query.isError);

  return {
    missionQ,
    preflightQ,
    complianceQ,
    timelineQueries,
    mission: missionQ.data,
    loading,
    entries,
    timelineHasErrors,
  };
}
