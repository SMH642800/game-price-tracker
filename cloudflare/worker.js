/**
 * Experimental Cloudflare Worker entry point for Discord HTTP Interactions.
 *
 * This is intentionally a safe foundation, not a production replacement for
 * bot.py yet. Command parity and tests must be completed before deployment.
 */
const DISCORD_PING = 1;
const APPLICATION_COMMAND = 2;

function json(data, status = 200, headers = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", ...headers },
  });
}

function hexToBytes(hex) {
  if (!/^[0-9a-f]+$/i.test(hex) || hex.length % 2 !== 0) {
    throw new Error("Invalid hex signature");
  }
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < bytes.length; i += 1) {
    bytes[i] = Number.parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  }
  return bytes;
}

async function verifyDiscordRequest(request, rawBody, publicKeyHex) {
  const signature = request.headers.get("X-Signature-Ed25519");
  const timestamp = request.headers.get("X-Signature-Timestamp");
  if (!signature || !timestamp || !publicKeyHex) return false;

  try {
    const key = await crypto.subtle.importKey(
      "raw",
      hexToBytes(publicKeyHex),
      { name: "Ed25519" },
      false,
      ["verify"],
    );
    return await crypto.subtle.verify(
      { name: "Ed25519" },
      key,
      hexToBytes(signature),
      new TextEncoder().encode(timestamp + rawBody),
    );
  } catch {
    return false;
  }
}

function interactionMessage(content, ephemeral = true) {
  return {
    type: 4,
    data: { content, flags: ephemeral ? 64 : 0 },
  };
}

async function handleInteraction(interaction, env) {
  if (interaction.type === DISCORD_PING) return { type: 1 };

  if (interaction.type !== APPLICATION_COMMAND) {
    return interactionMessage("目前不支援這種 Discord 互動。");
  }

  const command = interaction.data?.name;
  const userId = interaction.member?.user?.id ?? interaction.user?.id;

  if (command === "ping") {
    return interactionMessage("🏓 Pong！Cloudflare Worker 已收到 Discord 指令。");
  }

  if (command === "admincheck") {
    const isAdmin = Boolean(env.DISCORD_ADMIN_ID && userId === env.DISCORD_ADMIN_ID);
    return interactionMessage(
      isAdmin ? "✅ 你已通過管理員驗證。" : "⛔ 你沒有 Bot 管理員權限。",
    );
  }

  if (command === "help") {
    return interactionMessage(
      "🎮 Game Price Tracker（Cloudflare 遷移測試版）\n" +
      "目前此分支只驗證 HTTP Interactions 的基本流程；/list、/add、/remove、/lookup 與 autocomplete 尚未移植完成，請勿用於正式伺服器。",
    );
  }

  return interactionMessage(
    "此指令尚未在 Cloudflare 遷移分支完成。請繼續使用目前的正式 Bot。",
  );
}

export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const rawBody = await request.text();
    const valid = await verifyDiscordRequest(request, rawBody, env.DISCORD_PUBLIC_KEY);
    if (!valid) return new Response("Invalid request signature", { status: 401 });

    let interaction;
    try {
      interaction = JSON.parse(rawBody);
    } catch {
      return new Response("Invalid JSON", { status: 400 });
    }

    try {
      return json(await handleInteraction(interaction, env));
    } catch (error) {
      console.error("Interaction handler failed", error?.name ?? "Error");
      // Keep internal details and secrets out of Discord's response.
      return json(interactionMessage("❌ 指令處理失敗，請稍後再試。"));
    }
  },
};
