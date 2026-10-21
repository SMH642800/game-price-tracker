/**
 * Experimental Discord HTTP Interactions Worker.
 * Uses GitHub as the shared watchlist store; scheduled price checks remain in GitHub Actions.
 */
const DISCORD_PING = 1;
const APPLICATION_COMMAND = 2;
const AUTOCOMPLETE = 4;
const EPHEMERAL = 64;
const REPO = "SMH642800/game-price-tracker";
const BRANCH = "feature/cloudflare-interactions";
const GH_API = `https://api.github.com/repos/${REPO}/contents`;
const GH_HEADERS = (env) => ({
  Authorization: `Bearer ${env.GITHUB_TOKEN}`,
  Accept: "application/vnd.github+json",
  "X-GitHub-Api-Version": "2022-11-28",
  "Content-Type": "application/json",
});

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}
function hexToBytes(hex) {
  if (!/^[0-9a-f]+$/i.test(hex) || hex.length % 2) throw new Error("invalid hex");
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  return out;
}
async function verifyDiscordRequest(request, body, publicKey) {
  const sig = request.headers.get("X-Signature-Ed25519");
  const ts = request.headers.get("X-Signature-Timestamp");
  if (!sig || !ts || !publicKey) return false;
  try {
    const key = await crypto.subtle.importKey("raw", hexToBytes(publicKey), { name: "Ed25519" }, false, ["verify"]);
    return await crypto.subtle.verify({ name: "Ed25519" }, key, hexToBytes(sig), new TextEncoder().encode(ts + body));
  } catch { return false; }
}
const reply = (content, ephemeral = true) => ({ type: 4, data: { content: String(content).slice(0, 2000), flags: ephemeral ? EPHEMERAL : 0 } });
const defer = () => ({ type: 5, data: { flags: EPHEMERAL } });
const opt = (interaction, name) => (interaction.data?.options || []).find(o => o.name === name)?.value;
const userIdOf = (i) => i.member?.user?.id ?? i.user?.id;
const isAdmin = (i, env) => Boolean(env.DISCORD_ADMIN_ID && userIdOf(i) === env.DISCORD_ADMIN_ID);
const platformOf = g => String(g.platform || "steam").toLowerCase();
const productIdOf = g => String(g.product_id ?? g.app_id ?? "").trim();
const SUPPORTED = { steam: "Steam", ps5: "PlayStation 5", ns: "Nintendo Switch", ns2: "Nintendo Switch 2", nintendo: "Nintendo Switch／Switch 2" };

