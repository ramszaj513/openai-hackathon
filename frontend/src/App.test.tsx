import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { api } from "./lib/api";
import { CONVERSATION_INDEX_KEY } from "./lib/conversations";
import type { AgentTransaction } from "./types";

vi.mock("./lib/api", () => ({
  APIError: class APIError extends Error {},
  api: {
    health: vi.fn().mockResolvedValue(true),
    getTransaction: vi.fn(),
    getOrder: vi.fn(),
    getPayment: vi.fn(),
    events: vi.fn().mockResolvedValue([]),
    start: vi.fn(),
  },
}));

describe("single-chat commerce experience", () => {
  beforeEach(() => localStorage.clear());

  it("starts with one conversational composer and the canonical demo shortcut", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "What can I take care of?" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Message the commerce agent" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /try the demo request/i })).toBeInTheDocument();
  });

  it("grows the composer with multiline input and caps its height", () => {
    render(<App />);
    const composer = screen.getByRole("textbox", { name: "Message the commerce agent" });
    Object.defineProperty(composer, "scrollHeight", { configurable: true, value: 220 });

    fireEvent.change(composer, { target: { value: "A long\nmultiline\npurchase request" } });

    expect(composer).toHaveStyle({ height: "160px", overflowY: "auto" });
  });

  it("renders every saved conversation in the sidebar", () => {
    localStorage.setItem(
      CONVERSATION_INDEX_KEY,
      JSON.stringify([
        { transactionId: "txn-monitor", title: "Mac monitor", state: "APPROVAL_PENDING", updatedAt: "2026-07-11T12:00:00Z" },
        { transactionId: "txn-keyboard", title: "Mechanical keyboard", state: "ORDER_CONFIRMED", updatedAt: "2026-07-11T11:00:00Z" },
      ]),
    );

    render(<App />);

    expect(screen.getByRole("button", { name: /mac monitor/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /mechanical keyboard/i })).toBeInTheDocument();
  });

  it("allows a new conversation while a request is pending without letting the late response take over", async () => {
    let resolveStart!: (transaction: AgentTransaction) => void;
    vi.mocked(api.start).mockReturnValue(
      new Promise((resolve) => {
        resolveStart = resolve;
      }),
    );
    render(<App />);
    fireEvent.change(screen.getByRole("textbox", { name: "Message the commerce agent" }), {
      target: { value: "Find a standing desk" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));

    expect(screen.getByRole("button", { name: /find a standing desk/i })).toBeDisabled();
    const newTransaction = screen.getByRole("button", { name: /new transaction/i });
    expect(newTransaction).toBeEnabled();
    fireEvent.click(newTransaction);

    await act(async () => {
      resolveStart({
        transaction_id: "txn-desk",
        raw_request: "Find a standing desk",
        intent: { product_query: "Standing desk" },
        state: "APPROVAL_PENDING",
        updated_at: "2026-07-11T13:00:00Z",
      } as AgentTransaction);
    });

    await waitFor(() => expect(screen.getByRole("button", { name: /standing desk/i })).toBeEnabled());
    expect(screen.getByRole("heading", { name: "What can I take care of?" })).toBeInTheDocument();
  });

  it("keeps the composer available for a clarification reply", async () => {
    const clarification = {
      transaction_id: "txn-clarify",
      user_id: "user-1",
      agent_id: "agent-1",
      raw_request: "Buy a monitor",
      state: "CLARIFICATION_REQUIRED",
      intent: {
        product_query: "monitor",
        clarification_questions: ["What is your maximum budget?"],
      },
      transitions: [],
      updated_at: "2026-07-11T13:00:00Z",
    } as unknown as AgentTransaction;
    localStorage.setItem("arc-active-transaction", clarification.transaction_id);
    vi.mocked(api.getTransaction).mockResolvedValue(clarification);
    vi.mocked(api.start).mockResolvedValue({
      ...clarification,
      transaction_id: "txn-clarified",
      raw_request: "Buy a monitor\n\nAdditional clarification: Up to 1,200 PLN",
    });

    render(<App />);
    const composer = await screen.findByRole("textbox", { name: "Message the commerce agent" });
    fireEvent.change(composer, { target: { value: "Up to 1,200 PLN" } });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));

    await waitFor(() =>
      expect(api.start).toHaveBeenCalledWith(
        "Buy a monitor\n\nAdditional clarification: Up to 1,200 PLN",
      ),
    );
  });
});
