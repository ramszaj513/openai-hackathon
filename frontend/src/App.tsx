import { FormEvent, useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  ArrowUpIcon,
  CheckIcon,
  ChevronIcon,
  ClockIcon,
  LockIcon,
  MenuIcon,
  MonitorIcon,
  PackageIcon,
  PlusIcon,
  RefreshIcon,
  ShieldIcon,
  SparkIcon,
  TruckIcon,
  XIcon,
} from "./components/Icons";
import { api, APIError } from "./lib/api";
import {
  appendChatMessage,
  ensureChatMessage,
  loadChatMessages,
  moveChatMessages,
  removeChatMessages,
  type ChatMessage,
} from "./lib/chatMessages";
import {
  ACTIVE_CONVERSATION_KEY,
  loadConversationIndex,
  pendingConversation,
  rememberConversation as upsertConversation,
  saveConversationIndex,
  type ConversationSummary,
} from "./lib/conversations";
import { CANONICAL_REQUEST, formatDate, formatMoney, sentenceCase } from "./lib/format";
import type {
  AgentTransaction,
  DomainEvent,
  Order,
  Payment,
  TransactionActivity,
  TransactionState,
} from "./types";

type BusyAction = "starting" | "approving" | "refreshing" | "cancelling" | "returning" | "advancing" | null;

const APPROVAL_EXECUTION_STATES = new Set<TransactionState>([
  "APPROVAL_PENDING",
  "APPROVED",
  "PAYMENT_AUTHORIZING",
  "PAYMENT_AUTHORIZED",
  "ORDER_COMMITTING",
  "RECOVERY_REQUIRED",
  "ORDER_CONFIRMED",
  "PAYMENT_CAPTURED",
  "FULFILLING",
]);

function latestApprovalExecutionState(
  activities: TransactionActivity[],
  fallback: TransactionState,
): TransactionState {
  for (let index = activities.length - 1; index >= 0; index -= 1) {
    const state = activities[index].data.to_state;
    if (typeof state === "string" && APPROVAL_EXECUTION_STATES.has(state as TransactionState)) {
      return state as TransactionState;
    }
  }
  return fallback;
}

