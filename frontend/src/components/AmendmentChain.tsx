import { Link } from "react-router-dom";

import { Mono } from "@/components/ui";
import type { Supersession } from "@/types/api";

/**
 * Horizontal supersession graph for one circular: what it replaced, and what
 * replaced it. Each edge carries the date it took effect, which is the same
 * date the point-in-time filter uses.
 */
export function AmendmentChain({
  circularId,
  circularNumber,
  edges,
}: {
  circularId: number;
  circularNumber: string;
  edges: Supersession[];
}) {
  const replaces = edges.filter((e) => e.superseding_circular_id === circularId);
  const replacedBy = edges.filter((e) => e.superseded_circular_id === circularId);

  if (replaces.length === 0 && replacedBy.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No supersession relationships found for this circular.
      </p>
    );
  }

  return (
    <div className="flex items-stretch gap-3 overflow-x-auto pb-2">
      <Column title="Supersedes" tone="muted">
        {replaces.map((e) => (
          <Node
            key={e.id}
            id={e.superseded_circular_id}
            label={e.superseded_number}
            meta={`${e.supersession_type}${e.effective_date ? ` · ${e.effective_date}` : ""}`}
          />
        ))}
        {replaces.length === 0 && <Nothing />}
      </Column>

      <Arrow />

      <Column title="This circular" tone="current">
        <div className="rounded-md border border-ring bg-accent/60 px-3 py-2">
          <Mono className="block">{circularNumber}</Mono>
        </div>
      </Column>

      <Arrow />

      <Column title="Superseded by" tone="muted">
        {replacedBy.map((e) => (
          <Node
            key={e.id}
            id={e.superseding_circular_id}
            label={e.superseding_number}
            meta={`${e.supersession_type}${e.effective_date ? ` · ${e.effective_date}` : ""}`}
          />
        ))}
        {replacedBy.length === 0 && <Nothing />}
      </Column>
    </div>
  );
}

function Column({
  title,
  children,
}: {
  title: string;
  tone: "muted" | "current";
  children: React.ReactNode;
}) {
  return (
    <div className="min-w-[220px] flex-1">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
        {title}
      </div>
      <div className="space-y-2">{children}</div>
    </div>
  );
}

function Node({
  id,
  label,
  meta,
}: {
  id: number | null;
  label: string | null;
  meta: string;
}) {
  const body = (
    <div className="rounded-md border border-border bg-card px-3 py-2 hover:border-ring">
      <Mono className="block truncate">{label ?? "unresolved"}</Mono>
      <span className="text-[11px] text-muted-foreground">{meta}</span>
    </div>
  );
  return id ? <Link to={`/circulars/${id}`}>{body}</Link> : body;
}

function Nothing() {
  return (
    <div className="rounded-md border border-dashed border-border px-3 py-2 text-xs text-muted-foreground">
      None
    </div>
  );
}

function Arrow() {
  return (
    <div className="flex items-center px-1 text-muted-foreground" aria-hidden>
      →
    </div>
  );
}
