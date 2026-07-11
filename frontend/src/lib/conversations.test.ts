import { describe, expect, it } from "vitest";
import type { AgentTransaction } from "../types";
import {
  loadConversationIndex,
  pendingConversation,
  rememberConversation,
  saveConversationIndex,
} from "./conversations";

function transaction(id: string, updatedAt: string, state = "APPROVAL_PENDING"): AgentTransaction {
  return {
    transaction_id: id,
    raw_request: `Buy product ${id}`,
    intent: { product_query: `Product ${id}` },
    state,
    updated_at: updatedAt,
  } as AgentTransaction;
}

describe("conversation index", () => {
  it("keeps multiple transactions ordered by most recent activity", () => {
    const first = rememberConversation([], transaction("one", "2026-07-11T10:00:00Z"));
    const both = rememberConversation(first, transaction("two", "2026-07-11T11:00:00Z"));

    expect(both.map((item) => item.transactionId)).toEqual(["two", "one"]);
  });

  it("updates an existing conversation instead of duplicating it", () => {
    const initial = rememberConversation([], transaction("one", "2026-07-11T10:00:00Z"));
    const updated = rememberConversation(
      initial,
      transaction("one", "2026-07-11T12:00:00Z", "ORDER_CONFIRMED"),
    );

    expect(updated).toHaveLength(1);
    expect(updated[0].state).toBe("ORDER_CONFIRMED");
  });

  it("round-trips the index through browser storage", () => {
    const conversations = rememberConversation([], transaction("one", "2026-07-11T10:00:00Z"));
    saveConversationIndex(conversations);

    expect(loadConversationIndex()).toEqual(conversations);
  });

  it("replaces an optimistic entry when the authoritative transaction arrives", () => {
    const optimistic = pendingConversation("pending:one", "Buy a monitor");
    const remembered = rememberConversation(
      [optimistic],
      transaction("one", "2026-07-11T10:00:00Z"),
      optimistic.transactionId,
    );

    expect(remembered.map((item) => item.transactionId)).toEqual(["one"]);
  });
});
