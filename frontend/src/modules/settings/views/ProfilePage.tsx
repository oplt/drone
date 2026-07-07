import Alert from "@mui/material/Alert";
import Avatar from "@mui/material/Avatar";
import Box from "@mui/material/Box";
import { ActionIconButton } from "../../../shared/ui/ActionIconButton";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import Grid from "@mui/material/Grid";
import { useCurrentUserProfile } from "../hooks/useCurrentUserProfile";

export default function ProfilePage() {
  const {
    user,
    userLoading,
    userError,
    fullName,
    setFullName,
    saveProfileSuccess,
    setSaveProfileSuccess,
    saveProfileError,
    setSaveProfileError,
    savingProfile,
    saveCurrentUserProfile,
  } = useCurrentUserProfile();

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
            <ActionIconButton
              variant="upgrade"
              title={savingProfile ? "Saving…" : "Save profile"}
              color="primary"
              loading={savingProfile}
              disabled={savingProfile || !fullName.trim() || !user}
              onClick={saveCurrentUserProfile}
            />
          </Box>
        </Stack>
      </Grid>
    </Grid>
  );
}
