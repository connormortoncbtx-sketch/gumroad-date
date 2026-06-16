/**
 * TX Construction Intelligence — Cloudflare Worker
 *
 * Handles two routes:
 *   POST /ping     — Gumroad webhook, stores subscriber emails in KV
 *   GET  /subs     — GitHub Actions calls this to get the email list
 *
 * KV namespace: TX_INTEL_SUBS
 * Secrets (set via wrangler or Cloudflare dashboard):
 *   WORKER_SECRET  — shared secret so only your pipeline can call /subs
 */

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === "POST" && url.pathname === "/ping") {
      return handleGumroadPing(request, env);
    }

    if (request.method === "GET" && url.pathname === "/subs") {
      return handleGetSubscribers(request, env);
    }

    return new Response("TX Construction Intel Worker", { status: 200 });
  },
};

// ── Gumroad Ping handler ───────────────────────────────────────────────────

async function handleGumroadPing(request, env) {
  try {
    const contentType = request.headers.get("content-type") || "";
    let data = {};

    if (contentType.includes("application/json")) {
      data = await request.json();
    } else {
      const text = await request.text();
      const params = new URLSearchParams(text);
      for (const [k, v] of params) data[k] = v;
    }

    const email      = data.email || data.purchaser_email || "";
    const saleType   = data.sale_timestamp ? "sale" : (data.cancelled ? "cancel" : "unknown");
    const refunded   = data.refunded === "true" || data.refunded === true;
    const cancelled  = data.cancelled === "true" || data.cancelled === true;

    if (!email) {
      return new Response("No email found in ping", { status: 400 });
    }

    // Determine the subscriber's tier from the Gumroad variant
    const variant = (data.variants || data.option || "").toLowerCase();
    let tier = "tier2";
    if (variant.includes("pro") || variant.includes("49")) tier = "tier3";

    if (refunded || cancelled) {
      // Remove subscriber
      await env.TX_INTEL_SUBS.delete(`sub:${email}`);
      console.log(`Removed subscriber: ${email} (${saleType})`);
    } else {
      // Add/update subscriber
      const record = {
        email,
        tier,
        subscribed_at: new Date().toISOString(),
        sale_id: data.sale_id || data.order_number || "",
      };
      await env.TX_INTEL_SUBS.put(`sub:${email}`, JSON.stringify(record));
      console.log(`Added subscriber: ${email} → ${tier}`);
    }

    return new Response("OK", { status: 200 });
  } catch (err) {
    console.error("Ping error:", err);
    return new Response("Error processing ping", { status: 500 });
  }
}

// ── Get subscribers list ───────────────────────────────────────────────────

async function handleGetSubscribers(request, env) {
  // Verify shared secret
  const secret = url.searchParams.get("secret");
  if (!secret || secret !== env.WORKER_SECRET) {
    return new Response("Unauthorized", { status: 401 });
  }

  try {
    const list = await env.TX_INTEL_SUBS.list({ prefix: "sub:" });
    const subscribers = [];

    for (const key of list.keys) {
      const val = await env.TX_INTEL_SUBS.get(key.name);
      if (val) subscribers.push(JSON.parse(val));
    }

    return new Response(JSON.stringify({ success: true, subscribers }), {
      headers: { "Content-Type": "application/json" },
    });
  } catch (err) {
    console.error("Get subs error:", err);
    return new Response("Error fetching subscribers", { status: 500 });
  }
}
