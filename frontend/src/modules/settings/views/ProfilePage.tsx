import { useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Avatar from "@mui/material/Avatar";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import Grid from "@mui/material/Grid";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchCurrentUser, getToken, updateCurrentUser } from "../../session";

type UserResponse = {
  id: string;
  email: string;
  full_name: string | null;
  created_at?: string;
};

type UserUpdate = {
  full_name?: string;
};

export default function ProfilePage() {
  const token = getToken();
  const queryClient = useQueryClient();
  const [fullName, setFullName] = useState("");
  const [saveProfileSuccess, setSaveProfileSuccess] = useState(false);
  const [saveProfileError, setSaveProfileError] = useState<string | null>(null);

  const { data: user, isLoading: userLoading, error: userError } = useQuery<UserResponse>({
    queryKey: ["me"],
    enabled: Boolean(token),
    queryFn: async (): Promise<UserResponse> => {
      const user = await fetchCurrentUser();
      const fullName = [user.first_name, user.last_name].filter(Boolean).join(" ").trim();
      return {
        id: String(user.id),
        email: user.email,
        full_name: fullName || user.email,
      };
    },
  });

  useEffect(() => {
    if (user) {
      setFullName(user.full_name ?? "");
    }
  }, [user]);

  const profileMutation = useMutation({
    mutationFn: (payload: UserUpdate) => updateCurrentUser(payload, token),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["me"] });
      setSaveProfileSuccess(true);
      setSaveProfileError(null);
    },
    onError: (error: unknown) => {
      setSaveProfileError(error instanceof Error ? error.message : "Failed to save profile.");
      setSaveProfileSuccess(false);
    },
  });

  const handleSaveProfile = () => {
    setSaveProfileSuccess(false);
    setSaveProfileError(null);
    profileMutation.mutate({ full_name: fullName.trim() });
  };

  return (
    <Grid container spacing={3}>
      <Grid size={{ xs: 12, md: 4 }}>
        <Stack alignItems="center" spacing={2}>
          {userLoading ? (
            <Skeleton variant="circular" width={80} height={80} />
          ) : (
            <Avatar sx={{ width: 80, height: 80, bgcolor: "primary.main", fontSize: 28, fontWeight: 700 }}>
              {(user?.full_name ?? user?.email ?? "?")
                .split(/\s+/)
                .filter(Boolean)
                .slice(0, 2)
                .map((part) => part[0]?.toUpperCase() ?? "")
                .join("")}
            </Avatar>
          )}
          <Typography variant="body2" color="text.secondary">
            {user?.created_at ? `Member since ${new Date(user.created_at).toLocaleDateString()}` : "Profile details"}
          </Typography>
        </Stack>
      </Grid>
      <Grid size={{ xs: 12, md: 8 }}>
        <Stack spacing={2.5}>
          {userError ? (
            <Alert severity="error">Failed to load profile. Refresh page.</Alert>
          ) : null}
          {saveProfileSuccess ? (
            <Alert severity="success" onClose={() => setSaveProfileSuccess(false)}>
              Profile updated successfully.
            </Alert>
          ) : null}
          {saveProfileError ? (
            <Alert severity="error" onClose={() => setSaveProfileError(null)}>
              {saveProfileError}
            </Alert>
          ) : null}
          <TextField
            variant="filled"
            fullWidth
            label="Full name"
            value={fullName}
            onChange={(event) => setFullName(event.target.value)}
            disabled={userLoading || !user}
          />
          <TextField
            variant="filled"
            fullWidth
            label="Email"
            value={user?.email ?? ""}
            disabled
          />
          <Box>
            <Button
              variant="contained"
              onClick={handleSaveProfile}
              disabled={profileMutation.isPending || !fullName.trim() || !user}
            >
              {profileMutation.isPending ? "Saving..." : "Save profile"}
            </Button>
          </Box>
        </Stack>
      </Grid>
    </Grid>
  );
}
