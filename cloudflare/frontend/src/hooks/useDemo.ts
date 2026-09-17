import { useQuery } from "@tanstack/react-query";
import { demoApi } from "../api/demoApi";

export const useDemo = () => useQuery({ queryKey: ["demo"], queryFn: demoApi.summary, staleTime: Infinity });
export const useDemoGrids = () => useQuery({ queryKey: ["demo", "grids"], queryFn: demoApi.grids, staleTime: Infinity });
export const useGridDetail = (gridId: string | null) => useQuery({ queryKey: ["demo", "grid", gridId], queryFn: () => demoApi.grid(gridId!), enabled: Boolean(gridId), staleTime: Infinity });
export const useGridActions = (gridId: string | null, enabled: boolean) => useQuery({
  queryKey: ["actions", "grid", gridId],
  queryFn: () => demoApi.actionsForGrid(gridId!),
  enabled: Boolean(gridId) && enabled,
  staleTime: Infinity,
});
