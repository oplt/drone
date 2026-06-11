import * as React from 'react';
import { styled } from '@mui/material/styles';
import AppBar from '@mui/material/AppBar';
import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import MuiToolbar from '@mui/material/Toolbar';
import Typography from '@mui/material/Typography';
import MenuRoundedIcon from '@mui/icons-material/MenuRounded';
import SideMenuMobile from './SideMenuMobile';
import MenuButton from './MenuButton';

import type { ShellUser } from "./types";

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

type AppNavbarProps = {
  user: ShellUser;
  onLogout: () => void | Promise<void>;
};

export default function AppNavbar({ user, onLogout }: AppNavbarProps) {
  const [open, setOpen] = React.useState(false);

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
            gap: 1.5,
            px: 2,
            py: 1,
            bgcolor: 'background.paper',
            backdropFilter: 'blur(8px)',
          }}
        >
          <Typography
            sx={{
              fontSize: '0.875rem',
              fontWeight: 500,
              letterSpacing: '0.12em',
              color: 'text.primary',
              mr: 'auto',
            }}
          >
            drone ops
          </Typography>
          <Chip size="small" label="Live" color="primary" />
          <MenuButton aria-label="Open menu" onClick={toggleDrawer(true)}>
            <MenuRoundedIcon />
          </MenuButton>
          <SideMenuMobile open={open} toggleDrawer={toggleDrawer} user={user} onLogout={onLogout} />
        </Stack>
      </Toolbar>
    </AppBar>
  );
}