function App() {
  const [draft, setDraft] = useState("");
  const [transaction, setTransaction] = useState<AgentTransaction | null>(null);
  const [order, setOrder] = useState<Order | null>(null);
  const [payment, setPayment] = useState<Payment | null>(null);
  const [events, setEvents] = useState<DomainEvent[]>([]);
  const [activities, setActivities] = useState<TransactionActivity[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>(() => {
    const activeId = localStorage.getItem(ACTIVE_CONVERSATION_KEY);
    return activeId ? loadChatMessages(activeId) : [];
  });
  const [conversations, setConversations] = useState<ConversationSummary[]>(loadConversationIndex);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(() =>
    localStorage.getItem(ACTIVE_CONVERSATION_KEY),
  );
  const [busy, setBusy] = useState<BusyAction>(() =>
    localStorage.getItem(ACTIVE_CONVERSATION_KEY) ? "refreshing" : null,
  );
  const [error, setError] = useState<string | null>(null);
  const [consent, setConsent] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [returnReason, setReturnReason] = useState("Changed my mind");
  const conversationEnd = useRef<HTMLDivElement>(null);
  const viewVersion = useRef(0);
  const activeConversationIdRef = useRef(activeConversationId);
  const activitiesRef = useRef<TransactionActivity[]>([]);
  const activityStreamRef = useRef<(() => void) | null>(null);

  function replaceActivities(next: TransactionActivity[]) {
    const ordered = [...next].sort((left, right) => left.sequence - right.sequence);
    activitiesRef.current = ordered;
    setActivities(ordered);
  }

  function appendActivity(next: TransactionActivity) {
    if (activitiesRef.current.some((item) => item.event_id === next.event_id)) return;
    replaceActivities([...activitiesRef.current, next]);
  }

  function followActivity(transactionId: string, view: number) {
    activityStreamRef.current?.();
    const cursor = activitiesRef.current.at(-1)?.sequence ?? 0;
    const close = api.streamActivity(transactionId, cursor, (activity) => {
      if (
        view === viewVersion.current &&
        activeConversationIdRef.current === transactionId
      ) {
        appendActivity(activity);
      }
    });
    activityStreamRef.current = close;
    return () => {
      close();
      if (activityStreamRef.current === close) activityStreamRef.current = null;
    };
  }

  function transcriptFor(next: AgentTransaction, replaceTransactionId?: string) {
    let transcript = replaceTransactionId
      ? moveChatMessages(replaceTransactionId, next.transaction_id, next.raw_request)
      : loadChatMessages(next.transaction_id, next.raw_request);
    if (next.state === "CLARIFICATION_REQUIRED" && next.intent?.clarification_questions.length) {
      transcript = ensureChatMessage(next.transaction_id, {
        messageId: `${next.transaction_id}:clarification:${next.updated_at}`,
        role: "assistant",
        content: next.intent.clarification_questions.join(" "),
        createdAt: next.updated_at,
      });
    }
    return transcript;
  }

  useEffect(() => {
    let active = true;
    const saved = localStorage.getItem(ACTIVE_CONVERSATION_KEY);
    if (saved) {
      const view = viewVersion.current;
      void (async () => {
        try {
          const restored = await api.getTransaction(saved);
          const [restoredOrder, restoredPayment, restoredEvents, restoredActivities] = await Promise.all([
            restored.order_id ? api.getOrder(restored.order_id) : Promise.resolve(null),
            restored.payment_id ? api.getPayment(restored.payment_id) : Promise.resolve(null),
            api.events(restored.transaction_id).catch(() => []),
            api.activity(restored.transaction_id).catch(() => []),
          ]);
          if (!active || view !== viewVersion.current) return;
          setTransaction(restored);
          setOrder(restoredOrder);
          setPayment(restoredPayment);
          setEvents(restoredEvents);
          replaceActivities(restoredActivities);
          setMessages(transcriptFor(restored));
          const updatedIndex = upsertConversation(loadConversationIndex(), restored);
          saveConversationIndex(updatedIndex);
          setConversations(updatedIndex);
        } catch {
          if (view === viewVersion.current) {
            localStorage.removeItem(ACTIVE_CONVERSATION_KEY);
            activeConversationIdRef.current = null;
            setActiveConversationId(null);
          }
        } finally {
          if (active && view === viewVersion.current) setBusy(null);
        }
      })();
    }
    return () => {
      active = false;
      activityStreamRef.current?.();
    };
  }, []);

  useEffect(() => {
    conversationEnd.current?.scrollIntoView?.({ behavior: "smooth", block: "end" });
  }, [transaction, order, payment, activities, messages, busy, error]);

  async function hydrate(next: AgentTransaction, view: number) {
    const [nextOrder, nextPayment, nextEvents, nextActivities] = await Promise.all([
      next.order_id ? api.getOrder(next.order_id) : Promise.resolve(null),
      next.payment_id ? api.getPayment(next.payment_id) : Promise.resolve(null),
      api.events(next.transaction_id).catch(() => []),
      api.activity(next.transaction_id).catch(() => []),
    ]);
    if (view !== viewVersion.current) return;
    setOrder(nextOrder);
    setPayment(nextPayment);
    setEvents(nextEvents);
    replaceActivities(nextActivities);
  }

  function remember(next: AgentTransaction, replaceTransactionId?: string) {
    setConversations((current) => {
      const updated = upsertConversation(current, next, replaceTransactionId);
      saveConversationIndex(updated);
      return updated;
    });
  }

  async function applyResult(
    next: AgentTransaction,
    view: number,
    replaceTransactionId?: string,
  ) {
    const nextMessages = transcriptFor(next, replaceTransactionId);
    remember(next, replaceTransactionId);
    const targetView =
      view === viewVersion.current
        ? view
        : activeConversationIdRef.current === next.transaction_id ||
            activeConversationIdRef.current === replaceTransactionId
          ? viewVersion.current
          : null;
    if (targetView === null) return;
    setTransaction(next);
    setMessages(nextMessages);
    activeConversationIdRef.current = next.transaction_id;
    setActiveConversationId(next.transaction_id);
    localStorage.setItem(ACTIVE_CONVERSATION_KEY, next.transaction_id);
    await hydrate(next, targetView);
  }

  function showError(cause: unknown, view = viewVersion.current) {
    if (view !== viewVersion.current) return;
    if (cause instanceof APIError) setError(`${cause.code}: ${cause.message}`);
    else setError(cause instanceof Error ? cause.message : "Something unexpected happened.");
  }

  async function submitIntent(event: FormEvent) {
    event.preventDefault();
    const intent = draft.trim();
    if (!intent || busy) return;
    const view = viewVersion.current;
    const clarification = transaction?.state === "CLARIFICATION_REQUIRED";
    const replaceTransactionId = clarification
      ? transaction.transaction_id
      : `pending:${crypto.randomUUID()}`;
    const request = clarification
      ? `${transaction.raw_request}\n\nAdditional clarification: ${intent}`
      : intent;
    if (!clarification) {
      const optimistic = pendingConversation(replaceTransactionId, intent);
      setConversations((current) => {
        const updated = [optimistic, ...current];
        saveConversationIndex(updated);
        return updated;
      });
      activeConversationIdRef.current = replaceTransactionId;
      setActiveConversationId(replaceTransactionId);
    }
    const messageOwnerId = clarification ? transaction.transaction_id : replaceTransactionId;
    setMessages(appendChatMessage(messageOwnerId, "user", intent));
    setError(null);
    setBusy("starting");
    let acceptedTransactionId: string | null = null;
    try {
      const accepted = await api.start(request);
      acceptedTransactionId = accepted.transaction.transaction_id;
      await applyResult(accepted.transaction, view, replaceTransactionId);
      const stopFollowing = followActivity(accepted.transaction.transaction_id, view);
      try {
        const next = await api.waitForStartResult(
          accepted.transaction.transaction_id,
          (update) => {
            remember(update, replaceTransactionId);
            if (
              view === viewVersion.current &&
              activeConversationIdRef.current === update.transaction_id
            ) {
              setTransaction(update);
            }
          },
          accepted.recommended_poll_interval_ms,
        );
        await applyResult(next, view, replaceTransactionId);
      } finally {
        stopFollowing();
      }
      if (view === viewVersion.current) setDraft("");
    } catch (cause) {
      if (!clarification && acceptedTransactionId === null) {
        removeChatMessages(replaceTransactionId);
        setConversations((current) => {
          const updated = current.filter(
            (conversation) => conversation.transactionId !== replaceTransactionId,
          );
          saveConversationIndex(updated);
          return updated;
        });
        if (view === viewVersion.current) {
          activeConversationIdRef.current = null;
          setActiveConversationId(null);
          setMessages([]);
        }
      }
      showError(cause, view);
    } finally {
      if (view === viewVersion.current) setBusy(null);
    }
  }

  async function approve() {
    if (!transaction || !consent) return;
    const view = viewVersion.current;
    setError(null);
    setBusy("approving");
    const stopFollowing = followActivity(transaction.transaction_id, view);
    try {
      const next = await api.approve(transaction);
      await applyResult(next, view);
    } catch (cause) {
      showError(cause, view);
    } finally {
      stopFollowing();
      if (view === viewVersion.current) setBusy(null);
    }
  }

  async function cancel() {
    if (!transaction) return;
    const view = viewVersion.current;
    setError(null);
    setBusy("cancelling");
    const stopFollowing = followActivity(transaction.transaction_id, view);
    try {
      const next = await api.cancel(transaction);
      await applyResult(next, view);
    } catch (cause) {
      showError(cause, view);
    } finally {
      stopFollowing();
      if (view === viewVersion.current) setBusy(null);
    }
  }

  async function advanceOrder() {
    if (!transaction || !order) return;
    const nextState: Partial<Record<Order["state"], Order["state"]>> = {
      CONFIRMED: "PROCESSING",
      PROCESSING: "SHIPPED",
      SHIPPED: "DELIVERED",
    };
    const state = nextState[order.state];
    if (!state) return;
    const view = viewVersion.current;
    setBusy("advancing");
    setError(null);
    const stopFollowing = followActivity(transaction.transaction_id, view);
    try {
      await api.setOrderState(order, state);
      const next = await api.resume(transaction.transaction_id);
      await applyResult(next, view);
    } catch (cause) {
      showError(cause, view);
    } finally {
      stopFollowing();
      if (view === viewVersion.current) setBusy(null);
    }
  }

  async function createReturn() {
    if (!transaction || !order || returnReason.trim().length < 3) return;
    const view = viewVersion.current;
    setBusy("returning");
    setError(null);
    const stopFollowing = followActivity(transaction.transaction_id, view);
    try {
      const items = Object.fromEntries(order.lines.map((line) => [line.product_id, line.quantity]));
      const next = await api.createReturn(transaction, items, returnReason.trim());
      await applyResult(next, view);
    } catch (cause) {
      showError(cause, view);
    } finally {
      stopFollowing();
      if (view === viewVersion.current) setBusy(null);
    }
  }

  async function openConversation(transactionId: string) {
    if (transactionId === activeConversationId) {
      setSidebarOpen(false);
      return;
    }
    activityStreamRef.current?.();
    activityStreamRef.current = null;
    const view = ++viewVersion.current;
    activeConversationIdRef.current = transactionId;
    setActiveConversationId(transactionId);
    localStorage.setItem(ACTIVE_CONVERSATION_KEY, transactionId);
    setTransaction(null);
    setOrder(null);
    setPayment(null);
    setEvents([]);
    replaceActivities([]);
    setMessages(loadChatMessages(transactionId));
    setBusy("refreshing");
    setError(null);
    setConsent(false);
    setSidebarOpen(false);
    try {
      const next = await api.getTransaction(transactionId);
      await applyResult(next, view);
    } catch (cause) {
      showError(cause, view);
    } finally {
      if (view === viewVersion.current) setBusy(null);
    }
  }

  function newConversation() {
    viewVersion.current += 1;
    activityStreamRef.current?.();
    activityStreamRef.current = null;
    localStorage.removeItem(ACTIVE_CONVERSATION_KEY);
    activeConversationIdRef.current = null;
    setActiveConversationId(null);
    setTransaction(null);
    setOrder(null);
    setPayment(null);
    setEvents([]);
    replaceActivities([]);
    setMessages([]);
    setError(null);
    setBusy(null);
    setConsent(false);
    setDraft("");
    setSidebarOpen(false);
  }

  const hasStarted = Boolean(transaction || busy);
  const approvalExecutionState = transaction && busy === "approving"
    ? latestApprovalExecutionState(activities, transaction.state)
    : transaction?.state;

  return (
    <div className="app-shell">
      <aside className={`sidebar ${sidebarOpen ? "sidebar--open" : ""}`}>
        <div className="sidebar__top">
          <div className="brand"><span className="brand__mark">a</span><span>aShop</span></div>
          <button className="icon-button sidebar__close" onClick={() => setSidebarOpen(false)} aria-label="Close sidebar"><XIcon /></button>
        </div>
        <button className="new-chat" onClick={newConversation}><PlusIcon /><span>New transaction</span></button>

        <div className="sidebar__section">
          <p className="sidebar__label">Conversations</p>
          <div className="conversation-list">
            {conversations.length === 0 && <p className="conversation-list__empty">Your transactions will appear here.</p>}
            {conversations.map((conversation) => (
              <button
                className={`conversation-link ${conversation.transactionId === activeConversationId ? "conversation-link--active" : ""}`}
                disabled={conversation.pending}
                key={conversation.transactionId}
                onClick={() => void openConversation(conversation.transactionId)}
              >
                <span className="conversation-link__icon"><SparkIcon /></span>
                <span><strong>{conversation.title}</strong><small>{sentenceCase(conversation.state)}</small></span>
              </button>
            ))}
          </div>
        </div>

      </aside>
      {sidebarOpen && <button className="scrim" aria-label="Close sidebar" onClick={() => setSidebarOpen(false)} />}

      <main className="main">
        <header className="topbar">
          <button className="icon-button menu-button" onClick={() => setSidebarOpen(true)} aria-label="Open sidebar"><MenuIcon /></button>
          <div className="topbar__title"><span>Commerce agent</span><small><span className="status-dot status-dot--online" /> Ready to act</small></div>
        </header>

        <section className={`conversation ${hasStarted ? "conversation--active" : ""}`} aria-live="polite">
          {!hasStarted && <Welcome onPrompt={() => setDraft(CANONICAL_REQUEST)} />}

          {messages.map((message) => message.role === "user"
            ? <UserMessage key={message.messageId}>{message.content}</UserMessage>
            : <AssistantMessage key={message.messageId}><div className="assistant-copy"><h2>I need one more detail</h2><p>{message.content}</p></div></AssistantMessage>
          )}
          {busy === "refreshing" && !transaction && <Thinking label="Loading conversation…" />}
          {busy === "starting" && <Thinking />}

          {transaction?.state === "FAILED" && (
            <AssistantMessage tone="error"><div className="assistant-copy"><h2>I couldn't complete that request</h2><p>{transaction.last_error_message}</p></div></AssistantMessage>
          )}

          {transaction?.state === "NO_MATCH" && transaction.selection && (
            <AssistantMessage>
              <div className="assistant-copy">
                <p className="eyebrow"><SparkIcon /> Search complete</p>
                <h2>I couldn't find a good match.</h2>
                <p>{transaction.selection.selection_reason}</p>
                <p>I won't recommend or purchase an option that does not satisfy your request.</p>
              </div>
            </AssistantMessage>
          )}

          {transaction?.selection && transaction.selected_offer && transaction.intent && (
            <AssistantMessage>
              <div className="assistant-copy">
                <p className="eyebrow"><SparkIcon /> Request understood</p>
                <h2>I found a strong match.</h2>
                <p>{transaction.selection.selection_reason}</p>
              </div>
              <IntentSummary transaction={transaction} />
              <ProductCard transaction={transaction} />
            </AssistantMessage>
          )}

          {transaction?.proposal && !transaction.order_id && transaction.state !== "FAILED" && (
            <AssistantMessage>
              <ApprovalCard transaction={transaction} consent={consent} setConsent={setConsent} onApprove={() => void approve()} busy={busy === "approving"} executionState={approvalExecutionState} />
            </AssistantMessage>
          )}

          {transaction?.approval_id && <UserMessage compact>Approved this exact checkout.</UserMessage>}

          {order && payment && (
            <AssistantMessage>
              <OrderCard order={order} payment={payment} transaction={transaction!} busy={busy} onCancel={() => void cancel()} onAdvance={() => void advanceOrder()} returnReason={returnReason} setReturnReason={setReturnReason} onReturn={() => void createReturn()} />
            </AssistantMessage>
          )}

          {error && <AssistantMessage tone="error"><div className="assistant-copy"><h2>Something needs attention</h2><p>{error}</p><button className="text-button" onClick={() => setError(null)}>Dismiss</button></div></AssistantMessage>}

          {transaction && (activities.length > 0 || transaction.transitions.length > 0) && (
            <AssistantMessage subtle><Timeline transaction={transaction} events={events} activities={activities} live={busy === "starting" || busy === "approving"} /></AssistantMessage>
          )}
          <div ref={conversationEnd} />
        </section>

        <Composer draft={draft} setDraft={setDraft} submit={submitIntent} disabled={Boolean(busy)} hasTransaction={transaction !== null && transaction.state !== "CLARIFICATION_REQUIRED"} newConversation={newConversation} />
      </main>
    </div>
  );
}

function Welcome({ onPrompt }: { onPrompt: () => void }) {
  return <div className="welcome">
    <div className="welcome__orb"><SparkIcon /></div>
    <p className="eyebrow">AGENT-FIRST COMMERCE</p>
    <h1>What can I take care of?</h1>
    <p className="welcome__sub">Tell me what you need. I’ll compare the options, explain my choice, ask before spending, and stay with the order through resolution.</p>
    <button className="suggestion" onClick={onPrompt}><MonitorIcon /><span><strong>Try the demo request</strong><small>Find a Mac-compatible monitor under 1,200 PLN</small></span><ChevronIcon /></button>
  </div>;
}

function Composer({ draft, setDraft, submit, disabled, hasTransaction, newConversation }: { draft: string; setDraft: (value: string) => void; submit: (event: FormEvent) => void; disabled: boolean; hasTransaction: boolean; newConversation: () => void }) {
  const textarea = useRef<HTMLTextAreaElement>(null);

  useLayoutEffect(() => {
    const input = textarea.current;
    if (!input) return;
    input.style.height = "0px";
    const nextHeight = Math.min(input.scrollHeight, 160);
    input.style.height = `${Math.max(38, nextHeight)}px`;
    input.style.overflowY = input.scrollHeight > 160 ? "auto" : "hidden";
  }, [draft]);

  return <div className="composer-wrap">
    {hasTransaction ? <button className="start-over" onClick={newConversation}><PlusIcon /> Start another transaction</button> : <form className="composer" onSubmit={submit}>
      <textarea ref={textarea} aria-label="Message the commerce agent" placeholder="Describe what you'd like me to buy…" value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} rows={1} disabled={disabled} />
      <button type="submit" disabled={disabled || !draft.trim()} aria-label="Send message"><ArrowUpIcon /></button>
    </form>}
    <p className="composer-note"><LockIcon /> You always approve the exact total before purchase</p>
  </div>;
}

