import { useSearchParams } from "react-router";
import { parseDays, type Days } from "../../platform/range";

/** The usage range lives in the URL (`?days=`), so reload, share and the back button all keep it. */
export function useDays(): [Days, (days: Days) => void] {
  const [params, setParams] = useSearchParams();
  const days = parseDays(params.get("days"));
  return [days, (next) => setParams((current) => { const copy = new URLSearchParams(current); copy.set("days", String(next)); return copy; }, { replace: true })];
}
