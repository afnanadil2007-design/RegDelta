import { useId, useMemo } from "react";
import { Link, useParams } from "react-router-dom";

import { ApiRequestError } from "@/api/client";
import { GuideHead, Ident, PageHeader, Plate, SyntheticTag } from "@/components/lexicon";
import { Prose } from "@/components/Prose";
import { StartAssessment } from "@/components/StartAssessment";
import { EmptyState, RequestError, Skeleton } from "@/components/ui/feedback";
import { useCircular } from "@/hooks/queries";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { clip, isSectionHeading, numberPrefix, paragraphLabel } from "@/lib/evidence";
import { formatDate, formatDateTime, plural } from "@/lib/format";
import { toBlocks } from "@/lib/prose";
import { segmentText } from "@/lib/text";
import type { CircularDetail as Detail, Obligation, Supersession } from "@/types/api";

const EDGE_VERB: Record<Supersession["supersession_type"], string> = {
  supersedes: "supersedes",
  rescinds: "rescinds",
  amends: "amends",
  partial: "partly supersedes",
};

function Side({
  title,
  first,
  last,
  children,
}: {
  title: string;
  first?: string;
  last?: string;
  children: React.ReactNode;
}) {
  const id = useId();
  return (
    <section aria-labelledby={id} className="flex flex-col gap-3 bg-paper px-4 py-4 sm:px-5">
      <GuideHead id={id} first={first} title={title} last={last} />
      {children}
    </section>
  );
}

function ObligationEntry({ obligation, label }: { obligation: Obligation; label: string | null }) {
  const facts = [
    obligation.actor ? `Subject: ${obligation.actor}` : null,
    obligation.deadline ? `By: ${obligation.deadline}` : null,
    obligation.condition ? `When: ${obligation.condition}` : null,
  ].filter(Boolean);
  return (
    <li className="grid grid-cols-[2.25rem_minmax(0,1fr)] gap-x-2 border-b border-rule py-2 last:border-0">
      <a href={`#para-${obligation.paragraph_id}`} className="guide-words pt-0.5 text-right text-ink">
        {label ?? "¶"}
      </a>
      <div className="flex flex-col gap-1">
        <p className="font-serif text-base text-ink">{obligation.text}</p>
        {facts.length ? <p className="text-sm text-ink-soft">{facts.join(" · ")}</p> : null}
        <p className="text-xs text-ink-soft">
          Extracted by {obligation.extractor ?? "an unrecorded extractor"}
          {obligation.model_confidence !== null
            ? ` · model-stated ${obligation.model_confidence.toFixed(2)}, uncalibrated`
            : ""}
        </p>
      </div>
    </li>
  );
}

function SupersessionEntry({ edge }: { edge: Supersession }) {
  const outgoing = edge.direction === "outgoing";
  const otherId = outgoing ? edge.superseded_circular_id : edge.superseding_circular_id;
  const otherNumber = (outgoing ? edge.superseded_number : edge.superseding_number) ?? edge.raw_reference;
  const otherTitle = outgoing ? edge.superseded_title : edge.superseding_title;
  const verb = EDGE_VERB[edge.supersession_type] ?? edge.supersession_type;
  const relation = outgoing
    ? `This circular ${verb}`
    : edge.removes_from_force
      ? "Taken out of force by"
      : edge.supersession_type === "amends"
        ? "Amended by"
        : "Partly superseded by";
  return (
    <li className="flex flex-col gap-1 border-b border-rule py-2 last:border-0">
      <p className="text-sm text-ink-soft">{relation}</p>
      {otherId ? (
        <Link to={`/circulars/${otherId}`} className="font-semibold text-ink break-words">
          <Ident value={otherNumber} />
        </Link>
      ) : (
        <span className="font-semibold break-words">
          <Ident value={otherNumber} />
        </span>
      )}
      {otherTitle ? <span className="text-sm">{otherTitle}</span> : null}
      <p className="text-sm text-ink-soft">
        {edge.removes_from_force
          ? `The earlier circular is out of force from ${formatDate(edge.effective_date, "an unrecorded date")}.`
          : "The earlier circular stays in force as amended."}
        {!edge.resolved ? " The reference was not found in the corpus." : ""}
      </p>
      <Link
        to={`/point-in-time?circular=${outgoing ? edge.superseding_circular_id : (edge.superseded_circular_id ?? "")}`}
        className="text-sm text-ink"
      >
        See it on the timeline
      </Link>
    </li>
  );
}

