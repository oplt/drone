import { styled } from "@mui/material/styles";
import Typography from "@mui/material/Typography";
import Breadcrumbs, { breadcrumbsClasses } from "@mui/material/Breadcrumbs";
import NavigateNextRoundedIcon from "@mui/icons-material/NavigateNextRounded";
import Link from "@mui/material/Link";
import { Link as RouterLink, useLocation } from "react-router-dom";
import { buildBreadcrumbTrail } from "./breadcrumbTrail";

const StyledBreadcrumbs = styled(Breadcrumbs)(({ theme }) => ({
  margin: theme.spacing(1, 0),
  [`& .${breadcrumbsClasses.separator}`]: {
    color: (theme.vars || theme).palette.action.disabled,
    margin: 1,
  },
  [`& .${breadcrumbsClasses.ol}`]: {
    alignItems: "center",
  },
}));

type NavbarBreadcrumbsProps = {
  /** Limit visible crumbs (mobile overflow menus may pass maxItems). */
  maxItems?: number;
};

export default function NavbarBreadcrumbs({ maxItems }: NavbarBreadcrumbsProps) {
  const { pathname } = useLocation();
  const crumbs = buildBreadcrumbTrail(pathname);

  return (
    <StyledBreadcrumbs
      aria-label="breadcrumb"
      maxItems={maxItems}
      separator={<NavigateNextRoundedIcon fontSize="small" />}
    >
      {crumbs.map((crumb) =>
        crumb.current ? (
          <Typography
            key={crumb.to}
            variant="body1"
            sx={{ color: "text.primary", fontWeight: 500 }}
          >
            {crumb.label}
          </Typography>
        ) : (
          <Link
            key={crumb.to}
            component={RouterLink}
            to={crumb.to}
            underline="hover"
            color="inherit"
            variant="body1"
          >
            {crumb.label}
          </Link>
        ),
      )}
    </StyledBreadcrumbs>
  );
}
