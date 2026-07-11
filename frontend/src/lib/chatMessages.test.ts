import { beforeEach, describe, expect, it } from "vitest";
import {
  appendChatMessage,
  ensureChatMessage,
  loadChatMessages,
  moveChatMessages,
  removeChatMessages,
} from "./chatMessages";

describe("persisted chat messages", () => {
  beforeEach(() => localStorage.clear());

  it("stores every user submission as a separate message", () => {
    appendChatMessage("txn-1", "user", "Find a monitor", localStorage, "msg-1", "2026-07-11T10:00:00Z");
    appendChatMessage("txn-1", "user", "My budget is 1,200 PLN", localStorage, "msg-2", "2026-07-11T10:01:00Z");

    expect(loadChatMessages("txn-1").map((message) => message.content)).toEqual([
      "Find a monitor",
      "My budget is 1,200 PLN",
    ]);
  });

  it("moves the transcript from an optimistic id to the backend transaction id", () => {
    appendChatMessage("pending:1", "user", "Find a keyboard", localStorage, "msg-1");

    const moved = moveChatMessages("pending:1", "txn-1");

    expect(moved).toHaveLength(1);
    expect(loadChatMessages("txn-1")[0].content).toBe("Find a keyboard");
    expect(loadChatMessages("pending:1")).toEqual([]);
  });

  it("migrates legacy combined clarification requests into individual messages", () => {
    const messages = loadChatMessages(
      "txn-legacy",
      "Buy a monitor\n\nAdditional clarification: Under 1,200 PLN",
    );

    expect(messages.map((message) => message.content)).toEqual([
      "Buy a monitor",
      "Under 1,200 PLN",
    ]);
  });

  it("deduplicates persisted assistant messages and supports removal", () => {
    const clarification = {
      messageId: "clarification-1",
      role: "assistant" as const,
      content: "What is your budget?",
      createdAt: "2026-07-11T10:01:00Z",
    };
    ensureChatMessage("txn-1", clarification);
    ensureChatMessage("txn-1", clarification);
    expect(loadChatMessages("txn-1")).toHaveLength(1);

    removeChatMessages("txn-1");
    expect(loadChatMessages("txn-1")).toEqual([]);
  });
});
