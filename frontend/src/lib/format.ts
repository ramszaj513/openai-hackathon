export const CANONICAL_REQUEST =
  "Buy a Mac-compatible monitor for no more than 1,200 PLN, deliverable tomorrow, with at least a 30-day return window. Buy it if you are confident.";

export function formatMoney(amountMinor: number, currency: string): string {
  return new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
  }).format(amountMinor / 100);
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "Not specified";
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(new Date(`${value.length === 10 ? `${value}T12:00:00` : value}`));
}

export function sentenceCase(value: string): string {
  const words = value.toLowerCase().replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}
