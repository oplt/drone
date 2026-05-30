import { useState } from 'react';
import Box from '@mui/material/Box';
import { ActionIconButton } from "../ui/ActionIconButton";
import Divider from '@mui/material/Divider';
import IconButton from '@mui/material/IconButton';
import MuiDrawer, { drawerClasses } from '@mui/material/Drawer';
import Stack from '@mui/material/Stack';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import ChevronLeftRoundedIcon from '@mui/icons-material/ChevronLeftRounded';
import ChevronRightRoundedIcon from '@mui/icons-material/ChevronRightRounded';
import MenuContent from './MenuContent';
import ColorModeIconDropdown from "../theme/ColorModeIconDropdown";
import type { ShellUser } from "./types";

const expandedDrawerWidth = 260;
const collapsedDrawerWidth = 72;

function getDisplayName(user: ShellUser) {
  return [user?.first_name, user?.last_name].filter(Boolean).join(' ') || user?.email || 'Operator';
}

function getInitials(user: ShellUser) {
  const displayName = getDisplayName(user);
  return displayName
    .split(/[\s@._-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part.charAt(0).toUpperCase())
    .join('');
}

type SideMenuProps = {
  user: ShellUser;
  onLogout: () => void | Promise<void>;
};

export default function SideMenu({ user, onLogout }: SideMenuProps) {
  const [collapsed, setCollapsed] = useState(false);
  const drawerWidth = collapsed ? collapsedDrawerWidth : expandedDrawerWidth;

  return (
    <MuiDrawer
      variant="permanent"
      sx={(theme) => ({
        display: { xs: 'none', md: 'block' },
        width: drawerWidth,
        flexShrink: 0,
        whiteSpace: 'nowrap',
        transition: theme.transitions.create('width', {
          duration: 200,
          easing: 'cubic-bezier(0.25, 0.1, 0.25, 1)',
        }),
        [`& .${drawerClasses.paper}`]: {
          backgroundColor: 'background.default',
          width: drawerWidth,
          overflowX: 'hidden',
          boxSizing: 'border-box',
          borderRight: '1px solid',
          borderColor: 'divider',
          transition: theme.transitions.create('width', {
            duration: 200,
            easing: 'cubic-bezier(0.25, 0.1, 0.25, 1)',
          }),
        },
      })}
    >
      <Box sx={{ p: 2 }}>
        <Stack
          direction="row"
          sx={{
            gap: 1,
            alignItems: 'center',
            justifyContent: collapsed ? 'center' : 'space-between',
          }}
        >
          {!collapsed ? (
            <Stack direction="row" sx={{ gap: 1.5, alignItems: 'center', minWidth: 0 }}>
              <Box
                sx={{
                  width: 36,
                  height: 36,
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
                    fontSize: '0.75rem',
                    fontWeight: 700,
                    color: 'text.primary',
                  }}
                >
                  {getInitials(user)}
                </Typography>
              </Box>
              <Box sx={{ minWidth: 0 }}>
                <Typography
                  variant="body2"
                  sx={{ fontWeight: 500, lineHeight: '18px', color: 'text.primary' }}
                  noWrap
                >
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
              </Box>
            </Stack>
          ) : (
            <Box
              sx={{
                width: 36,
                height: 36,
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
                  fontSize: '0.75rem',
                  fontWeight: 700,
                  color: 'text.primary',
                }}
              >
                {getInitials(user)}
              </Typography>
            </Box>
          )}
          <Tooltip title={collapsed ? 'Expand menu' : 'Collapse menu'} placement="right">
            <IconButton
              size="small"
              onClick={() => setCollapsed((prev) => !prev)}
              aria-label={collapsed ? 'Expand sidebar menu' : 'Collapse sidebar menu'}
              sx={{ border: 'none', '&:hover': { border: 'none' } }}
            >
              {collapsed ? (
                <ChevronRightRoundedIcon fontSize="small" />
              ) : (
                <ChevronLeftRoundedIcon fontSize="small" />
              )}
            </IconButton>
          </Tooltip>
        </Stack>
      </Box>
      <Divider sx={{ borderColor: 'divider' }} />
      <Box
        sx={{
          overflow: 'auto',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <MenuContent collapsed={collapsed} userRole={user?.role ?? undefined} />
        <Box sx={{ mt: 'auto', p: 1.5, display: 'flex', flexDirection: 'column', gap: 1 }}>
          <ColorModeIconDropdown />
          <ActionIconButton
            variant="logout"
            title="Log out"
            onClick={() => void onLogout()}
          />
        </Box>
      </Box>
    </MuiDrawer>
  );
}
