import { Link, useLocation } from "react-router-dom";

import { PageHeader } from "@/components/lexicon";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";

export default function NotFound() {
  const location = useLocation();
  useDocumentTitle("Page not found");
  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Page not found"
        context={
          <>
            <span className="break-words">{location.pathname}</span> is not a RegDelta address.
          </>
        }
      />
      <div className="bg-paper px-5 py-4">
        <p className="text-base text-ink">
          The menu at the top lists every page.{" "}
          <Link to="/" className="font-semibold text-ink">
            Go to the overview
          </Link>
        </p>
      </div>
    </div>
  );
}
