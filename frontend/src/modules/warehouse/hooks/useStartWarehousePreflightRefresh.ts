import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  refreshWarehousePreflight,
  type WarehousePreflightRefresh,
} from "../api/warehousePreflightApi";

export function useStartWarehousePreflightRefresh(token: string | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationKey: ["warehouse-preflight-refresh", token],
    mutationFn: (options: {
      missionLoaded?: boolean;
      deep?: boolean;
      force?: boolean;
      freshVehicleProbe?: boolean;
    }) => {
      if (!token) throw new Error("Missing auth token");
      return refreshWarehousePreflight(token, options);
    },
    onSuccess: (run: WarehousePreflightRefresh) => {
      queryClient.setQueryData(["warehouse-preflight-run", run.run_id], run);
    },
  });
}
