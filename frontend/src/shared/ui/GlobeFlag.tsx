import PublicRoundedIcon from "@mui/icons-material/PublicRounded";
import Box from "@mui/material/Box";

export function GlobeFlag() {
  return (
    <Box
      sx={{
        width: 28,
        height: 28,
        borderRadius: "50%",
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        border: "1px solid",
        borderColor: "divider",
        color: "text.secondary",
        backgroundColor: "background.paper",
      }}
    >
      <PublicRoundedIcon fontSize="small" />
    </Box>
  );
}
