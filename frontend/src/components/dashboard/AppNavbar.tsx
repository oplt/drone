import * as React from 'react';
import { styled } from '@mui/material/styles';
import AppBar from '@mui/material/AppBar';
import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import MuiToolbar from '@mui/material/Toolbar';
import Typography from '@mui/material/Typography';
import MenuRoundedIcon from '@mui/icons-material/MenuRounded';
import DashboardRoundedIcon from '@mui/icons-material/DashboardRounded';
import SideMenuMobile from './SideMenuMobile';
import MenuButton from './MenuButton';
import ColorModeIconDropdown from '../shared-theme/ColorModeIconDropdown';

type DashboardUser = {
  first_name?: string | null;
  last_name?: string | null;
  email: string;
} | null;

const Toolbar = styled(MuiToolbar)({
  width: '100%',
  padding: '12px 16px',
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'start',
  justifyContent: 'center',
  gap: '12px',
  flexShrink: 0,
});

export default function AppNavbar({ user }: { user: DashboardUser }) {
  const [open, setOpen] = React.useState(false);
  const displayName =
    [user?.first_name, user?.last_name].filter(Boolean).join(' ') || user?.email || 'Operator';

  const toggleDrawer = (nextOpen: boolean) => () => {
    setOpen(nextOpen);
  };

  return (
    <AppBar
      position="fixed"
      sx={{
        display: { xs: 'block', md: 'none' },
        boxShadow: 0,
        bgcolor: 'transparent',
        backgroundImage: 'none',
        top: 'var(--template-frame-height, 0px)',
      }}
    >
      <Toolbar variant="regular">
        <Stack
          direction="row"
          sx={{
            alignItems: 'center',
            width: '100%',
            gap: 1.25,
            px: 1.25,
            py: 1,
            borderRadius: 999,
            border: '1px solid',
            borderColor: 'divider',
            bgcolor: 'background.paper',
            backdropFilter: 'blur(18px)',
            boxShadow: 1,
          }}
        >
          <Stack direction="row" spacing={1.25} sx={{ alignItems: 'center', mr: 'auto', minWidth: 0 }}>
            <CustomIcon />
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="subtitle2" sx={{ color: 'text.primary' }}>
                Farm Ops Console
              </Typography>
              <Typography variant="body2" sx={{ color: 'text.secondary' }} noWrap>
                {displayName}
              </Typography>
            </Box>
          </Stack>
          <Chip size="small" label="Live" color="success" />
          <ColorModeIconDropdown />
          <MenuButton aria-label="Open menu" onClick={toggleDrawer(true)}>
            <MenuRoundedIcon />
          </MenuButton>
          <SideMenuMobile open={open} toggleDrawer={toggleDrawer} user={user} />
        </Stack>
      </Toolbar>
    </AppBar>
  );
}

export function CustomIcon() {
  return (
    <Box
      sx={{
        width: '1.85rem',
        height: '1.85rem',
        borderRadius: '12px',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        alignSelf: 'center',
        backgroundImage:
          'linear-gradient(135deg, hsla(174, 60%, 45%, 0.95) 0%, hsla(174, 70%, 22%, 0.95) 100%)',
        color: 'hsla(36, 100%, 92%, 0.9)',
        border: '1px solid hsla(174, 45%, 40%, 0.6)',
        boxShadow: 'inset 0 2px 6px rgba(255, 255, 255, 0.2)',
      }}
    >
      <DashboardRoundedIcon color="inherit" sx={{ fontSize: '1rem' }} />
    </Box>
  );
}
