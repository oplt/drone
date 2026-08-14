export function deviceStatusColor(
  status: string,
): "success" | "error" | "warning" | "default" {
  if (status === "airworthy") return "success";
  if (status === "grounded") return "error";
  if (status === "limited") return "warning";
  return "default";
}
