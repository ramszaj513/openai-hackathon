import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { api } from "./lib/api";
import { CONVERSATION_INDEX_KEY } from "./lib/conversations";
import type { AgentTransaction, TransactionAccepted, TransactionActivity } from "./types";

vi.mock("./lib/api", () => ({
  APIError: class APIError extends Error {},
  api: {
    health: vi.fn().mockResolvedValue(true),
    paymentConfig: vi.fn().mockResolvedValue({
      provider: "simulator",
      requires_payment_method: false,
      stripe_publishable_key: null,
    }),
    getTransaction: vi.fn(),
    getOrder: vi.fn(),
    getPayment: vi.fn(),
    events: vi.fn().mockResolvedValue([]),
    activity: vi.fn().mockResolvedValue([]),
    streamActivity: vi.fn().mockReturnValue(() => undefined),
    waitForStartResult: vi.fn(),
    start: vi.fn(),
  },
}));

describe("single-chat commerce experience", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    vi.mocked(api.health).mockResolvedValue(true);
    vi.mocked(api.events).mockResolvedValue([]);
    vi.mocked(api.activity).mockResolvedValue([]);
    vi.mocked(api.streamActivity).mockReturnValue(() => undefined);
  });

  it("starts with one conversational composer and the canonical demo shortcut", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "What can I take care of?" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Message the commerce agent" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start voice input" })).toBeInTheDocument();
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
    let resolveStart!: (receipt: TransactionAccepted) => void;
    const transaction = {
      transaction_id: "txn-desk",
      raw_request: "Find a standing desk",
      intent: { product_query: "Standing desk" },
      state: "APPROVAL_PENDING",
      transitions: [],
      updated_at: "2026-07-11T13:00:00Z",
    } as unknown as AgentTransaction;
    vi.mocked(api.waitForStartResult).mockResolvedValue(transaction);
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
        transaction,
        status_url: "/api/agent/transactions/txn-desk",
        activity_url: "/api/agent/transactions/txn-desk/activity",
        stream_url: "/api/agent/transactions/txn-desk/stream",
        recommended_poll_interval_ms: 500,
      });
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
    const clarified = {
      ...clarification,
      transaction_id: "txn-clarified",
      raw_request: "Buy a monitor\n\nAdditional clarification: Up to 1,200 PLN",
    };
    vi.mocked(api.start).mockResolvedValue({
      transaction: clarified,
      status_url: "/api/agent/transactions/txn-clarified",
      activity_url: "/api/agent/transactions/txn-clarified/activity",
      stream_url: "/api/agent/transactions/txn-clarified/stream",
      recommended_poll_interval_ms: 500,
    });
    vi.mocked(api.waitForStartResult).mockResolvedValue(clarified);

    render(<App />);
    const composer = await screen.findByRole("textbox", { name: "Message the commerce agent" });
    fireEvent.change(composer, { target: { value: "Up to 1,200 PLN" } });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));

    await waitFor(() =>
      expect(api.start).toHaveBeenCalledWith(
        "Buy a monitor\n\nAdditional clarification: Up to 1,200 PLN",
      ),
    );
    expect(screen.getByText("Buy a monitor")).toHaveClass("user-bubble");
    expect(screen.getByText("Up to 1,200 PLN")).toHaveClass("user-bubble");
    expect(screen.queryByText("Buy a monitor\n\nAdditional clarification: Up to 1,200 PLN")).not.toBeInTheDocument();
  });

  it("states clearly when the agent found no suitable offer", async () => {
    const noMatch = {
      transaction_id: "txn-no-match",
      user_id: "user-1",
      agent_id: "agent-1",
      raw_request: "Find a quiet coffee grinder under 300 PLN",
      state: "NO_MATCH",
      selection: {
        selected_offer_id: null,
        confidence: 0,
        selection_reason: "The connected merchants returned no products matching the request.",
        satisfied_constraints: [],
        disclosed_compromises: [],
        rejected_offers: [],
      },
      transitions: [],
      updated_at: "2026-07-11T13:00:00Z",
    } as unknown as AgentTransaction;
    localStorage.setItem("arc-active-transaction", noMatch.transaction_id);
    vi.mocked(api.getTransaction).mockResolvedValue(noMatch);

    render(<App />);

    expect(await screen.findByRole("heading", { name: "I couldn't find a good match." })).toBeInTheDocument();
    expect(screen.getByText(/won't recommend or purchase/i)).toBeInTheDocument();
  });

  it("collapses model and MCP telemetry into one searching-offers step", async () => {
    const transaction = {
      transaction_id: "txn-timeline",
      user_id: "user-1",
      agent_id: "agent-1",
      raw_request: "Find a monitor",
      state: "CHECKOUT_DRAFT",
      transitions: [],
      updated_at: "2026-07-11T13:00:00Z",
    } as unknown as AgentTransaction;
    const baseActivity = {
      transaction_id: transaction.transaction_id,
      actor_type: "agent",
      actor_id: transaction.agent_id,
      authority: "agent",
      status: "COMPLETED",
      occurred_at: "2026-07-11T13:00:00Z",
      data: {},
    } as const;
    const activity = [
      { ...baseActivity, event_id: "activity-1", sequence: 1, kind: "agent.llm.completed", phase: "DISCOVERY", title: "Model reasoning completed", message: "The planner returned a structured result." },
      { ...baseActivity, event_id: "activity-2", sequence: 2, kind: "agent.tool.started", phase: "DISCOVERY", title: "Calling search_offers", message: "Requesting merchant data." },
      { ...baseActivity, event_id: "activity-3", sequence: 3, kind: "transaction.transition", phase: "DISCOVERY", title: "Offer Selected", message: "The offer satisfies every hard constraint.", data: { to_state: "OFFER_SELECTED" } },
      { ...baseActivity, event_id: "activity-4", sequence: 4, kind: "transaction.transition", phase: "CHECKOUT", title: "Checkout Draft", message: "Merchant created an authoritative checkout.", data: { to_state: "CHECKOUT_DRAFT" } },
    ] as TransactionActivity[];
    localStorage.setItem("arc-active-transaction", transaction.transaction_id);
    vi.mocked(api.getTransaction).mockResolvedValue(transaction);
    vi.mocked(api.activity).mockResolvedValue(activity);

    render(<App />);

    expect(await screen.findByText("Searching offers")).toBeInTheDocument();
    expect(screen.getByText("Offer Selected")).toBeInTheDocument();
    expect(screen.getByText("Checkout Draft")).toBeInTheDocument();
    expect(screen.queryByText("Model reasoning completed")).not.toBeInTheDocument();
    expect(screen.queryByText("Calling search_offers")).not.toBeInTheDocument();
  });
});
