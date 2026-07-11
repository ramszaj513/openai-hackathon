import { describe, expect, it } from "vitest";
import { formatMoney, sentenceCase } from "./format";

describe("presentation formatting", () => {
  it("formats integer minor units without doing floating-point domain calculations", () => {
    expect(formatMoney(119900, "PLN")).toContain("1,199.00");
    expect(formatMoney(119900, "PLN")).toContain("PLN");
  });

  it("turns machine states into readable labels", () => {
    expect(sentenceCase("PAYMENT_CAPTURED")).toBe("Payment captured");
  });
});
