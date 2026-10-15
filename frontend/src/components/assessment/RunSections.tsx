import { ChevronDown } from "lucide-react";

import { TracePanel } from "@/components/assessment/TracePanel";
import { Prose } from "@/components/Prose";
import { RequestError } from "@/components/ui/feedback";
import { providerLabel } from "@/lib/labels";
import { toBlocks } from "@/lib/prose";
import { cn } from "@/lib/utils";
import type { AgentStep, AssessmentDetail } from "@/types/api";

function SectionHead({ id, title, children }: { id: string; title: string; children?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b-[1.5px] border-ink pb-1.5">
      <h2 id={id} className="font-serif text-md font-bold">
        {title}
      </h2>
      {children}
    </div>
  );
}

/** The run's memo, attributed to the judge that wrote it. */
export function MemoSection({ run, inProgress }: { run: AssessmentDetail; inProgress: boolean }) {
  return (
    <section aria-labelledby="memo-head" className="flex flex-col gap-3 bg-paper px-4 py-4 sm:px-6">
      <SectionHead id="memo-head" title="Memo">
        <p className="text-sm text-ink-soft">Written by {providerLabel(run.provider)}</p>
      </SectionHead>
      {run.memo ? (
        <Prose
          blocks={toBlocks([{ text: run.memo, spanId: null }], { keepLines: true })}
          className="doc-text"
        />
      ) : (
        <p className="text-base text-ink-soft">
          {inProgress
            ? "The memo is written after every obligation has been assessed."
            : "No memo was produced for this run."}
        </p>
      )}
    </section>
  );
}

/** The technical trace, secondary to the evidence: collapsed unless a run is live. */
export function TraceSection({
  steps,
  live,
  open,
  onToggle,
  error,
  onRetry,
}: {
  steps: AgentStep[];
  live: boolean;
  open: boolean;
  onToggle: () => void;
  error: unknown;
  onRetry: () => void;
}) {
  return (
    <section aria-labelledby="trace-head" className="flex flex-col gap-3 bg-paper px-4 py-4 sm:px-6">
      <SectionHead id="trace-head" title="Agent trace">
        <button
          type="button"
          aria-expanded={open}
          aria-controls="trace-body"
          onClick={onToggle}
          className="inline-flex items-center gap-1 rounded-control px-2 py-1 text-sm font-semibold text-ink hover:bg-raised"
        >
          {open ? "Hide steps" : `Show ${steps.length} steps`}
          <ChevronDown
            aria-hidden
            className={cn("size-4 transition-transform duration-150", open && "rotate-180")}
          />
        </button>
      </SectionHead>
      <div id="trace-body" hidden={!open}>
        {error ? (
          <RequestError error={error} what="the trace" onRetry={onRetry} />
        ) : (
          <TracePanel steps={steps} live={live} />
        )}
      </div>
    </section>
  );
}
