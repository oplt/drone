import { useState } from 'react';
import Avatar from '@mui/material/Avatar';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Divider from '@mui/material/Divider';
import IconButton from '@mui/material/IconButton';
import MuiDrawer, { drawerClasses } from '@mui/material/Drawer';
import Stack from '@mui/material/Stack';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import LogoutRoundedIcon from '@mui/icons-material/LogoutRounded';
import ChevronLeftRoundedIcon from '@mui/icons-material/ChevronLeftRounded';
import ChevronRightRoundedIcon from '@mui/icons-material/ChevronRightRounded';
import MenuContent from './MenuContent';
import { clearToken } from '../../auth';
import { useNavigate } from 'react-router-dom';

type DashboardUser = {
  first_name?: string | null;
  last_name?: string | null;
  email: string;
} | null;

const expandedDrawerWidth = 280;
const collapsedDrawerWidth = 84;

function getDisplayName(user: DashboardUser) {
  return [user?.first_name, user?.last_name].filter(Boolean).join(' ') || user?.email || 'Field Manager';
}

function getInitials(user: DashboardUser) {
  const displayName = getDisplayName(user);
  return displayName
    .split(/[\s@._-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part.charAt(0).toUpperCase())
    .join('');
}

export default function SideMenu({ user }: { user: DashboardUser }) {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const drawerWidth = collapsed ? collapsedDrawerWidth : expandedDrawerWidth;

  const handleLogout = () => {
    clearToken();
    navigate('/signin', { replace: true });
  };

  return (
    <MuiDrawer
      variant="permanent"
      sx={(theme) => ({
        display: { xs: 'none', md: 'block' },
        width: drawerWidth,
        flexShrink: 0,
        whiteSpace: 'nowrap',
        transition: theme.transitions.create('width', {
          duration: theme.transitions.duration.standard,
          easing: theme.transitions.easing.sharp,
        }),
        [`& .${drawerClasses.paper}`]: {
          backgroundColor: 'background.paper',
          width: drawerWidth,
          overflowX: 'hidden',
          boxSizing: 'border-box',
          borderRight: '1px solid',
          borderColor: 'divider',
          transition: theme.transitions.create('width', {
            duration: theme.transitions.duration.standard,
            easing: theme.transitions.easing.sharp,
          }),
        },
      })}
    >
      <Box
        sx={{
          mt: 'calc(var(--template-frame-height, 0px) + 8px)',
          p: 1.25,
        }}
      >
        <Stack
          spacing={1.5}
          sx={{
            p: 1.5,
            borderRadius: 4,
            border: '1px solid',
            borderColor: 'divider',
            background:
              'linear-gradient(160deg, rgba(255,255,255,0.82), rgba(242,249,246,0.78))',
            '[data-mui-color-scheme="dark"] &': {
              background:
                'linear-gradient(160deg, rgba(15,20,24,0.92), rgba(17,29,27,0.88))',
              borderColor: 'rgba(122, 160, 145, 0.18)',
            },
          }}
        >
          <Stack
            direction="row"
            sx={{
              gap: 1.25,
              alignItems: 'center',
              justifyContent: collapsed ? 'center' : 'space-between',
            }}
          >
            {!collapsed ? (
              <Stack direction="row" sx={{ gap: 1.25, alignItems: 'center', minWidth: 0 }}>
                <Avatar sx={{ width: 42, height: 42 }}>{getInitials(user)}</Avatar>
                <Box sx={{ minWidth: 0 }}>
                  <Typography variant="body2" sx={{ fontWeight: 600, lineHeight: '18px' }} noWrap>
                    {getDisplayName(user)}
                  </Typography>
                  <Typography variant="body2" sx={{ color: 'text.secondary' }} noWrap>
                    {user?.email || 'Farm session'}
                  </Typography>
                </Box>
              </Stack>
            ) : (
              <Avatar sx={{ width: 42, height: 42 }}>{getInitials(user)}</Avatar>
            )}
            <Tooltip title={collapsed ? 'Expand menu' : 'Collapse menu'} placement="right">
              <IconButton
                size="small"
                onClick={() => setCollapsed((prev) => !prev)}
                aria-label={collapsed ? 'Expand sidebar menu' : 'Collapse sidebar menu'}
              >
                {collapsed ? (
                  <ChevronRightRoundedIcon fontSize="small" />
                ) : (
                  <ChevronLeftRoundedIcon fontSize="small" />
                )}
              </IconButton>
            </Tooltip>
          </Stack>
          {!collapsed ? (
            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
              Live operations, fleet telemetry, and route planning in one workspace.
            </Typography>
          ) : null}
        </Stack>
      </Box>
      <Divider />
      <Box
        sx={{
          overflow: 'auto',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <MenuContent collapsed={collapsed} />
        <Box sx={{ mt: 'auto', p: 1.25 }}>
          <Button
            variant={collapsed ? 'outlined' : 'text'}
            color="inherit"
            fullWidth
            startIcon={collapsed ? undefined : <LogoutRoundedIcon />}
            onClick={handleLogout}
            sx={{ justifyContent: collapsed ? 'center' : 'flex-start' }}
          >
            {collapsed ? <LogoutRoundedIcon fontSize="small" /> : 'Log out'}
          </Button>
        </Box>
      </Box>
    </MuiDrawer>
  );
}
