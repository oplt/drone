import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo, useState } from "react";
import { missionKeys } from "../../../app/config/queryKeys";
import { getSessionMarker } from "../../session";
import {
  fetchMissionCommandAudit,
  fetchMissionStateTransitions,
  sendMissionCommand,
} from "../api/missionsApi";
import { fetchOpsHealth } from "../api/telemetryApi";
import { buildMissionTimeline } from "../lib/missionTimeline";
import type {
  MissionCommand,
  MissionCommandAuditResponse,
  MissionStateTransitionResponse,
  MissionStatusPayload,
  OpsHealthResponse,
} from "../types";

function buildIdempotencyKey(flightId: string | null, command: MissionCommand): string {
  const randomPart =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}_${Math.random().toString(16).slice(2)}`;
  return `${flightId ?? "mission"}_${command}_${randomPart}`.slice(0, 120);
}

export function useMissionCommands({
  flightId,
  missionStatus,
}: {
  flightId: string | null;
  missionStatus?: MissionStatusPayload | null;
}) {
  const token = getSessionMarker();
  const queryClient = useQueryClient();
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const lifecycleState = missionStatus?.mission_lifecycle?.state ?? null;

  const capabilities = useMemo(() => {
    const caps = missionStatus?.command_capabilities;
    if (caps) {
      return {
        pause: Boolean(caps.pause),
        resume: Boolean(caps.resume),
        abort: Boolean(caps.abort),
      };
    }
    return {
      pause: lifecycleState === "running",
      resume: lifecycleState === "paused",
      abort:
        lifecycleState === "queued" ||
        lifecycleState === "running" ||
        lifecycleState === "paused",
    };
  }, [lifecycleState, missionStatus?.command_capabilities]);

  const auditQuery = useQuery({
    queryKey: missionKeys.commandAudit(flightId ?? "none"),
    queryFn: () => fetchMissionCommandAudit(flightId!, token),
    enabled: Boolean(flightId && token),
    refetchInterval: 12_000,
  });

  const transitionsQuery = useQuery({
    queryKey: missionKeys.transitions(flightId ?? "none"),
    queryFn: () => fetchMissionStateTransitions(flightId!, token),
    enabled: Boolean(flightId && token),
    refetchInterval: 12_000,
  });

  const opsHealthQuery = useQuery({
    queryKey: missionKeys.opsHealth(),
    queryFn: () => fetchOpsHealth(token),
    enabled: Boolean(token),
    refetchInterval: 12_000,
  });

  const commandMutation = useMutation({
    mutationFn: async (command: MissionCommand) => {
      if (!flightId) throw new Error("No active mission selected.");
      if (!token) throw new Error("Not authenticated.");
      return sendMissionCommand(flightId, command, buildIdempotencyKey(flightId, command), null, token);
    },
    onSuccess: async (result) => {
      setMessage(result.message || `Command '${result.command}' accepted.`);
      setError(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: missionKeys.commandAudit(flightId!) }),
        queryClient.invalidateQueries({ queryKey: missionKeys.transitions(flightId!) }),
        queryClient.invalidateQueries({ queryKey: missionKeys.opsHealth() }),
      ]);
    },
    onError: (mutationError) => {
      setError(mutationError instanceof Error ? mutationError.message : "Command request failed");
    },
  });

  const issueCommand = useCallback(
    async (command: MissionCommand) => {
      setMessage(null);
      setError(null);
      await commandMutation.mutateAsync(command);
    },
    [commandMutation],
  );

  const recentAudit = useMemo(
    () =>
      [...(auditQuery.data ?? [])]
        .sort((a, b) => b.requested_at - a.requested_at)
        .slice(0, 8),
    [auditQuery.data],
  );

  const recentTimeline = useMemo(
    () => buildMissionTimeline(auditQuery.data ?? [], transitionsQuery.data ?? []),
    [auditQuery.data, transitionsQuery.data],
  );

  return {
    issueCommand,
    busyCommand: commandMutation.isPending
      ? (commandMutation.variables as MissionCommand | undefined) ?? null
      : null,
    message,
    error,
    capabilities,
    audit: auditQuery.data ?? [],
    recentAudit,
    transitions: transitionsQuery.data ?? [],
    recentTimeline,
    opsHealth: opsHealthQuery.data ?? null,
    auditLoading: auditQuery.isLoading,
    auditError: auditQuery.error instanceof Error ? auditQuery.error.message : null,
    timelineError:
      transitionsQuery.error instanceof Error ? transitionsQuery.error.message : null,
    opsError: opsHealthQuery.error instanceof Error ? opsHealthQuery.error.message : null,
  };
}

export type { MissionCommandAuditResponse, MissionStateTransitionResponse, OpsHealthResponse };
