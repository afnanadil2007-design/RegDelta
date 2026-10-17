import type { ReactNode, TdHTMLAttributes, ThHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

/**
 * A dense, rule-separated table. Wide tables scroll inside their own labelled
 * region, so the page itself never scrolls sideways.
 */
export function Table({
  label,
  children,
  minWidth,
  className,
}: {
  label: string;
  children: ReactNode;
  minWidth?: number;
  className?: string;
}) {
  return (
    <div role="region" aria-label={label} tabIndex={0} className={cn("overflow-x-auto", className)}>
      <table className="w-full border-collapse text-base" style={minWidth ? { minWidth } : undefined}>
        {children}
      </table>
    </div>
  );
}

export function Th({
  children,
  align = "left",
  className,
  ...rest
}: { align?: "left" | "right" } & ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      scope="col"
      className={cn(
        "border-b-[1.5px] border-ink px-2 py-1.5 text-sm font-semibold text-ink first:pl-0 last:pr-0",
        align === "right" ? "text-right" : "text-left",
        className,
      )}
      {...rest}
    >
      {children}
    </th>
  );
}

export function Td({
  children,
  align = "left",
  className,
  ...rest
}: { align?: "left" | "right" } & TdHTMLAttributes<HTMLTableCellElement>) {
  return (
    <td
      className={cn(
        "border-b border-rule px-2 py-2 align-top first:pl-0 last:pr-0",
        align === "right" && "text-right",
        className,
      )}
      {...rest}
    >
      {children}
    </td>
  );
}
