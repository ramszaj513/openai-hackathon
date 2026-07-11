import { useEffect, useRef, useState } from "react";
import { LockIcon } from "./Icons";
import { createStripeClient, type StripeCardElement, type StripeClient } from "../lib/stripe";

interface StripeCardFormProps {
  publishableKey: string;
  consent: boolean;
  busy: boolean;
  onApprove: (paymentMethodId: string) => void;
}

export function StripeCardForm({
  publishableKey,
  consent,
  busy,
  onApprove,
}: StripeCardFormProps) {
  const mountPoint = useRef<HTMLDivElement>(null);
  const stripe = useRef<StripeClient | null>(null);
  const card = useRef<StripeCardElement | null>(null);
  const [cardholderName, setCardholderName] = useState("");
  const [ready, setReady] = useState(false);
  const [complete, setComplete] = useState(false);
  const [tokenizing, setTokenizing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    let mountedCard: StripeCardElement | null = null;
    void createStripeClient(publishableKey)
      .then((client) => {
        if (!active || !mountPoint.current) return;
        stripe.current = client;
        mountedCard = client.elements().create("card", {
          hidePostalCode: true,
          style: {
            base: {
              color: "#24342e",
              fontFamily: 'Inter, system-ui, sans-serif',
              fontSize: "14px",
              "::placeholder": { color: "#909793" },
            },
            invalid: { color: "#a24431" },
          },
        });
        card.current = mountedCard;
        mountedCard.on("change", (event) => {
          if (!active) return;
          setComplete(event.complete);
          setError(event.error?.message ?? null);
        });
        mountedCard.mount(mountPoint.current);
        setReady(true);
      })
      .catch((cause: unknown) => {
        if (active) setError(cause instanceof Error ? cause.message : "Stripe.js is unavailable.");
      });
    return () => {
      active = false;
      mountedCard?.destroy();
      stripe.current = null;
      card.current = null;
    };
  }, [publishableKey]);

  async function submit() {
    if (!stripe.current || !card.current || !consent || !complete || busy || tokenizing) return;
    setTokenizing(true);
    setError(null);
    try {
      const result = await stripe.current.createPaymentMethod({
        type: "card",
        card: card.current,
        billing_details: cardholderName.trim() ? { name: cardholderName.trim() } : undefined,
      });
      if (result.error) {
        setError(result.error.message ?? "Stripe could not validate these payment details.");
        return;
      }
      if (!result.paymentMethod?.id) {
        setError("Stripe did not return a payment method.");
        return;
      }
      onApprove(result.paymentMethod.id);
    } finally {
      setTokenizing(false);
    }
  }

  return <div className="stripe-payment">
    <div className="stripe-payment__heading"><span>Card details <em>TEST SANDBOX</em></span><small><LockIcon /> Secured by Stripe</small></div>
    <div className="stripe-payment__test-card"><span>Successful test card</span><strong>4242 4242 4242 4242</strong><small>Any future expiry · any 3-digit CVC</small></div>
    <label className="stripe-payment__name">Name on card<input value={cardholderName} onChange={(event) => setCardholderName(event.target.value)} autoComplete="cc-name" placeholder="Cardholder name" /></label>
    <div className={`stripe-card-element ${error ? "stripe-card-element--error" : ""}`} ref={mountPoint} aria-label="Card number, expiry, and CVC" />
    {error && <p className="stripe-payment__error" role="alert">{error}</p>}
    <p className="stripe-payment__note">Use test data only. Real cards are intentionally declined by Stripe sandbox. Card details go directly to Stripe and never pass through this application.</p>
    <button className="primary-button" disabled={!consent || !ready || !complete || busy || tokenizing} onClick={() => void submit()}>{busy || tokenizing ? "Confirming securely…" : "Pay with card & place order"}<LockIcon /></button>
  </div>;
}
