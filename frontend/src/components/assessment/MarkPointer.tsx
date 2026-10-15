import { useLayoutEffect, useRef, type MutableRefObject } from "react";

import { DecisionTick } from "@/components/assessment/DecisionTick";
import { ShoulderArrow } from "@/components/lexicon";
import type { AnalystDecision } from "@/types/api";

const TRAVEL: KeyframeAnimationOptions = { duration: 180, easing: "cubic-bezier(0.16, 1, 0.3, 1)" };

function reducedMotion(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

/**
 * The shoulder arrow and decision tick for a leaf, placed by CSS rather than
 * by measuring. Rendered inline just before the first evidence mark, they are
 * absolutely positioned with no ``top``: each keeps its static position, the
 * line the mark starts on, while ``left`` moves it to the leaf's gutter
 * (the arrow) and shoulder (the tick). A layout read can catch a transient
 * frame (a full-page capture once put a measured arrow 3,900 px down for one
 * frame); the resting position here never depends on one.
 *
 * When the evidence moves, the pair travels from the line it left
 * (``travel`` remembers it per leaf): a transform animation that ends at the
 * CSS position, so even a bad reading could only make one 180 ms glide start
 * from the wrong place. Instant under reduced motion.
 */
export function MarkPointer({
  decision,
  travel,
}: {
  decision: AnalystDecision;
  travel: MutableRefObject<number | null>;
}) {
  const arrow = useRef<HTMLSpanElement>(null);
  const tick = useRef<HTMLSpanElement>(null);

  useLayoutEffect(() => {
    const element = arrow.current;
    if (!element) return;
    const top = element.offsetTop;
    const from = travel.current;
    travel.current = top;
    if (from === null || from === top || reducedMotion()) return;
    const frames = [{ transform: `translateY(${from - top}px)` }, { transform: "none" }];
    for (const node of [element, tick.current]) {
      if (node && typeof node.animate === "function") node.animate(frames, TRAVEL);
    }
  });

  return (
    <>
      {/* Centred in the 20 px gutter between the shoulder (2.25rem) and the text. */}
      <span
        ref={arrow}
        aria-hidden
        className="pointer-events-none absolute"
        style={{ left: "calc(2.25rem + 5px)", marginTop: "calc(0.5lh - 6px)" }}
      >
        <ShoulderArrow />
      </span>
      <span
        ref={tick}
        className="pointer-events-none absolute left-0"
        style={{ marginTop: "calc(0.5lh - 9px)" }}
      >
        <DecisionTick decision={decision} />
      </span>
    </>
  );
}
