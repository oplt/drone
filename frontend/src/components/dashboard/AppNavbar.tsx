import * as React from 'react';
import { styled } from '@mui/material/styles';
import AppBar from '@mui/material/AppBar';
import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import MuiToolbar from '@mui/material/Toolbar';
import Typography from '@mui/material/Typography';
import MenuRoundedIcon from '@mui/icons-material/MenuRounded';
import SideMenuMobile from './SideMenuMobile';
import MenuButton from './MenuButton';

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
            border: '1px solid',
            borderColor: 'divider',
            bgcolor: 'background.default',
          }}
        >
          <Typography
            sx={{
              fontFamily: '"Space Mono", monospace',
              fontSize: '0.75rem',
              fontWeight: 700,
              letterSpacing: '0.06em',
              textTransform: 'uppercase',
              color: 'text.primary',
              mr: 'auto',
            }}
          >
            DRONE OPS
          </Typography>
          <Chip size="small" label="LIVE" color="success" />
          <MenuButton aria-label="Open menu" onClick={toggleDrawer(true)}>
            <MenuRoundedIcon />
          </MenuButton>
          <SideMenuMobile open={open} toggleDrawer={toggleDrawer} user={user} />
        </Stack>
      </Toolbar>
    </AppBar>
  );
}