function UserMessage({ children, compact = false }: { children: React.ReactNode; compact?: boolean }) {
  return <div className={`message message--user ${compact ? "message--compact" : ""}`}><div className="user-avatar">B</div><div className="user-bubble">{children}</div></div>;
}

function AssistantMessage({ children, tone, subtle = false }: { children: React.ReactNode; tone?: "error"; subtle?: boolean }) {
  return <div className={`message message--assistant ${tone ? `message--${tone}` : ""} ${subtle ? "message--subtle" : ""}`}><div className="agent-avatar">a</div><div className="assistant-content">{children}</div></div>;
}

function Thinking({ label = "Understanding your request and comparing eligible offers…" }: { label?: string }) {
  return <AssistantMessage><div className="thinking"><span /><span /><span /><p>{label}</p></div></AssistantMessage>;
}

function IntentSummary({ transaction }: { transaction: AgentTransaction }) {
  const intent = transaction.intent!;
  return <div className="constraint-row">
    <span><strong>{intent.max_budget_minor ? formatMoney(intent.max_budget_minor, intent.currency) : "Any budget"}</strong><small>maximum</small></span>
    <span><strong>{intent.required_attributes.mac_compatible ? "Mac" : "Any"}</strong><small>compatibility</small></span>
    <span><strong>{formatDate(intent.latest_delivery_date)}</strong><small>delivery by</small></span>
    <span><strong>{intent.minimum_return_window_days ?? 0}+ days</strong><small>returns</small></span>
  </div>;
}

