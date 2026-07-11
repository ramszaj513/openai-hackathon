import type {
  AgentTransaction,
  DomainEvent,
  Order,
  Payment,
  TransactionAccepted,
  TransactionActivity,
  TransactionState,
} from "../types";

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "";

export class APIError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

const START_SETTLED_STATES = new Set<TransactionState>([
  "CLARIFICATION_REQUIRED",
  "NO_MATCH",
  "APPROVAL_PENDING",
  "FULFILLING",
  "DELIVERED",
  "CANCELLED",
  "REFUNDED",
  "FAILED",
]);

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: { "Content-Type": "application/json", ...options?.headers },
    });
  } catch {
    throw new APIError("BACKEND_UNAVAILABLE", "Cannot reach the commerce backend.", 0);
  }

  const payload = (await response.json().catch(() => null)) as Record<string, unknown> | null;
  if (!response.ok) {
    throw new APIError(
      String(payload?.code ?? "HTTP_ERROR"),
      String(payload?.message ?? "The backend rejected the request."),
      response.status,
    );
  }
  return payload as T;
}

async function requestSdp(path: string, sdp: string): Promise<string> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/sdp" },
      body: sdp,
    });
  } catch {
    throw new APIError("BACKEND_UNAVAILABLE", "Cannot reach the commerce backend.", 0);
  }

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as Record<string, unknown> | null;
    throw new APIError(
      String(payload?.code ?? "TRANSCRIPTION_ERROR"),
      String(payload?.message ?? "Could not start voice input."),
      response.status,
    );
  }
  return response.text();
}

export const api = {
  async health(): Promise<boolean> {
    try {
      const result = await request<{ status: string }>("/health");
      return result.status === "ok";
    } catch {
      return false;
    }
  },

  start(rawRequest: string): Promise<TransactionAccepted> {
    return request("/api/agent/transactions", {
      method: "POST",
      body: JSON.stringify({
        user_id: "user-bartosz",
        agent_id: "commerce-agent",
        raw_request: rawRequest,
        payment_scenario: "APPROVE",
        idempotency_key: `web-start-${crypto.randomUUID()}`,
      }),
    });
  },

  createTranscriptionSession(sdp: string): Promise<string> {
    return requestSdp("/api/realtime/transcription/session", sdp);
  },

  getTransaction(id: string): Promise<AgentTransaction> {
    return request(`/api/agent/transactions/${id}`);
  },

  activity(id: string, afterSequence = 0): Promise<TransactionActivity[]> {
    return request(
      `/api/agent/transactions/${id}/activity?after_sequence=${afterSequence}`,
    );
  },

  streamActivity(
    id: string,
    afterSequence: number,
    onActivity: (activity: TransactionActivity) => void,
    onDisconnect?: () => void,
  ): () => void {
    const stream = new EventSource(
      `${API_BASE}/api/agent/transactions/${id}/stream?after_sequence=${afterSequence}`,
    );
    stream.addEventListener("transaction.activity", (event) => {
      onActivity(JSON.parse((event as MessageEvent<string>).data) as TransactionActivity);
    });
    stream.onerror = () => {
      stream.close();
      onDisconnect?.();
    };
    return () => stream.close();
  },

  async waitForStartResult(
    id: string,
    onUpdate?: (transaction: AgentTransaction) => void,
    pollIntervalMs = 500,
    maxAttempts = 240,
  ): Promise<AgentTransaction> {
    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      const transaction = await this.getTransaction(id);
      onUpdate?.(transaction);
      if (START_SETTLED_STATES.has(transaction.state)) return transaction;
      await new Promise((resolve) => window.setTimeout(resolve, pollIntervalMs));
    }
    throw new APIError(
      "TRANSACTION_TIMEOUT",
      "The agent is still working. Refresh this transaction to continue tracking it.",
      0,
    );
  },

  approve(transaction: AgentTransaction): Promise<AgentTransaction> {
    if (!transaction.proposal) throw new Error("The transaction has no checkout proposal.");
    return request(`/api/agent/transactions/${transaction.transaction_id}/approve`, {
      method: "POST",
      body: JSON.stringify({
        transaction_id: transaction.transaction_id,
        user_id: transaction.user_id,
        approved_content_hash: transaction.proposal.content_hash,
        idempotency_key: `web-approve-${transaction.transaction_id}`,
      }),
    });
  },

  resume(id: string): Promise<AgentTransaction> {
    return request(`/api/agent/transactions/${id}/resume`, { method: "POST" });
  },

  cancel(transaction: AgentTransaction): Promise<AgentTransaction> {
    return request(`/api/agent/transactions/${transaction.transaction_id}/cancel`, {
      method: "POST",
      body: JSON.stringify({
        transaction_id: transaction.transaction_id,
        reason: "User requested cancellation in chat",
        idempotency_key: `web-cancel-${transaction.transaction_id}`,
      }),
    });
  },

  createReturn(transaction: AgentTransaction, items: Record<string, number>, reason: string) {
    return request<AgentTransaction>(`/api/agent/transactions/${transaction.transaction_id}/return`, {
      method: "POST",
      body: JSON.stringify({
        transaction_id: transaction.transaction_id,
        items,
        reason,
        idempotency_key: `web-return-${transaction.transaction_id}`,
      }),
    });
  },

  getOrder(id: string): Promise<Order> {
    return request(`/api/orders/${id}`);
  },

  getPayment(id: string): Promise<Payment> {
    return request(`/api/payments/${id}`);
  },

  setOrderState(order: Order, state: Order["state"]): Promise<Order> {
    return request(`/api/demo/orders/${order.order_id}/state`, {
      method: "POST",
      body: JSON.stringify({
        order_id: order.order_id,
        state,
        idempotency_key: `web-state-${order.order_id}-${state}`,
      }),
    });
  },

  events(id: string): Promise<DomainEvent[]> {
    return request(`/api/transactions/${id}/events`);
  },
};
