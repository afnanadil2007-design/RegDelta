import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { PageHeader, SyntheticTag } from "@/components/lexicon";
import {
  isAbort,
  isMode,
  ModeControl,
  QueryField,
  SubmitOrCancel,
  searchRequest,
  useCancellableSearch,
  useElapsed,
} from "@/components/SearchForm";
import { SearchResults } from "@/components/SearchResults";
import { Field, Select } from "@/components/ui/controls";
import { EmptyState, RequestError, Skeleton } from "@/components/ui/feedback";
import { useDepartments } from "@/hooks/queries";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { queryTerms } from "@/lib/text";
import type { RetrievalMode } from "@/types/api";

/** Passage search over the whole corpus. The query, mode, and filter live in the URL. */
export default function Search() {
  useDocumentTitle("Search");
  const [params, setParams] = useSearchParams();
  const urlQuery = params.get("q") ?? "";
  const urlMode = params.get("mode");
  const urlDepartment = params.get("department") ?? "";

  const [text, setText] = useState(urlQuery);
  const [mode, setMode] = useState<RetrievalMode>(isMode(urlMode) ? urlMode : "hybrid");
  const [department, setDepartment] = useState(urlDepartment);
  const [error, setError] = useState<string | null>(null);
  const departments = useDepartments();
  const { search, run, cancel, isCurrent } = useCancellableSearch();
  const elapsed = useElapsed(search.isPending);

  // The URL describes a search: a shared, refreshed or edited link runs it.
  // A submit runs its search before writing the URL, so this sees it as
  // current and does not run it twice.
  useEffect(() => {
    if (!urlQuery.trim()) return;
    const request = searchRequest(urlQuery, isMode(urlMode) ? urlMode : "hybrid", urlDepartment);
    if (!isCurrent(request)) run(request);
  }, [run, isCurrent, urlQuery, urlMode, urlDepartment]);

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!text.trim()) {
      setError("Type what you are looking for.");
      return;
    }
    setError(null);
    const next: Record<string, string> = { q: text.trim(), mode };
    if (department) next.department = department;
    run(searchRequest(text, mode, department));
    setParams(next, { replace: true });
  };

  const result = search.data;
  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Search"
        context={
          <span className="inline-flex flex-wrap items-center gap-2">
            Find passages across every circular. Retrieval only: no model writes an answer.
            <SyntheticTag>Synthetic corpus</SyntheticTag>
          </span>
        }
      />
      <form
        role="search"
        onSubmit={submit}
        className="flex flex-col gap-4 bg-paper px-4 py-4 sm:px-6"
        noValidate
      >
        <div className="flex flex-col gap-3 md:flex-row md:items-start">
          <QueryField
            label="Search the circulars"
            hint="For example: margin collection from clients, or 2024/306"
            value={text}
            onChange={setText}
            error={error}
          />
          <Field label="Department" className="md:w-48">
            {({ id }) => (
              <Select id={id} value={department} onChange={(event) => setDepartment(event.target.value)}>
                <option value="">All departments</option>
                {(departments.data ?? []).map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        </div>
        <ModeControl mode={mode} onChange={setMode} />
        <SubmitOrCancel pending={search.isPending} elapsed={elapsed} onCancel={cancel} />
      </form>

      <section aria-label="Search results" className="flex flex-col gap-4 bg-paper px-4 py-4 sm:px-6">
        {search.isPending ? (
          <>
            <p className="text-sm text-ink-soft">
              {mode === "hybrid_rerank"
                ? "Re-scoring candidate passages with the cross-encoder: about a minute on a laptop CPU, sometimes more. Cancel stops the wait; the server still finishes this search, and asking again picks up its result."
                : "Searching."}
            </p>
            <Skeleton lines={6} label="results" />
          </>
        ) : null}
        {search.isError && !isAbort(search.error) ? (
          <RequestError
            error={search.error}
            what="results"
            onRetry={() => run(searchRequest(text || urlQuery, mode, department))}
          />
        ) : null}
        {result && !search.isPending ? (
          <SearchResults result={result} terms={queryTerms(urlQuery || text)} />
        ) : null}
        {search.isIdle && !result ? (
          <EmptyState title="Search by meaning or by number">
            Hybrid search combines meaning and exact wording and answers in well under a second. Hybrid +
            rerank reads each candidate closely and is the only mode that refuses when nothing is relevant
            enough.
          </EmptyState>
        ) : null}
      </section>
    </div>
  );
}
