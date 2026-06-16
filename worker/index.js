/**
 * TX Construction Intelligence — Cloudflare Worker
 *
 * POST /ping   — Gumroad webhook, stores subscriber emails in KV
 * GET  /subs   — Returns subscriber list (protected by secret query param)
 *
 * KV namespace binding: TX_INTEL_SUBS
 * Environment variable:  WORKER_SECRET
 */

export default {
  async fetch(request, env) {
    try {
      const url = new URL(request.url);

      if (request.method === "POST" && url.pathname === "/ping") {
        return await handleGumroadPing(request, env);
      }

      if (request.method === "GET" && url.pathname === "/subs") {
        return await handleGetSubscribers(request, env, url);
      }

      return new Response("TX Construction Intel Worker — OK", { status: 200 });

    } catch (err) {
      return new Response(`Worker error: ${err.message}`, { status: 500 });
    }
  },
};

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

    const email     = data.email || data.purchaser_email || "";
    const refunded  = data.refunded === "true" || data.refunded === true;
    const cancelled = data.cancelled === "true" || data.cancelled === true;

    if (!email) {
      return new Response("No email in ping", { status: 400 });
    }

    const variant = (data.variants || data.option || "").toLowerCase();
    const tier    = (variant.includes("pro") || variant.includes("49")) ? "tier3" : "tier2";

    if (refunded || cancelled) {
      await env.TX_INTEL_SUBS.delete(`sub:${email}`);
    } else {
      const record = JSON.stringify({
        email,
        tier,
        subscribed_at: new Date().toISOString(),
        sale_id: data.sale_id || data.order_number || "",
      });
      await env.TX_INTEL_SUBS.put(`sub:${email}`, record);
    }

    return new Response("OK", { status: 200 });

  } catch (err) {
    return new Response(`Ping error: ${err.message}`, { status: 500 });
  }
}

async function handleGetSubscribers(request, env, url) {
  // Auth: compare query param secret against env variable
  const provided = url.searchParams.get("secret") || "";
  const expected = env.WORKER_SECRET || "";

  // If no secret is configured yet, return a helpful message
  if (!expected) {
    return new Response("WORKER_SECRET not configured on this Worker", { status: 500 });
  }

  if (provided !== expected) {
    return new Response("Unauthorized", { status: 401 });
  }

  try {
    const list        = await env.TX_INTEL_SUBS.list({ prefix: "sub:" });
    const subscribers = [];

    for (const key of list.keys) {
      const val = await env.TX_INTEL_SUBS.get(key.name);
      if (val) {
        try { subscribers.push(JSON.parse(val)); } catch (_) {}
      }
    }

    return new Response(JSON.stringify({ success: true, subscribers }), {
      headers: { "Content-Type": "application/json" },
    });

  } catch (err) {
    return new Response(`KV error: ${err.message}`, { status: 500 });
  }
}
