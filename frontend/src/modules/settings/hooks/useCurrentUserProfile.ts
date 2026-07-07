import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchCurrentUser, getToken, updateCurrentUser } from "../../session";
import type { UserResponse, UserUpdate } from "../settingsTypes";

const CURRENT_USER_QUERY_KEY = ["me"] as const;

function toUserResponse(user: Awaited<ReturnType<typeof fetchCurrentUser>>): UserResponse {
  const fullName = [user.first_name, user.last_name].filter(Boolean).join(" ").trim();

  return {
    id: String(user.id),
    email: user.email,
    full_name: fullName || user.email,
    created_at: undefined,
    org_id: user.org_id ?? null,
  };
}

export function useCurrentUserProfile() {
  const token = getToken();
  const queryClient = useQueryClient();
  const [fullName, setFullName] = useState("");
  const [saveProfileSuccess, setSaveProfileSuccess] = useState(false);
  const [saveProfileError, setSaveProfileError] = useState<string | null>(null);

  const userQuery = useQuery<UserResponse>({
    queryKey: CURRENT_USER_QUERY_KEY,
    enabled: Boolean(token),
    queryFn: async (): Promise<UserResponse> => toUserResponse(await fetchCurrentUser()),
  });

  useEffect(() => {
    if (userQuery.data) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setFullName(userQuery.data.full_name ?? "");
    }
  }, [userQuery.data]);

  const profileMutation = useMutation({
    mutationFn: (payload: UserUpdate) => updateCurrentUser(payload, token),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: CURRENT_USER_QUERY_KEY });
      setSaveProfileSuccess(true);
      setSaveProfileError(null);
    },
    onError: (error: unknown) => {
      setSaveProfileError(error instanceof Error ? error.message : "Failed to save profile.");
      setSaveProfileSuccess(false);
    },
  });

  const saveCurrentUserProfile = () => {
    setSaveProfileSuccess(false);
    setSaveProfileError(null);
    profileMutation.mutate({ full_name: fullName.trim() });
  };

  return {
    user: userQuery.data,
    userLoading: userQuery.isLoading,
    userError: userQuery.error,
    fullName,
    setFullName,
    saveProfileSuccess,
    setSaveProfileSuccess,
    saveProfileError,
    setSaveProfileError,
    savingProfile: profileMutation.isPending,
    saveCurrentUserProfile,
  };
}
