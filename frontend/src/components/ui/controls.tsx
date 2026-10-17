import { LoaderCircle } from "lucide-react";
import {
  forwardRef,
  useId,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactElement,
  type ReactNode,
  type SelectHTMLAttributes,
} from "react";

import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "quiet";

const BUTTON: Record<Variant, string> = {
  primary: "bg-ink text-paper border-ink hover:bg-[#2c3445] active:bg-[#0f141d]",
  secondary: "bg-raised text-ink border-ink hover:bg-paper active:bg-desk",
  quiet: "bg-transparent text-ink border-transparent hover:bg-raised active:bg-desk",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  /** Shows a spinner and blocks repeat clicks while a request is in flight. */
  busy?: boolean;
  icon?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", busy = false, icon, className, children, disabled, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type="button"
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      className={cn(
        "inline-flex min-h-9 items-center justify-center gap-2 rounded-control border px-4 py-1.5 text-base font-semibold",
        "transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-50",
        BUTTON[variant],
        className,
      )}
      {...rest}
    >
      {busy ? <LoaderCircle aria-hidden className="size-4 animate-spin" /> : icon}
      {children}
    </button>
  );
});

/** An icon-only button: always labelled, with a tooltip on hover and focus. */
export function IconButton({
  label,
  icon,
  className,
  ...rest
}: { label: string; icon: ReactElement } & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <span className="group relative inline-flex">
      <button
        type="button"
        aria-label={label}
        className={cn(
          "inline-flex size-9 items-center justify-center rounded-control text-ink transition-colors duration-150",
          "hover:bg-raised active:bg-desk disabled:opacity-40",
          className,
        )}
        {...rest}
      >
        {icon}
      </button>
      <span
        role="presentation"
        className="pointer-events-none absolute left-1/2 top-full z-30 mt-1 -translate-x-1/2 whitespace-nowrap rounded-control bg-ink px-2 py-1 text-xs font-medium text-paper opacity-0 shadow-float transition-opacity duration-150 group-hover:opacity-100 group-has-[:focus-visible]:opacity-100"
      >
        {label}
      </span>
    </span>
  );
}

interface FieldProps {
  label: string;
  hint?: ReactNode;
  error?: string | null;
  className?: string;
  children: (ids: { id: string; describedBy: string | undefined; invalid: boolean }) => ReactNode;
}

/** A visible label, the control, then hint or error text tied to it. */
export function Field({ label, hint, error, className, children }: FieldProps) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  return (
    <div className={cn("flex min-w-0 flex-col gap-1", className)}>
      <label htmlFor={id} className="text-sm font-semibold text-ink">
        {label}
      </label>
      {children({ id, describedBy, invalid: Boolean(error) })}
      {hint && !error ? (
        <p id={hintId} className="text-xs text-ink-soft">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} className="text-xs font-medium text-error">
          {error}
        </p>
      ) : null}
    </div>
  );
}

const CONTROL =
  "min-h-9 w-full rounded-control border border-ink-faint bg-raised px-3 py-1.5 text-base text-ink placeholder:text-ink-soft transition-colors duration-150 hover:border-ink aria-[invalid=true]:border-error disabled:bg-desk disabled:text-ink-soft";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input(
  { className, ...rest },
  ref,
) {
  return <input ref={ref} className={cn(CONTROL, className)} {...rest} />;
});

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cn(CONTROL, "pr-8", className)} {...rest}>
      {children}
    </select>
  );
}

/** A radio group drawn as joined buttons; arrow keys move between options. */
export function SegmentedControl<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  const name = useId();
  return (
    <fieldset className="min-w-0">
      <legend className="mb-1 text-sm font-semibold text-ink">{label}</legend>
      <div className="inline-flex flex-wrap rounded-control border border-ink-faint bg-raised p-0.5">
        {options.map((option) => (
          <label
            key={option.value}
            className={cn(
              "relative cursor-pointer rounded-[2px] px-3 py-1.5 text-sm font-semibold transition-colors duration-150",
              "has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-1 has-[:focus-visible]:outline-focus",
              value === option.value ? "bg-ink text-paper" : "text-ink hover:bg-paper",
            )}
          >
            <input
              type="radio"
              name={name}
              value={option.value}
              checked={value === option.value}
              onChange={() => onChange(option.value)}
              className="sr-only"
            />
            {option.label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
