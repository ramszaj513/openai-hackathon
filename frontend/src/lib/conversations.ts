import type { AgentTransaction, TransactionState } from "../types";

export const ACTIVE_CONVERSATION_KEY = "arc-active-transaction";
export const CONVERSATION_INDEX_KEY = "arc-conversations";

export interface ConversationSummary {
  transactionId: string;
  title: string;
  state: TransactionState | "SENDING";
  updatedAt: string;
  pending?: boolean;
}

export function loadConversationIndex(storage: Storage = localStorage): ConversationSummary[] {
  const stored = storage.getItem(CONVERSATION_INDEX_KEY);
  if (!stored) return [];
  try {
    const parsed: unknown = JSON.parse(stored);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isConversationSummary).filter((item) => !item.pending).sort(byMostRecent);
  } catch {
    return [];
  }
}

export function rememberConversation(
  conversations: ConversationSummary[],
  transaction: AgentTransaction,
  replaceTransactionId?: string,
): ConversationSummary[] {
  const summary: ConversationSummary = {
    transactionId: transaction.transaction_id,
    title: conversationTitle(transaction),
    state: transaction.state,
    updatedAt: transaction.updated_at,
  };
  return [summary, ...conversations.filter((item) =>
    item.transactionId !== summary.transactionId && item.transactionId !== replaceTransactionId
  )]
    .sort(byMostRecent)
    .slice(0, 30);
}

export function pendingConversation(transactionId: string, request: string): ConversationSummary {
  return {
    transactionId,
    title: truncateTitle(request.trim()),
    state: "SENDING",
    updatedAt: new Date().toISOString(),
    pending: true,
  };
}

export function saveConversationIndex(
  conversations: ConversationSummary[],
  storage: Storage = localStorage,
): void {
  storage.setItem(CONVERSATION_INDEX_KEY, JSON.stringify(conversations));
}

function conversationTitle(transaction: AgentTransaction): string {
  const source = transaction.intent?.product_query?.trim() || transaction.raw_request.trim();
  return truncateTitle(source);
}

function truncateTitle(source: string): string {
  return source.length > 42 ? `${source.slice(0, 39).trimEnd()}…` : source;
}

function isConversationSummary(value: unknown): value is ConversationSummary {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  return (
    typeof item.transactionId === "string" &&
    typeof item.title === "string" &&
    typeof item.state === "string" &&
    typeof item.updatedAt === "string"
  );
}

function byMostRecent(left: ConversationSummary, right: ConversationSummary): number {
  return right.updatedAt.localeCompare(left.updatedAt);
}
