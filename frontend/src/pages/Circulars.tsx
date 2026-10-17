import { X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { ApiRequestError } from "@/api/client";
import { Ident, PageHeader, SyntheticTag } from "@/components/lexicon";
import { Pager } from "@/components/Pager";
import { Button, Field, Input, Select } from "@/components/ui/controls";
import { EmptyState, RequestError, Skeleton } from "@/components/ui/feedback";
import { Table, Td, Th } from "@/components/ui/table";
import { useCirculars, useDepartments } from "@/hooks/queries";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { formatDate, formatInteger, plural } from "@/lib/format";
import type { CircularSummary } from "@/types/api";

const LIMIT = 50;

function NumberCell({ circular }: { circular: CircularSummary }) {
  return (
    <Link to={`/circulars/${circular.id}`} className="font-semibold text-ink">
      <Ident value={circular.circular_number} />
    </Link>
  );
}

/** The corpus index: filter by text, department, and issue date; every filter is in the URL. */
export default function Circulars() {
  useDocumentTitle("Circulars");
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const department = params.get("department") ?? "";
  const dateFrom = params.get("from") ?? "";
  const dateTo = params.get("to") ?? "";
  const offset = Math.max(0, Number(params.get("offset")) || 0);

  const set = useCallback(
    (changes: Record<string, string | null>) =>
      setParams(
        (current) => {
          const next = new URLSearchParams(current);
          for (const [key, value] of Object.entries(changes)) {
            if (value) next.set(key, value);
            else next.delete(key);
          }
          if (!("offset" in changes)) next.delete("offset");
          return next;
        },
        { replace: true },
      ),
    [setParams],
  );

  // Typing updates the URL after a pause, so each keystroke is not a request.
  const [text, setText] = useState(q);
  useEffect(() => setText(q), [q]);
  useEffect(() => {
    if (text === q) return;
    const timer = window.setTimeout(() => set({ q: text.trim() ? text : null }), 300);
    return () => window.clearTimeout(timer);
  }, [text, q, set]);

  const rangeError = dateFrom && dateTo && dateFrom > dateTo ? "The start date is after the end date." : null;
  const circulars = useCirculars({
    q: q.trim() || undefined,
    department: department || undefined,
    date_from: rangeError ? undefined : dateFrom || undefined,
    date_to: rangeError ? undefined : dateTo || undefined,
    limit: LIMIT,
    offset,
  });
  const departments = useDepartments();

  const filtered = Boolean(q.trim() || department || dateFrom || dateTo);
  const data = circulars.data;
  const serverRangeError =
    circulars.error instanceof ApiRequestError && circulars.error.code === "invalid_date_range"
      ? circulars.error.message
      : null;

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Circulars"
        context={
          <span className="inline-flex flex-wrap items-center gap-2">
            Every ingested circular, newest first.
            <SyntheticTag>Synthetic corpus</SyntheticTag>
          </span>
        }
      />

      <form
        role="search"
        aria-label="Filter circulars"
        onSubmit={(event) => {
          event.preventDefault();
          set({ q: text.trim() || null });
        }}
        className="grid gap-3 bg-paper px-4 py-4 sm:grid-cols-2 sm:px-6 lg:grid-cols-[minmax(0,2fr)_minmax(10.5rem,1fr)_minmax(0,1fr)_minmax(0,1fr)_auto] lg:items-start"
      >
        <Field label="Number or title" hint="For example 2024/306 or margin">
          {({ id, describedBy }) => (
            <Input
              id={id}
              type="search"
              value={text}
              aria-describedby={describedBy}
              onChange={(event) => setText(event.target.value)}
              autoComplete="off"
            />
          )}
        </Field>
        <Field label="Department">
          {({ id }) => (
            <Select
              id={id}
              value={department}
              onChange={(event) => set({ department: event.target.value || null })}
            >
              <option value="">All departments</option>
              {(departments.data ?? []).map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label="Issued from" error={rangeError ?? serverRangeError}>
          {({ id, describedBy, invalid }) => (
            <Input
              id={id}
              type="date"
              value={dateFrom}
              aria-invalid={invalid}
              aria-describedby={describedBy}
              onChange={(event) => set({ from: event.target.value || null })}
            />
          )}
        </Field>
        <Field label="Issued to">
          {({ id }) => (
            <Input
              id={id}
              type="date"
              value={dateTo}
              onChange={(event) => set({ to: event.target.value || null })}
            />
          )}
        </Field>
        <div className="flex items-end sm:col-span-2 lg:col-span-1 lg:pt-[1.375rem]">
          <Button
            variant="quiet"
            disabled={!filtered}
            icon={<X aria-hidden className="size-4" />}
            onClick={() => {
              setText("");
              setParams({}, { replace: true });
            }}
          >
            Clear filters
          </Button>
        </div>
      </form>

      <section aria-label="Circular list" className="flex flex-col gap-4 bg-paper px-4 py-4 sm:px-6">
        {circulars.isPending ? <Skeleton lines={8} label="circulars" /> : null}
        {circulars.isError && !serverRangeError ? (
          <RequestError error={circulars.error} what="circulars" onRetry={() => void circulars.refetch()} />
        ) : null}
        {data && data.total === 0 ? (
          <EmptyState
            title={filtered ? "No circular matches these filters" : "No circulars have been ingested"}
            action={
              filtered ? (
                <Button
                  onClick={() => {
                    setText("");
                    setParams({}, { replace: true });
                  }}
                >
                  Clear filters
                </Button>
              ) : undefined
            }
          >
            {filtered
              ? "Try part of the number (such as 2024/306), a single word of the title, or a wider date range."
              : "Build the demo database with make seed (it generates and ingests the synthetic corpus), then reload this page."}
          </EmptyState>
        ) : null}
        {data && data.total > 0 ? (
          <>
            <p className="text-sm text-ink-soft" aria-live="polite">
              {filtered ? `${plural(data.total, "circular")} match` : `${plural(data.total, "circular")}`}
              {circulars.isPlaceholderData ? " · updating" : ""}
            </p>
            <Table label="Circulars" className="hidden md:block">
              <thead>
                <tr>
                  <Th>Number</Th>
                  <Th>Title</Th>
                  <Th>Department</Th>
                  <Th>Issued</Th>
                  <Th align="right">Obligations</Th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((circular) => (
                  <tr key={circular.id}>
                    <Td className="w-[30%]">
                      <NumberCell circular={circular} />
                    </Td>
                    <Td>{circular.title}</Td>
                    <Td>{circular.department ?? "—"}</Td>
                    <Td className="whitespace-nowrap">{formatDate(circular.issue_date)}</Td>
                    <Td align="right">{formatInteger(circular.obligation_count)}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
            <ul aria-label="Circulars" className="flex flex-col md:hidden">
              {data.items.map((circular) => (
                <li key={circular.id} className="flex flex-col gap-0.5 border-b border-rule py-3 first:pt-0">
                  <NumberCell circular={circular} />
                  <span>{circular.title}</span>
                  <span className="text-sm text-ink-soft">
                    {circular.department ?? "No department"} · {formatDate(circular.issue_date)} ·{" "}
                    {plural(circular.obligation_count, "obligation")}
                  </span>
                </li>
              ))}
            </ul>
            <Pager
              offset={offset}
              limit={LIMIT}
              total={data.total}
              noun="circulars"
              onChange={(next) => set({ offset: next ? String(next) : null })}
            />
          </>
        ) : null}
      </section>
    </div>
  );
}
