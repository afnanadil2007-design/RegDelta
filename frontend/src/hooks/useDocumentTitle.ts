import { useEffect } from "react";

/** "Circulars · RegDelta"; each route names itself for tabs and history. */
export function useDocumentTitle(title: string | null | undefined) {
  useEffect(() => {
    if (title) document.title = `${title} · RegDelta`;
  }, [title]);
}
