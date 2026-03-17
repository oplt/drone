import Avatar from '@mui/material/Avatar';
import Button from '@mui/material/Button';
import Divider from '@mui/material/Divider';
import Drawer, { drawerClasses } from '@mui/material/Drawer';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import LogoutRoundedIcon from '@mui/icons-material/LogoutRounded';
import NotificationsRoundedIcon from '@mui/icons-material/NotificationsRounded';
import MenuButton from './MenuButton';
import MenuContent from './MenuContent';
import { clearToken } from '../../auth';
import { useNavigate } from 'react-router-dom';

type DashboardUser = {
  first_name?: string | null;
  last_name?: string | null;
  email: string;
} | null;

interface SideMenuMobileProps {
  open: boolean | undefined;
  toggleDrawer: (newOpen: boolean) => () => void;
  user: DashboardUser;
}

function getDisplayName(user: DashboardUser) {
  return [user?.first_name, user?.last_name].filter(Boolean).join(' ') || user?.email || 'Operator';
}

export default function SideMenuMobile({ open, toggleDrawer, user }: SideMenuMobileProps) {
  const navigate = useNavigate();

  const handleLogout = () => {
    clearToken();
    navigate('/signin', { replace: true });
  };

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={toggleDrawer(false)}
      sx={{
        zIndex: (theme) => theme.zIndex.drawer + 1,
        [`& .${drawerClasses.paper}`]: {
          backgroundImage: 'none',
          backgroundColor: 'background.paper',
        },
      }}
    >
      <Stack
        sx={{
          width: { xs: '82dvw', sm: 360 },
          maxWidth: 360,
          height: '100%',
        }}
      >
        <Stack direction="row" sx={{ p: 2, pb: 1, gap: 1.25 }}>
          <Stack
            direction="row"
            sx={{ gap: 1.25, alignItems: 'center', flexGrow: 1, p: 1 }}
          >
            <Avatar sx={{ width: 34, height: 34 }}>
              {getDisplayName(user)
                .split(/[\s@._-]+/)
                .filter(Boolean)
                .slice(0, 2)
                .map((part) => part.charAt(0).toUpperCase())
                .join('')}
            </Avatar>
            <Stack spacing={0.25} sx={{ minWidth: 0 }}>
              <Typography component="p" variant="subtitle2" noWrap>
                {getDisplayName(user)}
              </Typography>
              <Typography variant="body2" color="text.secondary" noWrap>
                {user?.email || 'Farm session'}
              </Typography>
            </Stack>
          </Stack>
          <MenuButton showBadge>
            <NotificationsRoundedIcon />
          </MenuButton>
        </Stack>
        <Divider />
        <Stack sx={{ flexGrow: 1 }}>
          <MenuContent />
          <Divider />
        </Stack>
        <Stack sx={{ p: 2 }}>
          <Button
            variant="outlined"
            fullWidth
            startIcon={<LogoutRoundedIcon />}
            onClick={handleLogout}
          >
            Log out
          </Button>
        </Stack>
      </Stack>
    </Drawer>
  );
}
