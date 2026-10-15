import { Component, type ErrorInfo, type ReactNode } from "react";

import { Button } from "@/components/ui/controls";
import { Notice } from "@/components/ui/feedback";

/**
 * A page that throws while rendering shows what failed instead of unmounting
 * the whole application. The shell stays usable, so the analyst can navigate
 * away; render it with ``key={pathname}`` so a new route starts clean.
 */
export class RouteErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("RegDelta page failed to render", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <Notice
        tone="error"
        title="This page could not be shown"
        action={<Button onClick={() => window.location.reload()}>Reload the page</Button>}
      >
        {this.state.error.message || "An unexpected error stopped the page from rendering."} Other pages in
        the menu still work.
      </Notice>
    );
  }
}
