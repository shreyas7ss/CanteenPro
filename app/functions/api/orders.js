import { buildPaymentLink, jsonResponse, supabaseRequest } from "../_lib.js";

async function cancelPendingOrder(env, orderId) {
  await supabaseRequest(env, `orders?id=eq.${encodeURIComponent(orderId)}&status=eq.pending_payment`, {
    method: "PATCH",
    body: JSON.stringify({ status: "cancelled" }),
  });
}

export async function onRequestPost({ request, env }) {
  let body;
  try {
    body = await request.json();
  } catch {
    return jsonResponse({ error: "Invalid request" }, 400);
  }

  const studentName = String(body.student_name || "").trim().slice(0, 120);
  const rollNumber = String(body.roll_number || "").trim().slice(0, 80);
  if (!studentName || !rollNumber) {
    return jsonResponse({ error: "Student name and roll number are required" }, 400);
  }
  if (!Array.isArray(body.items) || body.items.length === 0 || body.items.length > 30) {
    return jsonResponse({ error: "Cart is empty or invalid" }, 400);
  }

  const quantities = new Map();
  for (const line of body.items) {
    const quantity = Number(line.quantity);
    if (typeof line.menu_item_id !== "string" || !Number.isInteger(quantity) || quantity < 1 || quantity > 20) {
      return jsonResponse({ error: "Invalid cart item" }, 400);
    }
    quantities.set(line.menu_item_id, (quantities.get(line.menu_item_id) || 0) + quantity);
  }

  try {
    if (!env.UPI_VPA || !env.UPI_PAYEE_NAME) throw new Error("UPI configuration is missing");
    const menuResponse = await supabaseRequest(
      env,
      "menu_items?select=id,name,price,category&is_available=eq.true&order=category,name"
    );
    if (!menuResponse.ok) return jsonResponse({ error: "Could not load current menu" }, 502);
    const menuItems = await menuResponse.json();
    const menuById = new Map(menuItems.map((item) => [item.id, item]));
    const orderItems = [];
    let totalCents = 0;

    for (const [menuItemId, quantity] of quantities) {
      const item = menuById.get(menuItemId);
      if (!item) return jsonResponse({ error: "An item is no longer available" }, 400);
      const unitPriceCents = Math.round(Number(item.price) * 100);
      totalCents += unitPriceCents * quantity;
      orderItems.push({
        menu_item_id: item.id,
        item_name: item.name,
        unit_price: (unitPriceCents / 100).toFixed(2),
        quantity,
      });
    }

    const pickupSlot = ["Right now", "10:30 AM (today)"].includes(body.pickup_slot)
      ? body.pickup_slot
      : "Right now";
    const transactionId = crypto.randomUUID();
    const note = `LineZero order ${transactionId.slice(0, 8)}`;
    const orderResponse = await supabaseRequest(env, "orders?select=id", {
      method: "POST",
      headers: { Prefer: "return=representation" },
      body: JSON.stringify({
        student_name: studentName,
        roll_number: rollNumber,
        total_amount: (totalCents / 100).toFixed(2),
        merchant_transaction_id: transactionId,
        status: "pending_payment",
        notes: `Pickup: ${pickupSlot}`,
      }),
    });
    if (!orderResponse.ok) return jsonResponse({ error: "Could not create order" }, 502);
    const order = (await orderResponse.json())[0];

    const itemsResponse = await supabaseRequest(env, "order_items", {
      method: "POST",
      body: JSON.stringify(orderItems.map((item) => ({ ...item, order_id: order.id }))),
    });
    if (!itemsResponse.ok) {
      await cancelPendingOrder(env, order.id);
      return jsonResponse({ error: "Could not save order items" }, 502);
    }

    const paymentUrl = new URL(`/pay/${transactionId}`, request.url).toString();
    return jsonResponse({ order_id: order.id, total: totalCents / 100, payment_url: paymentUrl });
  } catch {
    return jsonResponse({ error: "Could not place order" }, 500);
  }
}