function CircularText({ detail }: { detail: Detail }) {
  const paragraphs = useMemo(
    () => [...detail.paragraphs].sort((a, b) => a.order_index - b.order_index),
    [detail.paragraphs],
  );
  const labels = paragraphs.map(paragraphLabel).filter(Boolean) as string[];
  const headId = useId();
  return (
    <section aria-labelledby={headId} className="flex min-w-0 flex-col gap-4 bg-paper px-4 py-4 sm:px-6">
      <GuideHead id={headId} first={labels[0]} title="Text" last={labels[labels.length - 1]} />
      <p className="text-sm text-ink-soft">
        Obligations are underlined with dots. {plural(paragraphs.length, "paragraph")} extracted from{" "}
        {plural(detail.circular.page_count, "page")}
        {detail.circular.vision_page_count ? `, ${detail.circular.vision_page_count} read by OCR` : ""}.
      </p>
      <div className="grid grid-cols-[2.75rem_minmax(0,1fr)] gap-x-3">
        {paragraphs.map((paragraph) => {
          const spans = detail.obligations
            .filter((o) => o.paragraph_id === paragraph.id)
            .map((o) =>
              clip(
                { id: "obligation", start: o.char_start, end: o.char_end },
                paragraph.char_start,
                paragraph.char_end,
              ),
            )
            .filter((s): s is NonNullable<typeof s> => s !== null);
          const { segments } = segmentText(paragraph.text, paragraph.char_start, spans);
          const heading = isSectionHeading(paragraph);
          return (
            <div key={paragraph.id} id={`para-${paragraph.id}`} className="contents">
              <span className="guide-words pt-0.5 text-right text-ink-soft">{paragraphLabel(paragraph)}</span>
              <div className={heading ? "section-caps scroll-mt-20 pb-1 pt-2" : "doc-text scroll-mt-20 pb-3"}>
                {heading ? (
                  paragraph.text
                ) : (
                  <Prose
                    blocks={toBlocks(segments, {
                      stripPrefix: numberPrefix(paragraph),
                      // Front matter (letterhead, date, addressees) keeps its lines.
                      keepLines: !paragraph.para_number && !paragraph.heading_path,
                    })}
                  />
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

/** One circular: its text with obligations marked, and everything known about it. */
export default function CircularDetail() {
  const params = useParams();
  const id = Number(params.circularId);
  const valid = Number.isInteger(id) && id > 0;
  const query = useCircular(valid ? id : null);
  const detail = query.data;
  useDocumentTitle(detail?.circular.circular_number ?? "Circular");

  const paragraphLabels = useMemo(() => {
    const map = new Map<number, string | null>();
    detail?.paragraphs.forEach((p) => map.set(p.id, paragraphLabel(p)));
    return map;
  }, [detail]);

  if (!valid || (query.error instanceof ApiRequestError && query.error.status === 404)) {
    return (
      <div className="bg-paper px-5 py-4">
        <EmptyState
          title="No circular with this ID"
          action={
            <Link to="/circulars" className="font-semibold text-ink">
              Browse all circulars
            </Link>
          }
        >
          It may have been removed by a re-ingest, or the link is from another database.
        </EmptyState>
      </div>
    );
  }
  if (query.isPending) return <Skeleton lines={10} label="the circular" />;
  if (query.isError || !detail) {
    return <RequestError error={query.error} what="the circular" onRetry={() => void query.refetch()} />;
  }

  const { circular } = detail;
  const outgoing = detail.supersessions.filter((s) => s.direction === "outgoing");
  const incoming = detail.supersessions.filter((s) => s.direction === "incoming");
  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title={circular.title}
        context={
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="font-semibold text-ink break-words">
              <Ident value={circular.circular_number} />
            </span>
            <span>{circular.department ?? "No department"}</span>
            <span>Issued {formatDate(circular.issue_date)}</span>
            {circular.is_synthetic ? <SyntheticTag>Synthetic circular</SyntheticTag> : null}
          </span>
        }
        actions={
          circular.source_url && !circular.is_synthetic ? (
            <a
              href={circular.source_url}
              className="text-sm font-semibold text-ink"
              rel="noreferrer"
              target="_blank"
            >
              Source document
            </a>
          ) : undefined
        }
      />
      {incoming.some((s) => s.removes_from_force && s.resolved) ? (
        <Plate tone="conflict">
          <p className="text-base text-ink">
            <span className="font-semibold">No longer in force.</span> A later circular superseded or
            rescinded it; see the relationships below.
          </p>
        </Plate>
      ) : null}

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_360px] wide:grid-cols-[minmax(0,1fr)_420px]">
        <CircularText detail={detail} />
        <div className="flex flex-col gap-5">
          <Side title="Assess">
            <StartAssessment circularId={circular.id} obligationCount={detail.obligations.length} />
          </Side>
          <Side
            title="Obligations"
            first={detail.obligations.length ? String(detail.obligations.length) : undefined}
          >
            {detail.obligations.length === 0 ? (
              <p className="text-sm text-ink-soft">No obligation sentences were found in this circular.</p>
            ) : (
              <ol className="flex flex-col">
                {detail.obligations.map((obligation) => (
                  <ObligationEntry
                    key={obligation.id}
                    obligation={obligation}
                    label={paragraphLabels.get(obligation.paragraph_id) ?? null}
                  />
                ))}
              </ol>
            )}
          </Side>
          <Side title="Relationships">
            {detail.supersessions.length === 0 &&
            detail.citations.length === 0 &&
            detail.cited_by.length === 0 ? (
              <p className="text-sm text-ink-soft">
                This circular cites no other circular and nothing cites it.
              </p>
            ) : null}
            {outgoing.length + incoming.length > 0 ? (
              <ul className="flex flex-col">
                {[...incoming, ...outgoing].map((edge) => (
                  <SupersessionEntry key={`${edge.direction}-${edge.id}`} edge={edge} />
                ))}
              </ul>
            ) : null}
            {detail.citations.length > 0 ? (
              <div className="flex flex-col gap-1">
                <h3 className="text-sm font-semibold">Cites</h3>
                <ul className="flex flex-col gap-1.5">
                  {detail.citations.map((citation) => (
                    <li key={citation.id} className="text-sm">
                      {citation.cited_circular_id ? (
                        <Link
                          to={`/circulars/${citation.cited_circular_id}`}
                          className="font-semibold text-ink break-words"
                        >
                          <Ident value={citation.cited_circular_number} />
                        </Link>
                      ) : (
                        <span className="font-semibold break-words">
                          <Ident value={citation.raw_reference} />
                        </span>
                      )}
                      <span className="block text-ink-soft">
                        {citation.cited_circular_title ?? "Not in the corpus"}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {detail.cited_by.length > 0 ? (
              <div className="flex flex-col gap-1">
                <h3 className="text-sm font-semibold">Cited by</h3>
                <ul className="flex flex-col gap-1.5">
                  {detail.cited_by.map((citation) => (
                    <li key={citation.id} className="text-sm">
                      <Link
                        to={`/circulars/${citation.citing_circular_id}`}
                        className="font-semibold text-ink break-words"
                      >
                        <Ident value={citation.citing_circular_number} />
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </Side>
          <Side title="Provenance">
            <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1.5 text-sm">
              <dt className="text-ink-soft">File</dt>
              <dd className="break-words">{detail.provenance.pdf_filename ?? "Not recorded"}</dd>
              <dt className="text-ink-soft">SHA-256</dt>
              <dd className="break-words" title={detail.provenance.checksum ?? undefined}>
                {detail.provenance.checksum ?? "Not recorded"}
              </dd>
              <dt className="text-ink-soft">Ingested</dt>
              <dd>{formatDateTime(detail.provenance.ingested_at)}</dd>
            </dl>
          </Side>
        </div>
      </div>
    </div>
  );
}
