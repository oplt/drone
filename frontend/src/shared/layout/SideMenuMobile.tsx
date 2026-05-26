import Button from '@mui/material/Button';
import Divider from '@mui/material/Divider';
import Drawer, { drawerClasses } from '@mui/material/Drawer';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import Box from '@mui/material/Box';
import LogoutRoundedIcon from '@mui/icons-material/LogoutRounded';
import MenuContent from './MenuContent';
import ColorModeIconDropdown from "../theme/ColorModeIconDropdown";
import type { ShellUser } from "./types";

type SideMenuMobileProps = {
  open: boolean | undefined;
  toggleDrawer: (newOpen: boolean) => () => void;
  user: ShellUser;
  onLogout: () => void | Promise<void>;
};

function getDisplayName(user: ShellUser) {
  return [user?.first_name, user?.last_name].filter(Boolean).join(' ') || user?.email || 'Operator';
}

function getInitials(user: ShellUser) {
  return getDisplayName(user)
    .split(/[\s@._-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part.charAt(0).toUpperCase())
    .join('');
}

export default function SideMenuMobile({ open, toggleDrawer, user, onLogout }: SideMenuMobileProps) {
  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={toggleDrawer(false)}
      sx={{
        zIndex: (theme) => theme.zIndex.drawer + 1,
        [`& .${drawerClasses.paper}`]: {
          backgroundImage: 'none',
          backgroundColor: 'background.default',
          borderLeft: '1px solid',
          borderColor: 'divider',
        },
      }}
    >
      <Stack
        sx={{
          width: { xs: '82dvw', sm: 320 },
          maxWidth: 320,
          height: '100%',
        }}
      >
        <Stack direction="row" sx={{ p: 2, pb: 1, gap: 1.5, alignItems: 'center' }}>
          <Box
            sx={{
              width: 32,
              height: 32,
              borderRadius: '50%',
              border: '1px solid',
              borderColor: 'divider',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Typography
              sx={{
                fontFamily: '"Space Mono", monospace',
                fontSize: '0.6875rem',
                fontWeight: 700,
                color: 'text.primary',
              }}
            >
              {getInitials(user)}
            </Typography>
          </Box>
          <Stack spacing={0.25} sx={{ minWidth: 0, flex: 1 }}>
            <Typography component="p" variant="subtitle2" noWrap>
              {getDisplayName(user)}
            </Typography>
            <Typography
              sx={{
                fontFamily: '"Space Mono", monospace',
                fontSize: '0.625rem',
                letterSpacing: '0.06em',
                textTransform: 'uppercase',
                color: 'text.secondary',
              }}
              noWrap
            >
              {user?.role || 'OPERATOR'}
            </Typography>
          </Stack>
          <ColorModeIconDropdown />
        </Stack>
        <Divider sx={{ borderColor: 'divider' }} />
        <Stack sx={{ flexGrow: 1 }}>
          <MenuContent userRole={user?.role ?? undefined} />
        </Stack>
        <Divider sx={{ borderColor: 'divider' }} />
        <Stack sx={{ p: 2 }}>
          <Button
            variant="outlined"
            fullWidth
            startIcon={<LogoutRoundedIcon />}
            onClick={() => void onLogout()}
            sx={{
              fontFamily: '"Space Mono", monospace',
              fontSize: '0.6875rem',
              letterSpacing: '0.06em',
              textTransform: 'uppercase',
            }}
          >
            Log out
          </Button>
        </Stack>
      </Stack>
    </Drawer>
  );
}
