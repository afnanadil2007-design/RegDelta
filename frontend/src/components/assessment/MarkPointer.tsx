import { DecisionTick } from "@/components/assessment/DecisionTick";
import { ShoulderArrow } from "@/components/lexicon";
import type { AnalystDecision } from "@/types/api";

/**
 * The shoulder arrow and decision tick for a leaf, placed by CSS rather than
 * by measuring. Rendered inline just before the first evidence mark, they are
 * absolutely positioned with no ``top``: each keeps its static position, the
 * line the mark starts on, while ``left`` moves it to the leaf's gutter
 * (the arrow) and shoulder (the tick). A layout read can catch a transient frame (a
 * full-page capture once put the arrow 3,900 px down for one frame); this
 * cannot.
 */
export function MarkPointer({ decision }: { decision: AnalystDecision }) {
  return (
    <>
      {/* Centred in the 20 px gutter between the shoulder (2.25rem) and the text. */}
      <span
        aria-hidden
        className="pointer-events-none absolute"
        style={{ left: "calc(2.25rem + 5px)", marginTop: "calc(0.5lh - 6px)" }}
      >
        <ShoulderArrow />
      </span>
      <span className="pointer-events-none absolute left-0" style={{ marginTop: "calc(0.5lh - 9px)" }}>
        <DecisionTick decision={decision} />
      </span>
    </>
  );
}