function ProductCard({ transaction }: { transaction: AgentTransaction }) {
  const offer = transaction.selected_offer!;
  const selection = transaction.selection!;
  return <div className="product-card">
    <div className="product-visual"><MonitorIcon /><span>{offer.product.brand}</span></div>
    <div className="product-info"><div className="match-pill"><CheckIcon /> {Math.round(selection.confidence * 100)}% match</div><h3>{offer.product.name}</h3><p>{offer.variant} · {offer.product.description}</p><div className="product-meta"><span><TruckIcon /> {formatDate(offer.delivery_options[0]?.estimated_delivery_date)}</span><span><RefreshIcon /> {offer.return_policy.window_days}-day returns</span></div></div>
    <div className="product-price"><strong>{formatMoney(offer.unit_price.amount_minor, offer.unit_price.currency)}</strong><small>merchant price</small></div>
  </div>;
}

function ApprovalCard({ transaction, consent, setConsent, onApprove, busy, executionState }: { transaction: AgentTransaction; consent: boolean; setConsent: (value: boolean) => void; onApprove: () => void; busy: boolean; executionState?: TransactionState }) {
  const proposal = transaction.proposal!;
  const progress = approvalProgress(executionState ?? transaction.state, proposal.price.total_minor, proposal.price.currency);
  return <div className="approval-card">
    <div className="approval-card__head"><div className="approval-icon"><ShieldIcon /></div><div><p className="eyebrow">{busy ? "SECURE TRANSACTION" : "YOUR APPROVAL"}</p><h2>{busy ? progress.title : "Ready to place the order"}</h2><p>{busy ? progress.message : "Review the merchant-authoritative checkout below. This is the only point where your consent can move money."}</p></div></div>
    <div className="receipt">
      {proposal.lines.map((line) => <div className="receipt__item" key={line.offer_id}><span>{line.product_name}<small>{line.variant} · Qty {line.quantity}</small></span><strong>{formatMoney(line.line_total_minor, proposal.price.currency)}</strong></div>)}
      <div className="receipt__row"><span>Delivery · {proposal.delivery_option.label}<small>Promised {formatDate(proposal.delivery_option.estimated_delivery_date)}</small></span><strong>{formatMoney(proposal.price.shipping_minor, proposal.price.currency)}</strong></div>
      <div className="receipt__row"><span>Tax</span><strong>{proposal.price.tax_included ? "Included" : formatMoney(proposal.price.tax_minor, proposal.price.currency)}</strong></div>
      <div className="receipt__total"><span>Total</span><strong>{formatMoney(proposal.price.total_minor, proposal.price.currency)}</strong></div>
    </div>
    <div className="terms"><CheckIcon /><span><strong>{proposal.return_policy.window_days}-day returns</strong><small>{proposal.return_policy.description}</small></span></div>
    {busy ? <div className="approval-progress" role="status">
      <span className="approval-progress__pulse"><ClockIcon /></span>
      <span><strong>{sentenceCase(executionState ?? transaction.state)}</strong><small>{progress.detail}</small></span>
    </div> : <>
      <label className="consent"><input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} /><span className="custom-check"><CheckIcon /></span><span>I approve checkout <strong>{proposal.checkout_id}</strong> version {proposal.checkout_version} for exactly <strong>{formatMoney(proposal.price.total_minor, proposal.price.currency)}</strong>.</span></label>
      <button className="primary-button" disabled={!consent} onClick={onApprove}>Approve & place order<LockIcon /></button>
    </>}
    <details className="binding"><summary>View approval binding</summary><dl><div><dt>Merchant</dt><dd>{proposal.merchant_id}</dd></div><div><dt>Checkout version</dt><dd>v{proposal.checkout_version}</dd></div><div><dt>Expires</dt><dd>{formatDate(proposal.expires_at)}</dd></div><div><dt>Secure hash</dt><dd>{proposal.content_hash.slice(0, 18)}…</dd></div></dl></details>
  </div>;
}

