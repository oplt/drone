import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { httpRequest } from "../../shared/api/httpClient";

export type AgricultureAlert = {
  id: number;
  severity: string;
  status: string;
  title: string;
  message: string;
  source: string;
  occurrences: number;
  last_triggered_at: string;
  assigned_to_user_id?: number | null;
  due_at?: string | null;
};

type AlertPage = { items: AgricultureAlert[]; total: number };

export function useAgricultureAlerts(status: "active" | "all" = "active") {
  return useQuery({
    queryKey: ["agriculture", "alerts", status],
    queryFn: () => httpRequest<AlertPage>(`/api/alerts?status=${status}&limit=50`),
    refetchInterval: 15_000,
  });
}

export function useAgricultureAlertActions() {
  const client = useQueryClient();
  const mutation = useMutation({
    mutationFn: ({ id, action }: { id: number; action: "ack" | "resolve" }) =>
      httpRequest<AgricultureAlert>(`/api/alerts/${id}/${action}`, { method: "POST" }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["agriculture", "alerts"] });
    },
  });
  return mutation;
}

export function useAssignAgricultureAlert() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, assigned_to_user_id, due_at }: { id: number; assigned_to_user_id?: number | null; due_at?: string | null }) => httpRequest<AgricultureAlert>(`/api/alerts/${id}/assignment`, { method: "PUT", body: { assigned_to_user_id, due_at } }),
    onSuccess: () => { void client.invalidateQueries({ queryKey: ["agriculture", "alerts"] }); },
  });
}
