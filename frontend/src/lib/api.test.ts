import { afterEach, describe, expect, it, vi } from "vitest";
import type { AgentTransaction } from "../types";
import { api } from "./api";

describe("browser API contract", () => {
  afterEach(() => vi.restoreAllMocks());

  it("binds explicit approval to the current proposal hash and transaction", async () => {
    const transaction = {
      transaction_id: "txn-1",
      user_id: "user-1",
      proposal: { content_hash: "sha256-current-proposal" },
    } as AgentTransaction;
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(transaction), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await api.approve(transaction);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/agent/transactions/txn-1/approve",
      expect.objectContaining({ method: "POST" }),
    );
    const options = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(options.body))).toMatchObject({
      transaction_id: "txn-1",
      user_id: "user-1",
      approved_content_hash: "sha256-current-proposal",
      idempotency_key: "web-approve-txn-1",
    });
  });

  it("exchanges a WebRTC offer for a transcription SDP answer", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("answer-sdp", {
        status: 201,
        headers: { "Content-Type": "application/sdp" },
      }),
    );

    await expect(api.createTranscriptionSession("offer-sdp")).resolves.toBe("answer-sdp");
    expect(fetchMock).toHaveBeenCalledWith("/api/realtime/transcription/session", {
      method: "POST",
      headers: { "Content-Type": "application/sdp" },
      body: "offer-sdp",
    });
  });
});
