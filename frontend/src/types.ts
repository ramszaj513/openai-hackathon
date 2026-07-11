export type TransactionState =
  | "INTENT_CAPTURED"
  | "CLARIFICATION_REQUIRED"
  | "DISCOVERING"
  | "OFFER_SELECTED"
  | "CHECKOUT_DRAFT"
  | "APPROVAL_PENDING"
  | "APPROVED"
  | "PAYMENT_AUTHORIZING"
  | "PAYMENT_AUTHORIZED"
  | "ORDER_COMMITTING"
  | "RECOVERY_REQUIRED"
  | "ORDER_CONFIRMED"
  | "PAYMENT_CAPTURED"
  | "FULFILLING"
  | "DELIVERED"
  | "CANCELLATION_REQUESTED"
  | "CANCELLED"
  | "RETURN_REQUESTED"
  | "REFUND_PENDING"
  | "REFUNDED"
  | "FAILED";

export interface Money {
  amount_minor: number;
  currency: string;
}

export interface PriceBreakdown {
  subtotal_minor: number;
  discount_minor: number;
  shipping_minor: number;
  tax_minor: number;
  fees_minor: number;
  total_minor: number;
  currency: string;
  tax_included: boolean;
}

export interface DeliveryOption {
  delivery_option_id: string;
  label: string;
  price_minor: number;
  estimated_delivery_date: string;
}

export interface ReturnPolicy {
  returnable: boolean;
  window_days: number;
  restocking_fee_minor: number;
  description: string;
}

export interface CheckoutLine {
  offer_id: string;
  offer_version: number;
  product_id: string;
  product_name: string;
  product_category: string;
  variant: string;
  quantity: number;
  unit_price: Money;
  line_total_minor: number;
}

export interface Offer {
  offer_id: string;
  merchant_id: string;
  product: {
    product_id: string;
    name: string;
    category: string;
    brand: string;
    description: string;
    attributes: Record<string, string | boolean | number>;
  };
  variant: string;
  unit_price: Money;
  available_quantity: number;
  delivery_options: DeliveryOption[];
  return_policy: ReturnPolicy;
  version: number;
  expires_at: string;
}

export interface CheckoutProposal {
  proposal_id: string;
  transaction_id: string;
  checkout_id: string;
  checkout_version: number;
  merchant_id: string;
  lines: CheckoutLine[];
  delivery_option: DeliveryOption;
  price: PriceBreakdown;
  return_policy: ReturnPolicy;
  selection_reason: string;
  satisfied_constraints: string[];
  disclosed_compromises: string[];
  content_hash: string;
  status: string;
  expires_at: string;
}

export interface AgentTransaction {
  transaction_id: string;
  user_id: string;
  agent_id: string;
  raw_request: string;
  state: TransactionState;
  intent: {
    product_query: string;
    category: string;
    quantity: number;
    max_budget_minor: number | null;
    currency: string;
    required_attributes: Record<string, string | boolean | number>;
    latest_delivery_date: string | null;
    minimum_return_window_days: number | null;
    missing_required_fields: string[];
    clarification_questions: string[];
  } | null;
  selection: {
    selected_offer_id: string | null;
    confidence: number;
    selection_reason: string;
    satisfied_constraints: string[];
    disclosed_compromises: string[];
    rejected_offers: Array<{ offer_id: string; reasons: string[] }>;
  } | null;
  selected_offer: Offer | null;
  proposal: CheckoutProposal | null;
  approval_id: string | null;
  payment_id: string | null;
  order_id: string | null;
  return_id: string | null;
  last_error_code: string | null;
  last_error_message: string | null;
  transitions: Array<{
    from_state: TransactionState | null;
    to_state: TransactionState;
    occurred_at: string;
    reason: string;
  }>;
  created_at: string;
  updated_at: string;
}

export interface Order {
  order_id: string;
  transaction_id: string;
  checkout_id: string;
  merchant_id: string;
  state: "CONFIRMED" | "PROCESSING" | "SHIPPED" | "DELIVERED" | "CANCELLED";
  lines: CheckoutLine[];
  delivery_option: DeliveryOption;
  price: PriceBreakdown;
  return_policy: ReturnPolicy;
  cancellable: boolean;
  returnable_until: string | null;
}

export interface Payment {
  payment_id: string;
  provider: string;
  provider_reference: string;
  transaction_id: string;
  status: "AUTHORIZED" | "CAPTURED" | "VOIDED" | "DECLINED" | "PARTIALLY_REFUNDED" | "REFUNDED";
  authorized_amount_minor: number;
  captured_amount_minor: number;
  refunded_amount_minor: number;
  currency: string;
  order_id: string | null;
}

export interface DomainEvent {
  event_id: string;
  event_type: string;
  occurred_at: string;
  transaction_id: string;
}
