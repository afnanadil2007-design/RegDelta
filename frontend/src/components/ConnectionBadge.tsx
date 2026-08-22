import { useHealth } from "@/hooks/useHealth";
import { cn } from "@/lib/utils";

/** Live backend/database status pill. Never a bare spinner. */
export function ConnectionBadge() {
  const { data, isLoading, isError } = useHealth();

  const state = isLoading
    ? { label: "connecting", tone: "bg-muted text-muted-foreground" }
    : isError
      ? { label: "api offline", tone: "bg-impact-conflict/10 text-impact-conflict" }
      : data?.database === "up"
        ? { label: "db connected", tone: "bg-impact-covered/10 text-impact-covered" }
        : { label: "db down", tone: "bg-impact-modified/10 text-impact-modified" };

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 font-mono text-xs",
        state.tone,
      )}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {state.label}
    </span>
  );
}
