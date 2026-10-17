import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Prose } from "@/components/Prose";
import { toBlocks } from "@/lib/prose";

describe("Prose", () => {
  it("lets a circular number wrap after its slashes without changing the text", () => {
    const text = "Summary: 7 findings for SEBI/HO/MIRSD/MIRSD_Div1/P/CIR/2024/306 and/or 01/02/2024.";
    const { container } = render(<Prose blocks={toBlocks([{ text, spanId: null }])} />);

    // Evidence offsets are code points into this text, so it must be unchanged.
    expect(container.textContent).toBe(text);
    // One break opportunity after each of the identifier's seven slashes; none
    // in "and/or" or the date.
    expect(container.querySelectorAll("wbr")).toHaveLength(7);
  });
});
