import { Mono } from "@/components/ui";
import { cn } from "@/lib/utils";
import type { EvalRun } from "@/types/api";

const MODE_LABEL: Record<string, string> = {
  dense: "Dense only",
  lexical: "Lexical only",
  hybrid: "Hybrid (RRF)",
  hybrid_rerank: "Hybrid + rerank",
};

interface Row {
  mode: string;
  subset: string;
  recall5: number | null;
  recall10: number | null;
  mrr: number | null;
  gitSha: string;
}

function toRows(runs: EvalRun[]): Row[] {
  const rows: Row[] = [];
  for (const run of runs) {
    if (run.suite !== "retrieval" || !run.mode) continue;
    const subsets = new Set(run.results.map((r) => r.subset ?? "all"));
    for (const subset of subsets) {
      const pick = (name: string) =>
        run.results.find((r) => r.metric_name === name && (r.subset ?? "all") === subset)
          ?.metric_value ?? null;
      rows.push({
        mode: run.mode,
        subset,
        recall5: pick("recall@5"),
        recall10: pick("recall@10"),
        mrr: pick("mrr"),
        gitSha: run.git_sha,
      });
    }
  }
  return rows;
}

const SUBSET_ORDER = ["semantic", "identifier", "all"];
const MODE_ORDER = ["dense", "lexical", "hybrid", "hybrid_rerank"];

/**
 * The retrieval ablation. Per-subset rows are the point: a mode that wins
 * overall while collapsing on one subset is not an improvement, and only the
 * split shows it.
 */
export function AblationTable({ runs }: { runs: EvalRun[] }) {
  const rows = toRows(runs).sort(
    (a, b) =>
      MODE_ORDER.indexOf(a.mode) - MODE_ORDER.indexOf(b.mode) ||
      SUBSET_ORDER.indexOf(a.subset) - SUBSET_ORDER.indexOf(b.subset),
  );

  if (rows.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No retrieval evaluation has been run yet. Run{" "}
        <Mono>make eval</Mono> to populate this table.
      </p>
    );
  }

  const best = Math.max(...rows.filter((r) => r.subset === "all").map((r) => r.recall10 ?? 0));

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs text-muted-foreground">
            <th className="px-3 py-2 font-medium">Mode</th>
            <th className="px-3 py-2 font-medium">Subset</th>
            <th className="px-3 py-2 text-right font-medium">Recall@5</th>
            <th className="px-3 py-2 text-right font-medium">Recall@10</th>
            <th className="px-3 py-2 text-right font-medium">MRR</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={`${row.mode}-${row.subset}`}
              className={cn(
                "border-b border-border/60",
                row.subset === "all" && "bg-muted/40 font-medium",
              )}
            >
              <td className="px-3 py-2">{MODE_LABEL[row.mode] ?? row.mode}</td>
              <td className="px-3 py-2 text-muted-foreground">{row.subset}</td>
              <Metric value={row.recall5} />
              <Metric
                value={row.recall10}
                highlight={row.subset === "all" && row.recall10 === best}
              />
              <Metric value={row.mrr} />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Metric({ value, highlight }: { value: number | null; highlight?: boolean }) {
  return (
    <td
      className={cn(
        "px-3 py-2 text-right font-mono text-xs",
        highlight && "text-impact-covered",
      )}
    >
      {value === null ? "—" : value.toFixed(3)}
    </td>
  );
}
