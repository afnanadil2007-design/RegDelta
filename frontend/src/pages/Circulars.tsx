import { useState } from "react";
import { Link } from "react-router-dom";

import { Card, EmptyState, ErrorState, Mono, PageHeader, SkeletonRows } from "@/components/ui";
import { useCirculars, useDepartments } from "@/hooks/queries";

export default function Circulars() {
  const [department, setDepartment] = useState<string | null>(null);
  const circulars = useCirculars(department);
  const departments = useDepartments();

  return (
    <div className="px-8 py-6">
      <PageHeader
        title="Circulars"
        description="The ingested corpus. Open a circular to see its obligations and amendment chain."
        actions={
          <select
            value={department ?? ""}
            onChange={(e) => setDepartment(e.target.value || null)}
            className="rounded-md border border-border bg-card px-2 py-1.5 text-sm"
          >
            <option value="">All departments</option>
            {departments.data?.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        }
      />

      {circulars.isLoading ? (
        <SkeletonRows rows={10} />
      ) : circulars.isError ? (
        <ErrorState what="circulars" error={circulars.error} onRetry={circulars.refetch} />
      ) : !circulars.data?.length ? (
        <EmptyState
          title="No circulars match this filter"
          hint={
            department
              ? "Try clearing the department filter."
              : "Run `make seed` to build the demo corpus."
          }
        />
      ) : (
        <Card>
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs text-muted-foreground">
                <th className="px-4 py-2 font-medium">Reference</th>
                <th className="px-4 py-2 font-medium">Title</th>
                <th className="px-4 py-2 font-medium">Dept</th>
                <th className="px-4 py-2 font-medium">Issued</th>
                <th className="px-4 py-2 text-right font-medium">Pages</th>
              </tr>
            </thead>
            <tbody>
              {circulars.data.map((circular) => (
                <tr key={circular.id} className="border-b border-border/60 hover:bg-muted/40">
                  <td className="px-4 py-2">
                    <Link
                      to={`/circulars/${circular.id}`}
                      className="hover:underline"
                    >
                      <Mono>{circular.circular_number}</Mono>
                    </Link>
                  </td>
                  <td className="max-w-md px-4 py-2">
                    <span className="line-clamp-1">{circular.title}</span>
                  </td>
                  <td className="px-4 py-2 text-xs text-muted-foreground">
                    {circular.department ?? "—"}
                  </td>
                  <td className="px-4 py-2 text-xs text-muted-foreground">
                    {circular.issue_date ?? "—"}
                  </td>
                  <td className="px-4 py-2 text-right">
                    <Mono className="text-muted-foreground">
                      {circular.page_count}
                      {circular.vision_page_count > 0 && (
                        <span title="pages extracted via the vision fallback">
                          {" "}
                          ({circular.vision_page_count}v)
                        </span>
                      )}
                    </Mono>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
