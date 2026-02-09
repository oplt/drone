import { Typography, Paper } from "@mui/material";
import Header from "../components/Header";


export default function TasksPage() {
  return (
    <>
      <Header />
      <Paper sx={{ width: "100%", p: 2 }}>
        <Typography variant="h4">Tasks</Typography>
        {/* components later */}
      </Paper>
    </>
  );
}
