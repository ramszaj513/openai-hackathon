import { FormEvent, useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  ArrowUpIcon,
  CheckIcon,
  ChevronIcon,
  ClockIcon,
  LockIcon,
  MenuIcon,
  MicrophoneIcon,
  MonitorIcon,
  PackageIcon,
  PlusIcon,
  RefreshIcon,
  ShieldIcon,
  SparkIcon,
  StopIcon,
  TruckIcon,
  XIcon,
} from "./components/Icons";
import { api, APIError } from "./lib/api";
import {
  startRealtimeTranscription,
  type RealtimeTranscriptionSession,
} from "./lib/realtimeTranscription";
import {
  ACTIVE_CONVERSATION_KEY,
  loadConversationIndex,
  pendingConversation,
  rememberConversation as upsertConversation,
  saveConversationIndex,
  type ConversationSummary,
} from "./lib/conversations";
import { CANONICAL_REQUEST, formatDate, formatMoney, sentenceCase } from "./lib/format";
import type { AgentTransaction, DomainEvent, Order, Payment } from "./types";

type BusyAction = "starting" | "approving" | "refreshing" | "cancelling" | "returning" | "advancing" | null;

function App() {
  const [draft, setDraft] = useState("");
  const [transaction, setTransaction] = useState<AgentTransaction | null>(null);
  const [order, setOrder] = useState<Order | null>(null);
  const [payment, setPayment] = useState<Payment | null>(null);
  const [events, setEvents] = useState<DomainEvent[]>([]);
  const [conversations, setConversations] = useState<ConversationSummary[]>(loadConversationIndex);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(() =>
    localStorage.getItem(ACTIVE_CONVERSATION_KEY),
  );
  const [online, setOnline] = useState<boolean | null>(null);
  const [busy, setBusy] = useState<BusyAction>(() =>
    localStorage.getItem(ACTIVE_CONVERSATION_KEY) ? "refreshing" : null,
  );
  const [error, setError] = useState<string | null>(null);
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);
  const [consent, setConsent] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [returnReason, setReturnReason] = useState("Changed my mind");
  const conversationEnd = useRef<HTMLDivElement>(null);
  const viewVersion = useRef(0);
  const activeConversationIdRef = useRef(activeConversationId);

  useEffect(() => {
    let active = true;
    void api.health().then((status) => {
      if (active) setOnline(status);
    });
    const saved = localStorage.getItem(ACTIVE_CONVERSATION_KEY);
    if (saved) {
      const view = viewVersion.current;
      void (async () => {
        try {
          const restored = await api.getTransaction(saved);
          const [restoredOrder, restoredPayment, restoredEvents] = await Promise.all([
            restored.order_id ? api.getOrder(restored.order_id) : Promise.resolve(null),
            restored.payment_id ? api.getPayment(restored.payment_id) : Promise.resolve(null),
            api.events(restored.transaction_id).catch(() => []),
          ]);
          if (!active || view !== viewVersion.current) return;
          setTransaction(restored);
          setOrder(restoredOrder);
          setPayment(restoredPayment);
          setEvents(restoredEvents);
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
    };
  }, []);

  useEffect(() => {
    conversationEnd.current?.scrollIntoView?.({ behavior: "smooth", block: "end" });
  }, [transaction, order, payment, busy, error]);

  async function hydrate(next: AgentTransaction, view: number) {
    const [nextOrder, nextPayment, nextEvents] = await Promise.all([
      next.order_id ? api.getOrder(next.order_id) : Promise.resolve(null),
      next.payment_id ? api.getPayment(next.payment_id) : Promise.resolve(null),
      api.events(next.transaction_id).catch(() => []),
    ]);
    if (view !== viewVersion.current) return;
    setOrder(nextOrder);
    setPayment(nextPayment);
    setEvents(nextEvents);
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
    setPendingMessage(null);
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
    setPendingMessage(intent);
    setError(null);
    setBusy("starting");
    try {
      const next = await api.start(request);
      await applyResult(next, view, replaceTransactionId);
      if (view === viewVersion.current) setDraft("");
    } catch (cause) {
      if (!clarification) {
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
        }
      }
      if (view === viewVersion.current) setPendingMessage(null);
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
    try {
      const next = await api.approve(transaction);
      await applyResult(next, view);
    } catch (cause) {
      showError(cause, view);
    } finally {
      if (view === viewVersion.current) setBusy(null);
    }
  }

  async function refresh() {
    if (!transaction) return;
    const view = viewVersion.current;
    setError(null);
    setBusy("refreshing");
    try {
      const next = await api.resume(transaction.transaction_id);
      await applyResult(next, view);
    } catch (cause) {
      showError(cause, view);
    } finally {
      if (view === viewVersion.current) setBusy(null);
    }
  }

  async function cancel() {
    if (!transaction) return;
    const view = viewVersion.current;
    setError(null);
    setBusy("cancelling");
    try {
      const next = await api.cancel(transaction);
      await applyResult(next, view);
    } catch (cause) {
      showError(cause, view);
    } finally {
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
    try {
      await api.setOrderState(order, state);
      const next = await api.resume(transaction.transaction_id);
      await applyResult(next, view);
    } catch (cause) {
      showError(cause, view);
    } finally {
      if (view === viewVersion.current) setBusy(null);
    }
  }

  async function createReturn() {
    if (!transaction || !order || returnReason.trim().length < 3) return;
    const view = viewVersion.current;
    setBusy("returning");
    setError(null);
    try {
      const items = Object.fromEntries(order.lines.map((line) => [line.product_id, line.quantity]));
      const next = await api.createReturn(transaction, items, returnReason.trim());
      await applyResult(next, view);
    } catch (cause) {
      showError(cause, view);
    } finally {
      if (view === viewVersion.current) setBusy(null);
    }
  }

  async function openConversation(transactionId: string) {
    if (transactionId === activeConversationId) {
      setSidebarOpen(false);
      return;
    }
    const view = ++viewVersion.current;
    activeConversationIdRef.current = transactionId;
    setActiveConversationId(transactionId);
    localStorage.setItem(ACTIVE_CONVERSATION_KEY, transactionId);
    setTransaction(null);
    setOrder(null);
    setPayment(null);
    setEvents([]);
    setBusy("refreshing");
    setError(null);
    setPendingMessage(null);
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
    localStorage.removeItem(ACTIVE_CONVERSATION_KEY);
    activeConversationIdRef.current = null;
    setActiveConversationId(null);
    setTransaction(null);
    setOrder(null);
    setPayment(null);
    setEvents([]);
    setError(null);
    setBusy(null);
    setPendingMessage(null);
    setConsent(false);
    setDraft("");
    setSidebarOpen(false);
  }

  const hasStarted = Boolean(transaction || busy);

  return (
    <div className="app-shell">
      <aside className={`sidebar ${sidebarOpen ? "sidebar--open" : ""}`}>
        <div className="sidebar__top">
          <div className="brand"><span className="brand__mark">a</span><span>arc</span></div>
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

        <div className="sidebar__bottom">
          <div className="trust-note"><ShieldIcon /><div><strong>Protected by design</strong><p>Approval is bound to the exact checkout. Arc never handles reusable card details.</p></div></div>
          <div className="api-status"><span className={`status-dot ${online ? "status-dot--online" : ""}`} /> <span>Commerce API</span><strong>{online === null ? "Checking" : online ? "Online" : "Offline"}</strong></div>
        </div>
      </aside>
      {sidebarOpen && <button className="scrim" aria-label="Close sidebar" onClick={() => setSidebarOpen(false)} />}

      <main className="main">
        <header className="topbar">
          <button className="icon-button menu-button" onClick={() => setSidebarOpen(true)} aria-label="Open sidebar"><MenuIcon /></button>
          <div className="topbar__title"><span>Commerce agent</span><small><span className="status-dot status-dot--online" /> Ready to act</small></div>
          {transaction && <button className="refresh-button" onClick={() => void refresh()} disabled={Boolean(busy)}><RefreshIcon /> Refresh</button>}
        </header>

        <section className={`conversation ${hasStarted ? "conversation--active" : ""}`} aria-live="polite">
          {!hasStarted && <Welcome onPrompt={() => setDraft(CANONICAL_REQUEST)} />}

          {transaction && <UserMessage>{transaction.raw_request}</UserMessage>}
          {busy === "refreshing" && !transaction && <Thinking label="Loading conversation…" />}

          {transaction?.state === "CLARIFICATION_REQUIRED" && transaction.intent && (
            <AssistantMessage>
              <div className="assistant-copy"><h2>I need one more detail</h2><p>{transaction.intent.clarification_questions.join(" ")}</p></div>
            </AssistantMessage>
          )}

          {pendingMessage && <UserMessage>{pendingMessage}</UserMessage>}
          {busy === "starting" && <Thinking />}

          {transaction?.state === "FAILED" && (
            <AssistantMessage tone="error"><div className="assistant-copy"><h2>I couldn't complete that request</h2><p>{transaction.last_error_message}</p></div></AssistantMessage>
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
              <ApprovalCard transaction={transaction} consent={consent} setConsent={setConsent} onApprove={() => void approve()} busy={busy === "approving"} />
            </AssistantMessage>
          )}

          {busy === "approving" && <Thinking label="Securing approval, authorizing payment, and confirming the order…" />}

          {transaction?.approval_id && <UserMessage compact>Approved this exact checkout.</UserMessage>}

          {order && payment && (
            <AssistantMessage>
              <OrderCard order={order} payment={payment} transaction={transaction!} busy={busy} onCancel={() => void cancel()} onAdvance={() => void advanceOrder()} returnReason={returnReason} setReturnReason={setReturnReason} onReturn={() => void createReturn()} />
            </AssistantMessage>
          )}

          {error && <AssistantMessage tone="error"><div className="assistant-copy"><h2>Something needs attention</h2><p>{error}</p><button className="text-button" onClick={() => setError(null)}>Dismiss</button></div></AssistantMessage>}

          {transaction && transaction.transitions.length > 0 && (
            <AssistantMessage subtle><Timeline transaction={transaction} events={events} /></AssistantMessage>
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
  const session = useRef<RealtimeTranscriptionSession | null>(null);
  const baseDraft = useRef("");
  const [voiceState, setVoiceState] = useState<"idle" | "connecting" | "recording" | "stopping">("idle");
  const [voiceError, setVoiceError] = useState<string | null>(null);

  useEffect(() => () => session.current?.dispose(), []);

  useLayoutEffect(() => {
    const input = textarea.current;
    if (!input) return;
    input.style.height = "0px";
    const nextHeight = Math.min(input.scrollHeight, 160);
    input.style.height = `${Math.max(38, nextHeight)}px`;
    input.style.overflowY = input.scrollHeight > 160 ? "auto" : "hidden";
  }, [draft]);

  async function toggleVoice() {
    if (voiceState === "recording") {
      setVoiceState("stopping");
      try {
        await session.current?.stop();
      } catch (cause) {
        setVoiceError(cause instanceof Error ? cause.message : "Could not finish voice input.");
      } finally {
        session.current = null;
        setVoiceState("idle");
      }
      return;
    }
    if (voiceState !== "idle") return;
    setVoiceError(null);
    setVoiceState("connecting");
    baseDraft.current = draft.trimEnd();
    try {
      session.current = await startRealtimeTranscription(
        (transcript) => {
          const separator = baseDraft.current && transcript ? " " : "";
          setDraft(`${baseDraft.current}${separator}${transcript}`);
        },
        (message) => setVoiceError(message),
      );
      setVoiceState("recording");
    } catch (cause) {
      setVoiceError(cause instanceof Error ? cause.message : "Could not start voice input.");
      setVoiceState("idle");
    }
  }

  return <div className="composer-wrap">
    {hasTransaction ? <button className="start-over" onClick={newConversation}><PlusIcon /> Start another transaction</button> : <form className="composer" onSubmit={submit}>
      <textarea ref={textarea} aria-label="Message the commerce agent" placeholder="Describe what you'd like me to buy…" value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} rows={1} disabled={disabled} />
      <button type="button" className={`voice-button ${voiceState === "recording" ? "voice-button--recording" : ""}`} disabled={disabled || voiceState === "connecting" || voiceState === "stopping"} aria-label={voiceState === "recording" ? "Stop voice input" : "Start voice input"} aria-pressed={voiceState === "recording"} onClick={() => void toggleVoice()}>{voiceState === "recording" ? <StopIcon /> : <MicrophoneIcon />}</button>
      <button type="submit" disabled={disabled || voiceState !== "idle" || !draft.trim()} aria-label="Send message"><ArrowUpIcon /></button>
    </form>}
    {voiceState !== "idle" && <p className="voice-status" role="status"><span />{voiceState === "recording" ? "Listening and transcribing live…" : voiceState === "connecting" ? "Connecting microphone…" : "Finishing transcript…"}</p>}
    {voiceError && <p className="voice-error" role="alert">{voiceError}</p>}
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

function ApprovalCard({ transaction, consent, setConsent, onApprove, busy }: { transaction: AgentTransaction; consent: boolean; setConsent: (value: boolean) => void; onApprove: () => void; busy: boolean }) {
  const proposal = transaction.proposal!;
  return <div className="approval-card">
    <div className="approval-card__head"><div className="approval-icon"><ShieldIcon /></div><div><p className="eyebrow">YOUR APPROVAL</p><h2>Ready to place the order</h2><p>Review the merchant-authoritative checkout below. This is the only point where your consent can move money.</p></div></div>
    <div className="receipt">
      {proposal.lines.map((line) => <div className="receipt__item" key={line.offer_id}><span>{line.product_name}<small>{line.variant} · Qty {line.quantity}</small></span><strong>{formatMoney(line.line_total_minor, proposal.price.currency)}</strong></div>)}
      <div className="receipt__row"><span>Delivery · {proposal.delivery_option.label}<small>Promised {formatDate(proposal.delivery_option.estimated_delivery_date)}</small></span><strong>{formatMoney(proposal.price.shipping_minor, proposal.price.currency)}</strong></div>
      <div className="receipt__row"><span>Tax</span><strong>{proposal.price.tax_included ? "Included" : formatMoney(proposal.price.tax_minor, proposal.price.currency)}</strong></div>
      <div className="receipt__total"><span>Total</span><strong>{formatMoney(proposal.price.total_minor, proposal.price.currency)}</strong></div>
    </div>
    <div className="terms"><CheckIcon /><span><strong>{proposal.return_policy.window_days}-day returns</strong><small>{proposal.return_policy.description}</small></span></div>
    <label className="consent"><input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} /><span className="custom-check"><CheckIcon /></span><span>I approve checkout <strong>{proposal.checkout_id}</strong> version {proposal.checkout_version} for exactly <strong>{formatMoney(proposal.price.total_minor, proposal.price.currency)}</strong>.</span></label>
    <button className="primary-button" disabled={!consent || busy} onClick={onApprove}>{busy ? "Confirming securely…" : "Approve & place order"}<LockIcon /></button>
    <details className="binding"><summary>View approval binding</summary><dl><div><dt>Merchant</dt><dd>{proposal.merchant_id}</dd></div><div><dt>Checkout version</dt><dd>v{proposal.checkout_version}</dd></div><div><dt>Expires</dt><dd>{formatDate(proposal.expires_at)}</dd></div><div><dt>Secure hash</dt><dd>{proposal.content_hash.slice(0, 18)}…</dd></div></dl></details>
  </div>;
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

function Timeline({ transaction, events }: { transaction: AgentTransaction; events: DomainEvent[] }) {
  return <details className="timeline"><summary><span><ClockIcon /><strong>Transaction activity</strong><small>{transaction.transitions.length} state changes · {events.length} merchant events</small></span><ChevronIcon /></summary><ol>{transaction.transitions.map((item, index) => <li key={`${item.occurred_at}-${index}`}><span className="timeline__dot"><CheckIcon /></span><div><strong>{sentenceCase(item.to_state)}</strong><p>{item.reason}</p><time>{new Date(item.occurred_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</time></div></li>)}</ol><p className="correlation">Correlation ID · {transaction.transaction_id}</p></details>;
}

export default App;
