import { Search as SearchIcon, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button, Field, Input, SegmentedControl } from "@/components/ui/controls";
import { useSearch } from "@/hooks/queries";
import { MODE } from "@/lib/labels";
import type { RetrievalMode, SearchRequest } from "@/types/api";

export const MODES: RetrievalMode[] = ["hybrid", "hybrid_rerank", "lexical", "dense"];

/** A request this page cancelled itself; never shown as a failure. */
export function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

export function isMode(value: string | null): value is RetrievalMode {
  return value !== null && (MODES as string[]).includes(value);
}

/** Seconds since ``active`` became true, updated every 100 ms. */
export function useElapsed(active: boolean): number {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!active) return;
    const started = performance.now();
    setElapsed(0);
    const timer = window.setInterval(() => setElapsed((performance.now() - started) / 1000), 100);
    return () => window.clearInterval(timer);
  }, [active]);
  return elapsed;
}

/**
 * The search request, with cancellation. A new search aborts the one in
 * flight, so a slow reranked query can never overwrite a newer answer.
 * ``isCurrent`` says whether a request is the one this page last ran and did
 * not abandon, so a page can run its URL's search exactly when it needs to.
 */
export function useCancellableSearch() {
  const search = useSearch();
  const { mutate, reset } = search;
  const controller = useRef<AbortController | null>(null);
  const current = useRef<string | null>(null);
  const run = useCallback(
    (body: SearchRequest) => {
      controller.current?.abort();
      controller.current = new AbortController();
      current.current = JSON.stringify(body);
      mutate({ body, signal: controller.current.signal });
    },
    [mutate],
  );
  const cancel = useCallback(() => {
    controller.current?.abort();
    controller.current = null;
    reset();
  }, [reset]);
  const isCurrent = useCallback((body: SearchRequest) => current.current === JSON.stringify(body), []);
  // Leaving the page abandons the request. React may also unmount and
  // remount a page that stays (StrictMode does so on purpose); forgetting
  // the request lets the remounted page run it again instead of waiting on
  // an answer that was aborted.
  useEffect(
    () => () => {
      controller.current?.abort();
      current.current = null;
    },
    [],
  );
  return { search, run, cancel, isCurrent };
}

/** The request a query, mode and department filter describe. */
export function searchRequest(query: string, mode: RetrievalMode, department: string): SearchRequest {
  return { query: query.trim(), mode, department: department || null };
}

export function QueryField({
  value,
  onChange,
  label,
  hint,
  error,
}: {
  value: string;
  onChange: (value: string) => void;
  label: string;
  hint: string;
  error?: string | null;
}) {
  return (
    <Field label={label} hint={hint} error={error} className="flex-1">
      {({ id, describedBy, invalid }) => (
        <Input
          id={id}
          type="search"
          value={value}
          maxLength={2000}
          aria-invalid={invalid}
          aria-describedby={describedBy}
          onChange={(event) => onChange(event.target.value)}
          autoComplete="off"
        />
      )}
    </Field>
  );
}

export function ModeControl({
  mode,
  onChange,
}: {
  mode: RetrievalMode;
  onChange: (mode: RetrievalMode) => void;
}) {
  return (
    <div className="flex flex-col gap-1">
      <SegmentedControl
        label="Retrieval"
        value={mode}
        options={MODES.map((value) => ({ value, label: MODE[value].label }))}
        onChange={onChange}
      />
      <p className="max-w-measure text-sm text-ink-soft">{MODE[mode].note}</p>
    </div>
  );
}

export function SubmitOrCancel({
  pending,
  elapsed,
  onCancel,
  label = "Search",
}: {
  pending: boolean;
  elapsed: number;
  onCancel: () => void;
  label?: string;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <Button
        type="submit"
        variant="primary"
        busy={pending}
        icon={<SearchIcon aria-hidden className="size-4" />}
      >
        {pending ? "Searching" : label}
      </Button>
      {pending ? (
        <>
          <Button variant="quiet" icon={<X aria-hidden className="size-4" />} onClick={onCancel}>
            Cancel
          </Button>
          <span className="text-sm text-ink-soft" aria-live="off">
            {elapsed.toFixed(1)} s
          </span>
        </>
      ) : null}
    </div>
  );
}
