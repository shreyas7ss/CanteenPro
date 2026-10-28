import { buildPaymentLink, jsonResponse, supabaseRequest } from "../_lib.js";

export async function onRequestGet({ request, params, env }) {
  try {
    const query = new URLSearchParams({
      select: "total_amount",
      merchant_transaction_id: `eq.${params.txn_id}`,
      limit: "1",
    });
    const response = await supabaseRequest(env, `orders?${query}`);
    if (!response.ok) return jsonResponse({ error: "Payment details unavailable" }, 502);
    const [order] = await response.json();
    if (!order) return jsonResponse({ error: "Order not found" }, 404);

    const note = `LineZero order ${params.txn_id.slice(0, 8)}`;
    const paymentLink = buildPaymentLink(env, order.total_amount, params.txn_id, note);
    return Response.redirect(paymentLink, 302);
  } catch {
    return jsonResponse({ error: "Payment details unavailable" }, 500);
  }
}