function approvalProgress(state: TransactionState, totalMinor: number, currency: string) {
  const total = formatMoney(totalMinor, currency);
  const copy: Partial<Record<TransactionState, { title: string; message: string; detail: string }>> = {
    APPROVAL_PENDING: { title: "Recording your approval", message: "Binding your consent to this exact checkout before any payment action.", detail: "No funds have moved yet." },
    APPROVED: { title: "Exact checkout approved", message: "Your approval is recorded and cannot be reused for changed terms.", detail: "No funds have moved yet." },
    PAYMENT_AUTHORIZING: { title: `Authorizing ${total}`, message: "Requesting a transaction-scoped payment authorization for the exact approved total.", detail: "Payment is being authorized, not captured." },
    PAYMENT_AUTHORIZED: { title: "Payment authorized", message: `${total} is reserved for this checkout while the merchant confirms the order.`, detail: "Funds are reserved, not captured." },
    ORDER_COMMITTING: { title: "Waiting for merchant confirmation", message: "Submitting the approved checkout and scoped payment authority to the merchant.", detail: "The purchase is not complete without an order ID." },
    RECOVERY_REQUIRED: { title: "Verifying the merchant outcome", message: "The response was unclear, so the agent is checking for an existing order before any retry.", detail: "No duplicate order or charge will be attempted." },
    ORDER_CONFIRMED: { title: "Order confirmed", message: "The merchant returned an authoritative order. Payment can now be captured safely.", detail: "Merchant confirmation received." },
    PAYMENT_CAPTURED: { title: "Payment captured", message: `${total} was captured only after the merchant confirmed the order.`, detail: "The agent is handing off to fulfillment monitoring." },
    FULFILLING: { title: "Purchase complete", message: "The order is confirmed and the agent will continue monitoring fulfillment.", detail: "You can safely leave this page." },
  };
  return copy[state] ?? copy.APPROVAL_PENDING!;
}

