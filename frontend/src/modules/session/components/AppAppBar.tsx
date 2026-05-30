import * as React from 'react';
import { alpha, styled } from '@mui/material/styles';
import Box from '@mui/material/Box';
import AppBar from '@mui/material/AppBar';
import Toolbar from '@mui/material/Toolbar';
import IconButton from '@mui/material/IconButton';
import Container from '@mui/material/Container';
import Divider from '@mui/material/Divider';
import MenuItem from '@mui/material/MenuItem';
import Drawer from '@mui/material/Drawer';
import Stack from '@mui/material/Stack';
import Tooltip from '@mui/material/Tooltip';
import MenuIcon from '@mui/icons-material/Menu';
import CloseRoundedIcon from '@mui/icons-material/CloseRounded';
import HubRoundedIcon from '@mui/icons-material/HubRounded';
import ShieldRoundedIcon from '@mui/icons-material/ShieldRounded';
import HubOutlinedIcon from '@mui/icons-material/HubOutlined';
import ContactMailOutlinedIcon from '@mui/icons-material/ContactMailOutlined';
import ColorModeIconDropdown from '../../../shared/theme/ColorModeIconDropdown';
import Sitemark from './SitemarkIcon';
import { Link as RouterLink } from "react-router-dom";
import { ActionIconButton } from '../../../shared/ui/ActionIconButton';

const navItems = [
  { label: 'Platform', href: '#platform', icon: <HubRoundedIcon fontSize="small" /> },
  { label: 'Field Safety', href: '#safety', icon: <ShieldRoundedIcon fontSize="small" /> },
  { label: 'Integrations', href: '#integration', icon: <HubOutlinedIcon fontSize="small" /> },
  { label: 'Contact', href: '#contact', icon: <ContactMailOutlinedIcon fontSize="small" /> },
];

const StyledToolbar = styled(Toolbar)(({ theme }) => ({
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  flexShrink: 0,
  minHeight: 74,
  borderRadius: `calc(${theme.shape.borderRadius}px + 8px)`,
  backdropFilter: 'blur(24px)',
  border: '1px solid',
  borderColor: (theme.vars || theme).palette.divider,
  backgroundColor: theme.vars
    ? `rgba(${theme.vars.palette.background.paperChannel} / 0.68)`
    : alpha(theme.palette.background.paper, 0.68),
  boxShadow: (theme.vars || theme).shadows[1],
  padding: '10px 14px',
}));

export default function AppAppBar() {
  const [open, setOpen] = React.useState(false);

  const toggleDrawer = (newOpen: boolean) => () => {
    setOpen(newOpen);
  };

  return (
    <AppBar
      position="fixed"
      enableColorOnDark
      sx={{
        boxShadow: 0,
        bgcolor: 'transparent',
        backgroundImage: 'none',
        mt: 'calc(var(--template-frame-height, 0px) + 28px)',
      }}
    >
      <Container maxWidth="lg">
        <StyledToolbar variant="dense" disableGutters>
          <Box sx={{ flexGrow: 1, display: 'flex', alignItems: 'center', px: 0 }}>
            <Sitemark />
            <Box sx={{ display: { xs: 'none', md: 'flex' }, gap: 0.25 }}>
              {navItems.map((item) => (
                <Tooltip key={item.label} title={item.label}>
                  <IconButton
                    size="small"
                    color="primary"
                    href={item.href}
                    aria-label={item.label}
                  >
                    {item.icon}
                  </IconButton>
                </Tooltip>
              ))}
            </Box>
          </Box>
          <Box
            sx={{
              display: { xs: 'none', md: 'flex' },
              gap: 0.25,
              alignItems: 'center',
            }}
          >
            <ActionIconButton
              variant="connect"
              title="Grower sign in"
              color="primary"
              component={RouterLink}
              to="/signin"
            />
            <ActionIconButton
              variant="add"
              title="Request onboarding"
              color="primary"
              component={RouterLink}
              to="/signup"
            />
            <ColorModeIconDropdown />
          </Box>
          <Box sx={{ display: { xs: 'flex', md: 'none' }, gap: 1 }}>
            <ColorModeIconDropdown size="medium" />
            <IconButton aria-label="Menu button" onClick={toggleDrawer(true)}>
              <MenuIcon />
            </IconButton>
            <Drawer
              anchor="top"
              open={open}
              onClose={toggleDrawer(false)}
              PaperProps={{
                sx: {
                  top: 'var(--template-frame-height, 0px)',
                },
              }}
            >
              <Box sx={{ p: 2, backgroundColor: 'background.default' }}>
                <Box
                  sx={{
                    display: 'flex',
                    justifyContent: 'flex-end',
                  }}
                >
                  <IconButton onClick={toggleDrawer(false)}>
                    <CloseRoundedIcon />
                  </IconButton>
                </Box>
                {navItems.map((item) => (
                  <MenuItem key={item.label} component="a" href={item.href} onClick={toggleDrawer(false)}>
                    {item.label}
                  </MenuItem>
                ))}
                <Divider sx={{ my: 3 }} />
                <Stack direction="row" spacing={0.5} justifyContent="center">
                  <ActionIconButton
                    variant="add"
                    title="Request onboarding"
                    color="primary"
                    component={RouterLink}
                    to="/signup"
                    onClick={toggleDrawer(false)}
                  />
                  <ActionIconButton
                    variant="connect"
                    title="Grower sign in"
                    color="primary"
                    component={RouterLink}
                    to="/signin"
                    onClick={toggleDrawer(false)}
                  />
                </Stack>
              </Box>
            </Drawer>
          </Box>
        </StyledToolbar>
      </Container>
    </AppBar>
  );
}