async function githubGet(env, path) {
  if (!env.GITHUB_TOKEN) throw new Error("GITHUB_TOKEN is not configured");
  const response = await fetch(`${GH_API}/${path}?ref=${encodeURIComponent(env.GITHUB_BRANCH || BRANCH)}`, { headers: GH_HEADERS(env) });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`GitHub read failed: HTTP ${response.status}`);
  const payload = await response.json();
  const decoded = atob(payload.content.replace(/\s/g, ""));
  const bytes = Uint8Array.from(decoded, c => c.charCodeAt(0));
  return { data: JSON.parse(new TextDecoder().decode(bytes)), sha: payload.sha };
}
async function githubPut(env, path, data, sha, message) {
  const bytes = new TextEncoder().encode(JSON.stringify(data, null, 2) + "\n");
  let binary = "";
  for (const b of bytes) binary += String.fromCharCode(b);
  const response = await fetch(`${GH_API}/${path}`, {
    method: "PUT", headers: GH_HEADERS(env),
    body: JSON.stringify({ message, content: btoa(binary), sha, branch: env.GITHUB_BRANCH || BRANCH }),
  });
  if (!response.ok) throw new Error(`GitHub write failed: HTTP ${response.status}`);
  return response.json();
}
async function getWatchlist(env) {
  const result = await githubGet(env, "games_track_list.json");
  if (!result || !Array.isArray(result.data) || result.data.some(g => !g || typeof g !== "object" || Array.isArray(g))) throw new Error("games_track_list.json is missing or malformed");
  return result;
}
async function mutateWatchlist(env, mutator, message) {
  for (let attempt = 0; attempt < 5; attempt++) {
    const current = await getWatchlist(env);
    const before = JSON.stringify(current.data);
    const result = mutator(current.data);
    if (JSON.stringify(result.games) === before) return result.value;
    try { await githubPut(env, "games_track_list.json", result.games, current.sha, message); return result.value; }
    catch (e) {
      if (attempt === 4 || !String(e.message).includes("HTTP 409")) throw e;
      await new Promise(resolve => setTimeout(resolve, 200 * (attempt + 1)));
    }
  }
  throw new Error("Could not update watchlist");
}
async function steamSearch(query) {
  const u = new URL("https://store.steampowered.com/api/storesearch/");
  u.search = new URLSearchParams({ term: query, l: "tchinese", cc: "tw" });
  const r = await fetch(u, { headers: { "User-Agent": "GamePriceTracker/1.0" } });
  if (!r.ok) throw new Error("Steam search unavailable");
  const d = await r.json();
  return (Array.isArray(d.items) ? d.items : []).filter(x => x && /^\d+$/.test(String(x.id)) && x.name).slice(0, 25)
    .map(x => ({ name: `${x.name} (ID: ${x.id})`.slice(0, 100), value: String(x.id) }));
}
async function steamDetails(id) {
  const u = new URL("https://store.steampowered.com/api/appdetails/");
  u.search = new URLSearchParams({ appids: id, cc: "tw", l: "tchinese" });
  const r = await fetch(u);
  if (!r.ok) throw new Error("Steam details unavailable");
  const d = await r.json();
  return d[id]?.success ? d[id].data : null;
}
async function nintendoRows() {
  const url = "https://raw.githubusercontent.com/SMH642800/game-price-tracker/main/.cache/nintendo_tw_catalogue.json";
  const r = await fetch(url);
  if (!r.ok) throw new Error("Nintendo catalogue cache unavailable");
  const d = await r.json();
  if (d.schema_version !== 1 || !Array.isArray(d.rows) || typeof d.fetched_at !== "number" || Date.now()/1000 - d.fetched_at > 8*24*60*60) throw new Error("Nintendo catalogue cache is stale or invalid");
  return d.rows;
}
const norm = s => String(s).normalize("NFKC").toLocaleLowerCase().replace(/[^\p{L}\p{N}]/gu, "");
async function nintendoSearch(query) {
  const rows = await nintendoRows();
  const seen = new Set(), needle = norm(query), results = [];
  for (const row of rows) {
    const name = row.title || row.name || row.title_name;
    const id = String(row.nsuid || "").trim();
    if (!name || !/^\d+$/.test(id) || seen.has(id) || !norm(name).includes(needle)) continue;
    seen.add(id); results.push({ name: `${name}｜Nintendo Switch 系列數位版`.slice(0,100), value: id });
    if (results.length >= 25) break;
  }
  return results;
}
async function autocomplete(i, env) {
  const command = i.data?.name;
  const focused = (i.data?.options || []).find(o => o.focused);
  const platform = String(opt(i, "platform") || "steam").toLowerCase();
  if (!focused || focused.name !== "game" || !String(focused.value || "").trim()) return { type: 8, data: { choices: [] } };
  const query = String(focused.value).trim();
  if ((command === "add" || command === "remove") && !isAdmin(i, env)) return { type: 8, data: { choices: [] } };
  try {
    if (command === "remove") {
      const { data } = await getWatchlist(env);
      const matches = data.filter(g => {
        const p = platformOf(g);
        const platformOk = platform === "nintendo" ? ["ns","ns2","nintendo"].includes(p) : p === platform;
        return platformOk && (String(g.name || "").toLowerCase().includes(query.toLowerCase()) || productIdOf(g).includes(query));
      }).slice(0,25).map(g => ({ name: `${g.name || "未知遊戲"} (${productIdOf(g)})`.slice(0,100), value: productIdOf(g) }));
      return { type: 8, data: { choices: matches } };
    }
    if (platform === "steam") return { type: 8, data: { choices: await steamSearch(query) } };
    if (["nintendo","ns","ns2"].includes(platform)) return { type: 8, data: { choices: await nintendoSearch(query) } };
  } catch (e) { console.error("autocomplete failed", e?.name || "Error"); }
  return { type: 8, data: { choices: [] } };
}
async function processCommand(i, env) {
  const command = i.data?.name;
  const userId = userIdOf(i);
  if (command === "ping") return "🏓 Pong！Game Price Tracker Cloudflare Worker 正常運作。";
  if (command === "admincheck") return isAdmin(i, env) ? "✅ 你已通過管理員驗證。" : "⛔ 你沒有 Bot 管理員權限。";
  if (command === "help") return "🎮 **Game Price Tracker 使用說明**\n一般：`/ping`、`/list`、`/lookup platform game`、`/help`\n管理員限定：`/admincheck`、`/add platform game`、`/remove platform game`\nNintendo 僅回報台灣數位版價格；價格來源介面未公開文件化。每日查價、Webhook 通知與 Healthchecks 仍由 GitHub Actions 負責。";
  if (command === "list") {
    const { data } = await getWatchlist(env);
    const groups = [
      ["steam","Steam",["steam"]], ["ps5","PlayStation 5（手動追蹤項目）",["ps5"]],
      ["nintendo","Nintendo Switch／Switch 2",["ns","ns2","nintendo"]],
    ];
    const lines = [`🎮 **遊戲追蹤清單**（共 ${data.length} 款）`];
    for (const [, label, platforms] of groups) {
      const games = data.filter(g => platforms.includes(platformOf(g)));
      if (!games.length) continue;
      lines.push("", `🕹️ **${label}（${games.length} 款）**`);
      for (const g of games) lines.push(`• **${String(g.name || "未知遊戲").replace(/[\r\n]/g," ").slice(0,120)}** — ID: \`${productIdOf(g) || "未知"}\`（${g.region || "TW"}）`);
    }
    if (!data.length) lines.push("目前沒有追蹤任何遊戲。");
    return lines.join("\n").slice(0,1950);
  }
  if (command === "add") {
    if (!isAdmin(i, env)) return "⛔ 你沒有 Bot 管理員權限。";
    const platform = String(opt(i,"platform") || "").toLowerCase(), id = String(opt(i,"game") || "").trim();
    if (platform === "steam") {
      if (!/^\d+$/.test(id)) return "❌ 請從 Steam 搜尋結果中選擇遊戲。";
      const detail = await steamDetails(id);
      if (!detail?.name) return "❌ Steam 查不到這款遊戲，請重新搜尋。";
      const added = await mutateWatchlist(env, games => {
        if (games.some(g => platformOf(g)==="steam" && productIdOf(g)===id)) return { games, value:false };
        games.push({ platform:"steam", store:"steam", product_id:id, region:"TW", name:detail.name });
        return { games, value:true };
      }, "Add tracked game via Cloudflare Discord Worker");
      return added ? `✅ 已新增 **${detail.name}**（Steam App ID：${id}，台灣商店）到追蹤清單。` : "⚠️ 這款遊戲已經在追蹤清單中。";
    }
    if (["ns","ns2","nintendo"].includes(platform)) {
      if (!/^\d+$/.test(id)) return "❌ 請從 Nintendo 目錄搜尋結果中選擇遊戲。";
      const rows = await nintendoRows();
      const row = rows.find(x => String(x.nsuid || "") === id && (x.title || x.name || x.title_name));
      if (!row) return "❌ 找不到該 Nintendo 目錄項目；請重新搜尋。";
      const name = row.title || row.name || row.title_name;
      const added = await mutateWatchlist(env, games => {
        if (games.some(g => ["ns","ns2","nintendo"].includes(platformOf(g)) && productIdOf(g)===id)) return { games, value:false };
        games.push({ platform:"nintendo", store:"nintendo_eshop", product_id:id, region:"TW", name, edition:"digital", price_mode:"digital", catalogue_platform_verified:Boolean(row.platform) });
        return { games, value:true };
      }, "Add Nintendo tracked game via Cloudflare Discord Worker");
      return added ? `✅ 已新增 ${name}（Nintendo Switch 系列／台灣數位版，NSUID：${id}）到追蹤清單。` : "⚠️ 這款遊戲已經在追蹤清單中。";
    }
    return "❌ 不支援的平台。";
  }
  if (command === "remove") {
    if (!isAdmin(i, env)) return "⛔ 你沒有 Bot 管理員權限。";
    const platform = String(opt(i,"platform") || "").toLowerCase(), id = String(opt(i,"game") || "").trim();
    const removed = await mutateWatchlist(env, games => {
      const valid = platform === "nintendo" ? ["ns","ns2","nintendo"] : [platform];
      const gone = games.filter(g => valid.includes(platformOf(g)) && productIdOf(g)===id);
      return { games: games.filter(g => !(valid.includes(platformOf(g)) && productIdOf(g)===id)), value: gone };
    }, "Remove tracked game via Cloudflare Discord Worker");
    if (!removed.length) return "⚠️ 找不到該平台的追蹤遊戲，清單未變更。";
    return `✅ 已從 ${SUPPORTED[platform] || platform} 移除：${removed.map(g=>g.name || "未知遊戲").join("、")}。注意：此測試版尚未清理 notification_state.json 中的舊通知狀態。`;
  }
  if (command === "lookup") {
    const platform = String(opt(i,"platform") || "").toLowerCase(), id = String(opt(i,"game") || "").trim();
    if (platform === "steam") {
      if (!/^\d+$/.test(id)) return "❌ 請從 Steam 搜尋結果中選擇遊戲。";
      const d = await steamDetails(id);
      if (!d) return "❌ Steam 找不到這款遊戲或目前無法取得資料。";
      const price = d.price_overview;
      const url = `https://store.steampowered.com/app/${id}/`;
      if (!price || price.currency !== "TWD") return `🎮 **${d.name}**\n台灣商店目前沒有可驗證的價格資料。\n${url}`;
      return `🎮 **${d.name}**\n目前價格：**TWD ${(price.final/100).toFixed(2)}**\n原價：TWD ${(price.initial/100).toFixed(2)}\n折扣：**${price.discount_percent || 0}%**\n${url}`;
    }
    if (["ns","ns2","nintendo"].includes(platform)) {
      if (!/^\d+$/.test(id)) return "❌ 請從 Nintendo 目錄搜尋結果中選擇遊戲。";
      const rows = await nintendoRows(), row = rows.find(x=>String(x.nsuid||"")===id);
      if (!row) return "❌ 找不到該 Nintendo 目錄項目；請重新搜尋。";
      const u = new URL("https://api.ec.nintendo.com/v1/price");
      u.search = new URLSearchParams({country:"TW",lang:"zh",ids:id});
      const r = await fetch(u); if (!r.ok) throw new Error("Nintendo price API unavailable");
      const payload = await r.json(), price = (payload.prices || []).find(x=>String(x.title_id||"")===id);
      const name = row.title || row.name || row.title_name || id;
      const link = `https://ec.nintendo.com/TW/zh/titles/${id}`;
      if (!price) return `🎮 **${name}**｜台灣數位版\n目錄已找到遊戲，但價格介面沒有回傳對應的台灣價格紀錄。\n${link}`;
      const status = String(price.sales_status || "").toLowerCase();
      const currentObj = price.discount_price || price.regular_price;
      const current = currentObj && Number(currentObj.raw_value);
      const currency = currentObj?.currency;
      if (!["onsale","on_sale","preorder","pre_order"].includes(status) || !Number.isFinite(current) || currency !== "TWD") return `🎮 **${name}**｜台灣數位版\n目前沒有可驗證的台灣數位售價。\n${link}`;
      return `🎮 **${name}**｜Nintendo Switch 系列台灣數位版\n目前價格：**TWD ${current.toLocaleString("en-US")}**\n狀態：${status}\n${link}\n注意：不代表實體版價格。`;
    }
    return "❌ 不支援的平台。";
  }
  return "此指令尚未註冊或不支援。";
}
async function postFollowup(i, env, content) {
  const appId = env.DISCORD_APPLICATION_ID;
  const token = i.token;
  if (!appId || !token) throw new Error("Missing interaction follow-up configuration");
  const r = await fetch(`https://discord.com/api/v10/webhooks/${appId}/${token}`, {
    method: "POST", headers: { "content-type":"application/json" },
    body: JSON.stringify({ content: String(content).slice(0,2000), flags: EPHEMERAL }),
  });
  if (!r.ok) console.error("Discord follow-up failed", r.status);
}
async function runDeferred(i, env) {
  try { await postFollowup(i, env, await processCommand(i, env)); }
  catch (e) { console.error("command failed", i.data?.name, e?.name || "Error"); await postFollowup(i, env, "❌ 指令處理失敗，請稍後再試；若持續發生，請檢查 Worker Logs。").catch(()=>{}); }
}
export default {
  async fetch(request, env, ctx) {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });
    const body = await request.text();
    if (!await verifyDiscordRequest(request, body, env.DISCORD_PUBLIC_KEY)) return new Response("Invalid request signature", { status: 401 });
    let i; try { i = JSON.parse(body); } catch { return new Response("Invalid JSON", { status: 400 }); }
    if (i.type === DISCORD_PING) return json({ type: 1 });
    if (i.type === AUTOCOMPLETE) return json(await autocomplete(i, env));
    if (i.type !== APPLICATION_COMMAND) return json(reply("目前不支援這種 Discord 互動。"));
    const command = i.data?.name;
    if (["ping","admincheck","help"].includes(command)) {
      try { return json(reply(await processCommand(i, env))); }
      catch (e) { console.error("command failed", command, e?.name || "Error"); return json(reply("❌ 指令處理失敗，請稍後再試。")); }
    }
    // Defer immediately so GitHub/Steam/Nintendo requests can finish after Discord's 3-second deadline.
    if (["list","add","remove","lookup"].includes(command)) {
      ctx.waitUntil(runDeferred(i, env));
      return json(defer());
    }
    return json(reply("此指令尚未註冊或不支援。"));
  },
};
