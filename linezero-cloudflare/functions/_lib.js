export function jsonResponse(value, status = 200) {
  return Response.json(value, {
    status,
    headers: { "Cache-Control": "no-store" },
  });
}

export async function supabaseRequest(env, path, options = {}) {
  const baseUrl = env.SUPABASE_URL?.replace(/\/$/, "");
  const key = env.SUPABASE_SERVICE_ROLE_KEY;
  if (!baseUrl || !key) throw new Error("Supabase configuration is missing");

  return fetch(`${baseUrl}/rest/v1/${path}`, {
    ...options,
    headers: {
      apikey: key,
      Authorization: `Bearer ${key}`,
      "Content-Type": "application/json",
      ...options.headers,
    },
  });
}

export function buildPaymentLink(env, amount, transactionId, note) {
  const values = {
    pa: env.UPI_VPA,
    pn: env.UPI_PAYEE_NAME,
    am: Number(amount).toFixed(2),
    tr: transactionId,
    tn: note,
    cu: "INR",
  };
  const query = Object.entries(values)
    .map(([key, value]) => `${key}=${encodeURIComponent(value)}`)
    .join("&");
  return `upi://pay?${query}`;
}