import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { AmendmentChain } from "@/components/AmendmentChain";
import { CitationChip } from "@/components/CitationChip";
import { ObligationCard } from "@/components/ObligationCard";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  Mono,
  PageHeader,
  SkeletonRows,
} from "@/components/ui";
import { useCircular, usePolicyPacks, useStartAssessment } from "@/hooks/queries";

export default function CircularDetail() {
  const { circularId } = useParams<{ circularId: string }>();
  const id = circularId ? Number(circularId) : null;
  const navigate = useNavigate();

  const detail = useCircular(id);
  const packs = usePolicyPacks();
  const startAssessment = useStartAssessment();
  const [selectedObligation, setSelectedObligation] = useState<number | null>(null);

  if (detail.isLoading) {
    return (
      <div className="px-8 py-6">
        <SkeletonRows rows={8} />
      </div>
    );
  }
  if (detail.isError || !detail.data) {
    return (
      <div className="px-8 py-6">
        <ErrorState what="this circular" error={detail.error} onRetry={detail.refetch} />
      </div>
    );
  }

  const { circular, paragraphs, obligations, citations, supersessions } = detail.data;
  const paragraphById = new Map(paragraphs.map((p) => [p.id, p]));

  const run = async () => {
    const packId = packs.data?.[0]?.id;
    if (!packId || id === null) return;
    const { run_id } = await startAssessment.mutateAsync({
      circular_id: id,
      policy_pack_id: packId,
    });
    navigate(`/assessments/${run_id}`);
  };

  return (
    <div className="px-8 py-6">
      <PageHeader
        title={circular.title}
        description={`${circular.department ?? "—"} · issued ${circular.issue_date ?? "unknown"}`}
        actions={
          <Button
            variant="primary"
            onClick={run}
            disabled={startAssessment.isPending || !packs.data?.length}
          >
            {startAssessment.isPending ? "Starting…" : "Run new assessment"}
          </Button>
        }
      />

      <Mono className="mb-1 block text-muted-foreground">{circular.circular_number}</Mono>
      <p className="mb-6 text-xs text-muted-foreground">
        Each run creates a new assessment with its own run ID and agent trace; previous
        runs are kept as history.
      </p>

      {startAssessment.isError && (
        <div className="mb-4">
          <ErrorState what="the assessment" error={startAssessment.error} />
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[1.1fr_1fr]">
        <section>
          <h2 className="mb-2 text-sm font-semibold">
            Obligations{" "}
            <span className="font-normal text-muted-foreground">({obligations.length})</span>
          </h2>
          {obligations.length === 0 ? (
            <EmptyState
              title="No obligations extracted"
              hint="Run `python -m ingestion.extract_obligations` to populate them."
            />
          ) : (
            <div className="space-y-2">
              {obligations.map((obligation) => (
                <ObligationCard
                  key={obligation.id}
                  obligation={obligation}
                  paragraph={paragraphs.find(
                    (p) =>
                      p.char_start <= obligation.char_start &&
                      obligation.char_end <= p.char_end,
                  )}
                  selected={selectedObligation === obligation.id}
                  onSelect={() =>
                    setSelectedObligation(
                      selectedObligation === obligation.id ? null : obligation.id,
                    )
                  }
                />
              ))}
            </div>
          )}
        </section>

        <div className="space-y-6">
          <section>
            <h2 className="mb-2 text-sm font-semibold">Amendment chain</h2>
            <Card className="p-4">
              <AmendmentChain
                circularId={circular.id}
                circularNumber={circular.circular_number}
                edges={supersessions}
              />
            </Card>
          </section>

          <section>
            <h2 className="mb-2 text-sm font-semibold">
              References{" "}
              <span className="font-normal text-muted-foreground">({citations.length})</span>
            </h2>
            {citations.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                This circular cites no other circulars.
              </p>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {citations.map((citation) => (
                  <CitationChip key={citation.id} citation={citation} />
                ))}
              </div>
            )}
          </section>

          <section>
            <h2 className="mb-2 text-sm font-semibold">
              Source text{" "}
              <span className="font-normal text-muted-foreground">
                ({paragraphs.length} paragraphs)
              </span>
            </h2>
            <Card className="max-h-[26rem] overflow-y-auto p-4">
              <div className="space-y-3">
                {paragraphs.map((paragraph) => (
                  <div key={paragraph.id}>
                    <div className="mb-0.5 flex items-center gap-2 text-[10px] text-muted-foreground">
                      <Mono>
                        {paragraph.char_start}–{paragraph.char_end}
                      </Mono>
                      {paragraph.extraction_method === "vision" && (
                        <span className="rounded bg-impact-modified/10 px-1 text-impact-modified">
                          vision
                        </span>
                      )}
                      {paragraph.page_number && <span>p{paragraph.page_number}</span>}
                    </div>
                    <p className="whitespace-pre-wrap text-[13px] leading-relaxed">
                      {paragraph.text}
                    </p>
                  </div>
                ))}
              </div>
            </Card>
            <p className="mt-1 text-[11px] text-muted-foreground">
              Paragraph offsets index <Mono>circulars.full_text</Mono>; every span in
              this app resolves against it.
            </p>
          </section>
        </div>
      </div>

      {paragraphById.size === 0 && <SkeletonRows rows={2} />}
    </div>
  );
}
