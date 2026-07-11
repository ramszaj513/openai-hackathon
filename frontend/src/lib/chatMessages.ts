export const CHAT_MESSAGES_KEY = "arc-chat-messages-v1";

export interface ChatMessage {
  messageId: string;
  role: "user" | "assistant";
  content: string;
  createdAt: string;
}

type ChatMessageStore = Record<string, ChatMessage[]>;

export function loadChatMessages(
  transactionId: string,
  fallbackRawRequest?: string,
  storage: Storage = localStorage,
): ChatMessage[] {
  const store = readStore(storage);
  const saved = store[transactionId];
  if (saved?.length) return saved;
  if (!fallbackRawRequest?.trim()) return [];

  const migrated = legacyUserMessages(fallbackRawRequest);
  store[transactionId] = migrated;
  writeStore(store, storage);
  return migrated;
}

export function appendChatMessage(
  transactionId: string,
  role: ChatMessage["role"],
  content: string,
  storage: Storage = localStorage,
  messageId: string = crypto.randomUUID(),
  createdAt: string = new Date().toISOString(),
): ChatMessage[] {
  const store = readStore(storage);
  const messages = store[transactionId] ?? [];
  const message: ChatMessage = { messageId, role, content: content.trim(), createdAt };
  store[transactionId] = [...messages, message];
  writeStore(store, storage);
  return store[transactionId];
}

export function ensureChatMessage(
  transactionId: string,
  message: ChatMessage,
  storage: Storage = localStorage,
): ChatMessage[] {
  const store = readStore(storage);
  const messages = store[transactionId] ?? [];
  if (messages.some((item) => item.messageId === message.messageId)) return messages;
  store[transactionId] = [...messages, message];
  writeStore(store, storage);
  return store[transactionId];
}

export function moveChatMessages(
  sourceTransactionId: string,
  targetTransactionId: string,
  fallbackRawRequest?: string,
  storage: Storage = localStorage,
): ChatMessage[] {
  if (sourceTransactionId === targetTransactionId) {
    return loadChatMessages(targetTransactionId, fallbackRawRequest, storage);
  }
  const store = readStore(storage);
  const messages = store[sourceTransactionId]?.length
    ? store[sourceTransactionId]
    : store[targetTransactionId]?.length
      ? store[targetTransactionId]
      : fallbackRawRequest
        ? legacyUserMessages(fallbackRawRequest)
        : [];
  delete store[sourceTransactionId];
  store[targetTransactionId] = messages;
  writeStore(store, storage);
  return messages;
}

export function removeChatMessages(
  transactionId: string,
  storage: Storage = localStorage,
): void {
  const store = readStore(storage);
  delete store[transactionId];
  writeStore(store, storage);
}

function legacyUserMessages(rawRequest: string): ChatMessage[] {
  return rawRequest
    .split(/\n\nAdditional clarification:\s*/i)
    .map((content) => content.trim())
    .filter(Boolean)
    .map((content, index) => ({
      messageId: `legacy-user-${index}`,
      role: "user" as const,
      content,
      createdAt: new Date(0).toISOString(),
    }));
}

function readStore(storage: Storage): ChatMessageStore {
  const raw = storage.getItem(CHAT_MESSAGES_KEY);
  if (!raw) return {};
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    return Object.fromEntries(
      Object.entries(parsed).flatMap(([transactionId, value]) => {
        if (!Array.isArray(value)) return [];
        const messages = value.filter(isChatMessage);
        return messages.length ? [[transactionId, messages]] : [];
      }),
    );
  } catch {
    return {};
  }
}

function writeStore(store: ChatMessageStore, storage: Storage): void {
  storage.setItem(CHAT_MESSAGES_KEY, JSON.stringify(store));
}

function isChatMessage(value: unknown): value is ChatMessage {
  if (!value || typeof value !== "object") return false;
  const message = value as Record<string, unknown>;
  return (
    typeof message.messageId === "string" &&
    (message.role === "user" || message.role === "assistant") &&
    typeof message.content === "string" &&
    typeof message.createdAt === "string"
  );
}
