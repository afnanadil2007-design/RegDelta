import { CircleCheck, CircleX } from "lucide-react";

import type { AnalystDecision } from "@/types/api";

/**
 * The analyst's mark in a leaf's shoulder. It repeats what the decision bar
 * states in words, so it is hidden from assistive technology.
 */
export function DecisionTick({ decision }: { decision: AnalystDecision }) {
  if (decision === "PENDING") return null;
  const Icon = decision === "ACCEPTED" ? CircleCheck : CircleX;
  return (
    <span key={decision} aria-hidden className="settle-in inline-flex rounded-full bg-paper">
      <Icon className="size-[18px] text-ink" strokeWidth={2.25} />
    </span>
  );
}
