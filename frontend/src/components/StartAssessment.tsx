import { Play } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ApiRequestError, errorMessage } from "@/api/client";
import { Button, Field, Select } from "@/components/ui/controls";
import { Notice } from "@/components/ui/feedback";
import { useHealth, usePolicyPacks, useStartAssessment } from "@/hooks/queries";
import { providerLabel } from "@/lib/labels";

function runningRunId(error: unknown): string | null {
  if (!(error instanceof ApiRequestError) || error.code !== "assessment_in_progress") return null;
  const detail = error.detail as { run_id?: unknown } | undefined;
  return typeof detail?.run_id === "string" ? detail.run_id : null;
}

/** Start an assessment of one circular against a chosen policy manual. */
export function StartAssessment({
  circularId,
  obligationCount,
}: {
  circularId: number;
  obligationCount: number;
}) {
  const navigate = useNavigate();
  const packs = usePolicyPacks();
  const health = useHealth();
  const start = useStartAssessment();
  const [packId, setPackId] = useState<number | null>(null);

  useEffect(() => {
    if (packId === null && packs.data?.length) setPackId(packs.data[0].id);
  }, [packs.data, packId]);

  const provider = health.data?.provider;
  const unavailable = provider && !provider.ready ? provider.reason : null;
  const running = runningRunId(start.error);
  const startUnavailable =
    start.error instanceof ApiRequestError && start.error.code === "provider_unavailable";

  const submit = () => {
    if (packId === null) return;
    start.mutate(
      { circular_id: circularId, policy_pack_id: packId },
      { onSuccess: ({ run_id }) => navigate(`/assessments/${run_id}`) },
    );
  };

  return (
    <div className="flex flex-col gap-3">
      {packs.data && packs.data.length === 0 ? (
        <Notice tone="unavailable" title="No policy manual is loaded">
          Build the demo database with <span className="font-semibold">make seed</span>, then reload this
          page.
        </Notice>
      ) : (
        <Field
          label="Compare with"
          hint={
            packs.isError
              ? undefined
              : `${obligationCount} obligations will be judged against this manual${
                  packs.data?.find((p) => p.id === packId)?.is_synthetic ? " (a fictional one)" : ""
                }.`
          }
          error={packs.isError ? `The manuals could not be loaded. ${errorMessage(packs.error)}` : null}
        >
          {({ id, describedBy, invalid }) => (
            <Select
              id={id}
              aria-describedby={describedBy}
              aria-invalid={invalid}
              value={packId ?? ""}
              disabled={!packs.data}
              onChange={(event) => setPackId(Number(event.target.value))}
            >
              {!packs.data ? <option value="">Loading manuals…</option> : null}
              {(packs.data ?? []).map((pack) => (
                <option key={pack.id} value={pack.id}>
                  {pack.name} v{pack.version}
                </option>
              ))}
            </Select>
          )}
        </Field>
      )}
      {provider ? <p className="text-sm text-ink-soft">Judged by {providerLabel(provider)}.</p> : null}
      {unavailable ? (
        <Notice tone="unavailable" title="Assessments are unavailable">
          {unavailable}
        </Notice>
      ) : null}
      <div>
        <Button
          variant="primary"
          busy={start.isPending}
          disabled={packId === null || Boolean(unavailable) || obligationCount === 0}
          icon={<Play aria-hidden className="size-4" />}
          onClick={submit}
        >
          {start.isPending ? "Starting" : "Start assessment"}
        </Button>
      </div>
      {obligationCount === 0 ? (
        <p className="text-sm text-ink-soft">
          No obligations were extracted from this circular, so there is nothing to assess.
        </p>
      ) : null}
      {running ? (
        <Notice
          tone="info"
          title="This comparison is already running"
          action={
            <Link to={`/assessments/${running}`} className="font-semibold text-ink">
              Open it
            </Link>
          }
        >
          Only one run per circular and manual can be in progress. Follow the running one instead.
        </Notice>
      ) : start.isError ? (
        <Notice
          tone={startUnavailable ? "unavailable" : "error"}
          title={startUnavailable ? "Assessments are unavailable" : "The assessment did not start"}
          action={startUnavailable ? undefined : <Button onClick={submit}>Try again</Button>}
        >
          {errorMessage(start.error)}
        </Notice>
      ) : null}
    </div>
  );
}