function OrderCard({ order, payment, transaction, busy, onCancel, onAdvance, returnReason, setReturnReason, onReturn }: { order: Order; payment: Payment; transaction: AgentTransaction; busy: BusyAction; onCancel: () => void; onAdvance: () => void; returnReason: string; setReturnReason: (value: string) => void; onReturn: () => void }) {
  const resolved = transaction.state === "CANCELLED" || transaction.state === "REFUNDED";
  const canAdvance = ["CONFIRMED", "PROCESSING", "SHIPPED"].includes(order.state);
  return <div className="order-card">
    <div className={`order-hero ${resolved ? "order-hero--resolved" : ""}`}><div className="order-check"><CheckIcon /></div><div><p className="eyebrow">{resolved ? "RESOLUTION COMPLETE" : "ORDER CONFIRMED"}</p><h2>{resolved ? sentenceCase(transaction.state) : "It’s handled."}</h2><p>{resolved ? "The outcome remains linked to the original order and payment." : "The merchant confirmed your order and the payment was captured."}</p></div></div>
    <div className="order-grid"><div><PackageIcon /><span><small>Order</small><strong>{order.order_id}</strong></span></div><div><ShieldIcon /><span><small>Payment</small><strong>{sentenceCase(payment.status)}</strong></span></div><div><TruckIcon /><span><small>Delivery</small><strong>{formatDate(order.delivery_option.estimated_delivery_date)}</strong></span></div></div>
    {payment.refunded_amount_minor > 0 && <div className="refund-banner"><RefreshIcon /><span><strong>{formatMoney(payment.refunded_amount_minor, payment.currency)} refunded</strong><small>to the original simulated payment method</small></span></div>}
    {!resolved && <div className="order-actions">
      {canAdvance && <button className="secondary-button" onClick={onAdvance} disabled={Boolean(busy)}><TruckIcon /> {busy === "advancing" ? "Updating…" : `Demo: advance from ${sentenceCase(order.state)}`}</button>}
      {order.cancellable && <button className="danger-button" onClick={onCancel} disabled={Boolean(busy)}>{busy === "cancelling" ? "Cancelling…" : "Cancel order"}</button>}
      {order.state === "DELIVERED" && <div className="return-form"><label>Reason for return<input value={returnReason} onChange={(event) => setReturnReason(event.target.value)} /></label><button className="secondary-button" onClick={onReturn} disabled={Boolean(busy) || returnReason.trim().length < 3}>{busy === "returning" ? "Creating return…" : "Create return & refund"}</button></div>}
    </div>}
  </div>;
}

