import { useQuery } from "@tanstack/react-query";
import { sessionKeys } from "../../../app/config/queryKeys";
import * as sessionApi from "../api/sessionApi";

/** Lightweight session verification for route guards. */
export function useSession() {
  const query = useQuery({
    queryKey: sessionKeys.verified(),
    queryFn: () => sessionApi.verifySession(),
    staleTime: 0,
    retry: false,
  });

  return {
    isAuthenticated: query.data === true,
    isChecking: query.isLoading,
    status: query.isLoading
      ? ("checking" as const)
      : query.data
        ? ("authed" as const)
        : ("guest" as const),
    refetch: query.refetch,
  };
}
