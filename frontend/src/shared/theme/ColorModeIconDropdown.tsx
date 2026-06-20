import IconButton from "@mui/material/IconButton";
import type { IconButtonOwnProps } from "@mui/material/IconButton";
import DarkModeIcon from "@mui/icons-material/DarkModeRounded";
import LightModeIcon from "@mui/icons-material/LightModeRounded";
import Box from "@mui/material/Box";
import { useColorScheme } from "@mui/material/styles";

export default function ColorModeIconDropdown(props: IconButtonOwnProps) {
  const { mode, systemMode, setMode } = useColorScheme();

  if (!mode) {
    return (
      <Box
        data-screenshot="toggle-mode"
        sx={(theme) => ({
          verticalAlign: "bottom",
          display: "inline-flex",
          width: "2.25rem",
          height: "2.25rem",
          borderRadius: (theme.vars || theme).shape.borderRadius,
          border: "1px solid",
          borderColor: (theme.vars || theme).palette.divider,
        })}
      />
    );
  }

  const resolvedMode = ((mode === "system" ? systemMode : mode) ?? "light") as
    | "light"
    | "dark";
  const icon = {
    light: <LightModeIcon />,
    dark: <DarkModeIcon />,
  }[resolvedMode];

  const handleToggle = () => {
    setMode(resolvedMode === "light" ? "dark" : "light");
  };

  return (
    <IconButton
      data-screenshot="toggle-mode"
      onClick={handleToggle}
      disableRipple
      size="small"
      aria-label={`Switch to ${resolvedMode === "light" ? "dark" : "light"} mode`}
      {...props}
    >
      {icon}
    </IconButton>
  );
}
