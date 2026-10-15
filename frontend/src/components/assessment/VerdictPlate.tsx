import { Plate, QuoteStatusTag } from "@/components/lexicon";
import { IMPACT, modelScoreLabel, providerLabel } from "@/lib/labels";
import type { Finding, ProviderInfo } from "@/types/api";

/**
 * The machine's interpretation, set apart as a plate and labelled with the
 * judge that produced it. The quote check sits beside it, never inside the
 * verdict: a located quote proves the text exists, not that the reading is right.
 */
export function VerdictPlate({ finding, provider }: { finding: Finding; provider: ProviderInfo | null }) {
  const impact = IMPACT[finding.impact_type];
  const score = modelScoreLabel(finding.model_confidence, provider?.deterministic ?? false);
  return (
    <Plate tone={impact.tone} className="flex flex-col gap-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h3 className="font-serif text-xl font-bold" style={{ color: `var(--${impact.tone})` }}>
          {impact.label}
        </h3>
        <p className="text-sm text-ink">Machine interpretation · {providerLabel(provider)}</p>
      </div>
      <p className="text-sm text-ink">{impact.meaning}</p>
      <p className="max-w-measure text-md text-ink">{finding.rationale}</p>

      <dl
        className="grid gap-x-4 gap-y-2 border-t pt-3 text-sm sm:grid-cols-[auto_minmax(0,1fr)]"
        style={{ borderColor: `var(--${impact.tone})` }}
      >
        <dt className="font-semibold text-ink">Quote check</dt>
        <dd>
          <QuoteStatusTag status={finding.quote_status} detailed />
          {finding.verification_note ? <p className="mt-1 text-ink">{finding.verification_note}</p> : null}
          {finding.quote_status === "FAILED" && finding.unlocated_quote ? (
            <p className="mt-1 text-ink">
              Quoted, not found: <s className="quote-missing font-serif">“{finding.unlocated_quote}”</s>
            </p>
          ) : null}
          {finding.verification_attempts > 1 ? (
            <p className="mt-1 text-ink">Checked {finding.verification_attempts} times.</p>
          ) : null}
        </dd>
        {score ? (
          <>
            <dt className="font-semibold text-ink">Score</dt>
            <dd className="text-ink">{score}</dd>
          </>
        ) : null}
      </dl>
    </Plate>
  );
}
