import { useCallback, useState } from "react";
import {
  runMissionAgent,
  type AgentResult,
  type AgentRunRequest,
  type MissionAgentId,
} from "../api/agentsApi";

export function useMissionAgent(agentId: MissionAgentId) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AgentResult | null>(null);

  const run = useCallback(
    async (payload: AgentRunRequest) => {
      setLoading(true);
      setError(null);
      try {
        const response = await runMissionAgent(agentId, payload);
        setResult(response);
        return response;
      } catch (err) {
        const message = err instanceof Error ? err.message : "Agent request failed";
        setError(message);
        throw err;
      } finally {
        setLoading(false);
      }
    },
    [agentId],
  );

  const reset = useCallback(() => {
    setResult(null);
    setError(null);
  }, []);

  return { run, loading, error, result, reset };
}
