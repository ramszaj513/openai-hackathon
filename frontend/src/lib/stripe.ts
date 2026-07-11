export interface StripeCardElement {
  mount(target: HTMLElement): void;
  destroy(): void;
  on(event: "change", handler: (event: StripeCardChangeEvent) => void): void;
}

interface StripeCardChangeEvent {
  complete: boolean;
  error?: { message: string };
}

export interface StripeClient {
  elements(): {
    create(
      type: "card",
      options: Record<string, unknown>,
    ): StripeCardElement;
  };
  createPaymentMethod(options: {
    type: "card";
    card: StripeCardElement;
    billing_details?: { name?: string };
  }): Promise<{
    paymentMethod?: { id: string };
    error?: { message?: string };
  }>;
}

declare global {
  interface Window {
    Stripe?: (publishableKey: string) => StripeClient;
  }
}

let stripeJsPromise: Promise<void> | null = null;

function loadStripeJs(): Promise<void> {
  if (window.Stripe) return Promise.resolve();
  if (stripeJsPromise) return stripeJsPromise;
  stripeJsPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(
      'script[src="https://js.stripe.com/v3/"]',
    );
    const script = existing ?? document.createElement("script");
    const loaded = () => (window.Stripe ? resolve() : reject(new Error("Stripe.js did not load.")));
    script.addEventListener("load", loaded, { once: true });
    script.addEventListener(
      "error",
      () => reject(new Error("Could not load the secure Stripe payment form.")),
      { once: true },
    );
    if (!existing) {
      script.src = "https://js.stripe.com/v3/";
      script.async = true;
      document.head.appendChild(script);
    }
  });
  return stripeJsPromise;
}

export async function createStripeClient(publishableKey: string): Promise<StripeClient> {
  await loadStripeJs();
  if (!window.Stripe) throw new Error("Stripe.js is unavailable.");
  return window.Stripe(publishableKey);
}