function Timeline({ transaction, events, activities, live }: { transaction: AgentTransaction; events: DomainEvent[]; activities: TransactionActivity[]; live: boolean }) {
  const [open, setOpen] = useState(live);
  const rawItems = activities.length > 0
    ? activities
    : transaction.transitions.map((transition, index): TransactionActivity => ({
        event_id: `legacy-${index}`,
        sequence: index + 1,
        transaction_id: transaction.transaction_id,
        kind: "transaction.transition",
        phase: "SYSTEM",
        status: "COMPLETED",
        title: sentenceCase(transition.to_state),
        message: transition.reason,
        actor_type: "agent",
        actor_id: transaction.agent_id,
        authority: "orchestrator",
        occurred_at: transition.occurred_at,
        data: {},
      }));
  const meaningfulTransitions = rawItems.filter((item) => {
    if (item.kind !== "transaction.transition") return false;
    const state = String(item.data.to_state ?? item.title.toUpperCase().replaceAll(" ", "_"));
    return !["INTENT_CAPTURED", "DISCOVERING", "CLARIFICATION_REQUIRED"].includes(state);
  });
  const firstActivity = rawItems[0];
  const firstMeaningfulTransition = meaningfulTransitions[0];
  const searchStatus = transaction.state === "FAILED"
    ? "FAILED"
    : transaction.state === "CLARIFICATION_REQUIRED"
    ? "WAITING"
    : meaningfulTransitions.length > 0
      ? "COMPLETED"
      : "STARTED";
  const searchingOffers: TransactionActivity | null = firstActivity ? {
    event_id: `${transaction.transaction_id}:searching-offers`,
    sequence: 0,
    transaction_id: transaction.transaction_id,
    kind: "ui.search_summary",
    phase: "DISCOVERY",
    status: searchStatus,
    title: "Searching offers",
    message: searchStatus === "STARTED"
      ? "The agent is searching connected merchants and comparing eligible offers."
      : searchStatus === "WAITING"
        ? "The search is waiting for the requested clarification."
        : searchStatus === "FAILED"
          ? "The offer search could not be completed."
          : "The agent searched connected merchants and evaluated the eligible offers.",
    actor_type: "agent",
    actor_id: transaction.agent_id,
    authority: "agent",
    occurred_at: firstMeaningfulTransition?.occurred_at ?? firstActivity.occurred_at,
    data: {},
  } : null;
  const items = searchingOffers
    ? [searchingOffers, ...meaningfulTransitions]
    : meaningfulTransitions;
  return <details className="timeline" open={open} onToggle={(event) => setOpen(event.currentTarget.open)}><summary><span><ClockIcon /><strong>{live ? "Agent is working" : "Transaction activity"}</strong><small>{items.length} commerce {items.length === 1 ? "step" : "steps"} · {events.length} merchant events</small></span><ChevronIcon /></summary><ol>{items.map((item) => <li key={item.event_id}><span className={`timeline__dot timeline__dot--${item.status.toLowerCase()}`}>{item.status === "STARTED" ? <ClockIcon /> : item.status === "FAILED" ? <XIcon /> : <CheckIcon />}</span><div><strong>{item.title}</strong><p>{item.message}</p><time>{sentenceCase(item.phase)} · {sentenceCase(item.status)} · {new Date(item.occurred_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</time></div></li>)}</ol><p className="correlation">Correlation ID · {transaction.transaction_id}</p></details>;
}

export default App;
