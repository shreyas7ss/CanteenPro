import { jsonResponse, supabaseRequest } from "../_lib.js";

export async function onRequestGet({ env }) {
  try {
    const response = await supabaseRequest(
      env,
      "menu_items?select=id,name,price,category&is_available=eq.true&order=category,name"
    );
    if (!response.ok) return jsonResponse({ error: "Menu is unavailable" }, 502);

    return jsonResponse(await response.json(), 200);
  } catch {
    return jsonResponse({ error: "Menu is unavailable" }, 500);
  }
}