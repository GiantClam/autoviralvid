import { getPlanCatalog } from "./plan-catalog";

type StripeCheckoutResult = {
  sessionId: string;
  checkoutUrl: string;
  status: string;
};

function getStripeSecretKey() {
  const secret = process.env.STRIPE_SECRET_KEY;
  if (!secret) {
    throw new Error("Stripe secret key is not configured");
  }
  return secret;
}

function ensureStripePrice(planKey: string) {
  const catalog = getPlanCatalog();
  const plan = catalog[planKey as keyof typeof catalog];
  const priceId = plan?.providerPlanIds?.stripe?.trim();
  if (!plan || !priceId) {
    throw new Error(`Invalid Stripe plan: ${planKey}`);
  }
  return priceId;
}

export async function createStripeCheckoutSession(
  planKey: string,
  successUrl: string,
  cancelUrl: string,
  customerEmail?: string,
  userId?: string,
): Promise<StripeCheckoutResult> {
  const secretKey = getStripeSecretKey();
  const priceId = ensureStripePrice(planKey);

  const payload = new URLSearchParams();
  payload.set("mode", "subscription");
  payload.set("line_items[0][price]", priceId);
  payload.set("line_items[0][quantity]", "1");
  payload.set("success_url", successUrl);
  payload.set("cancel_url", cancelUrl);
  if (customerEmail) {
    payload.set("customer_email", customerEmail);
  }
  if (userId) {
    payload.set("client_reference_id", userId);
    payload.set("metadata[userId]", userId);
  }
  payload.set("metadata[plan]", planKey);

  const response = await fetch("https://api.stripe.com/v1/checkout/sessions", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${secretKey}`,
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: payload.toString(),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Stripe checkout session failed: ${response.status} ${text}`);
  }

  const data = (await response.json()) as {
    id?: string;
    url?: string;
    status?: string;
  };

  if (!data.id || !data.url) {
    throw new Error("Stripe checkout session response is missing id or url");
  }

  return {
    sessionId: data.id,
    checkoutUrl: data.url,
    status: data.status || "open",
  };
}
