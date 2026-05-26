import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { sessionKeys } from "../../../app/config/queryKeys";
import { ApiError } from "../../../shared/api/apiError";
import * as sessionApi from "../api/sessionApi";
import { clearSessionMarker } from "../sessionCookies";

export function useCurrentUser() {
  const navigate = useNavigate();
  const query = useQuery({
    queryKey: sessionKeys.currentUser(),
    queryFn: ({ signal }) => sessionApi.fetchCurrentUser(signal),
    retry: false,
  });

  useEffect(() => {
    if (!(query.error instanceof ApiError)) return;
    if (query.error.status !== 401 && query.error.status !== 403) return;
    clearSessionMarker();
    navigate("/signin", { replace: true });
  }, [navigate, query.error]);

  return {
    user: query.data ?? null,
    isLoading: query.isLoading,
    isReady: query.isFetched,
    error: query.error,
    refetch: query.refetch,
  };
}
