/* AI Automation Command Center — dashboard logic */
const $ = (s) => document.querySelector(s);
let mode = "lead";
let filter = "all";

const SAMPLES = {
  hot:  { name: "Priya Sharma", email: "priya@northwind.ai", company: "Northwind AI",
          subject: "Need automation demo",
          message: "We have budget approved this quarter and an urgent deadline — can we get a demo and pricing this week? Looking at an enterprise contract." },
  warm: { name: "Tom Becker", email: "tom@beckerco.com", company: "Becker & Co",
          subject: "Curious about your platform",
          message: "I'm interested in learning more about how your automation platform compares to Zapier. We might evaluate options later this year." },
  risk: { name: "Rita Gomez", email: "rita@oldclient.com", company: "OldClient Inc",
          subject: "Cancellation notice",
          message: "After the latest outage we want to cancel our contract and request a refund. If this isn't resolved we will involve our legal team." },
};

const PRIORITY_STYLE = { hot: "bg-rose-500/15 text-rose-300 border-rose-500/40",
  warm: "bg-amber-500/15 text-amber-300 border-amber-500/40",
  cold: "bg-sky-500/15 text-sky-300 border-sky-500/40" };
const STATUS_STYLE = { pending_approval: "bg-lemon/15 text-lemon border-lemon/40",
  auto_handled: "bg-emerald-500/15 text-emerald-300 border-emerald-500/40",
  approved: "bg-emerald-500/15 text-emerald-300 border-emerald-500/40",
  rejected: "bg-rose-500/15 text-rose-300 border-rose-500/40",
  processing: "bg-accent/15 text-accent border-accent/40",
  failed: "bg-rose-500/15 text-rose-300 border-rose-500/40" };
const AGENT_ICON = { "Intake": "📥", "Intake Guard": "🛡️", "Triage Agent": "🧭",
  "Scoring Agent": "🎯", "Drafting Agent": "✍️", "Compliance Agent": "⚖️",
  "Routing Agent": "🔀", "Pipeline": "✅", "Human Reviewer": "👤",
  "Channel: Telegram": "✈️", "Channel: Email": "📧", "Channel: Slack": "💬" };

const chip = (text, cls) =>
  `<span class="px-2 py-0.5 rounded-full border text-xs ${cls || "border-edge text-slate-400"}">${text}</span>`;
const esc = (s) => (s || "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/* ---- Metrics ---- */
async function loadMetrics() {
  const m = await (await fetch("/api/metrics")).json();
  const cards = [
    ["Items processed", m.total_items, "📊"],
    ["Hot leads", m.hot_leads, "🔥"],
    ["Pending approvals", m.pending_approvals, "🕐"],
    ["Avg pipeline time", m.avg_processing_ms ? (m.avg_processing_ms / 1000).toFixed(1) + "s" : "—", "⚡"],
  ];
  $("#metrics").innerHTML = cards.map(([label, val, icon]) => `
    <div class="bg-panel/80 border border-edge rounded-xl p-4">
      <div class="text-2xl">${icon}</div>
      <div class="text-2xl font-bold mt-1">${val ?? 0}</div>
      <div class="text-xs text-slate-400">${label}</div>
    </div>`).join("");
}

/* ---- Items table ---- */
async function loadItems() {
  const items = await (await fetch("/api/items")).json();
  const rows = items.filter((i) => filter === "all" || i.status === filter);
  $("#items-body").innerHTML = rows.map((i) => `
    <tr class="border-b border-edge/40 hover:bg-ink/40 cursor-pointer" onclick="openDrawer('${i.id}')">
      <td class="py-2.5 pr-3">
        <div class="font-medium">${esc(i.payload.name) || "Anonymous"}</div>
        <div class="text-xs text-slate-500">${esc(i.payload.company || i.payload.email || "")}</div>
      </td>
      <td class="pr-3">${chip(i.kind)}</td>
      <td class="pr-3 text-xs text-slate-400">${esc(i.classification || "…")}</td>
      <td class="pr-3">${i.score != null ? chip(i.score + " · " + i.priority, PRIORITY_STYLE[i.priority]) : "…"}</td>
      <td class="pr-3 text-xs">${i.risk_level ? chip(i.risk_level, i.risk_level === "high" ? PRIORITY_STYLE.hot : "") : "…"}</td>
      <td class="pr-3">${chip(i.status.replace("_", " "), STATUS_STYLE[i.status])}</td>
      <td class="text-xs text-slate-500">${i.engine || "…"}</td>
    </tr>`).join("") ||
    `<tr><td colspan="7" class="py-6 text-center text-slate-500 text-sm">No items match this filter.</td></tr>`;
}

/* ---- Detail drawer ---- */
async function openDrawer(id) {
  const i = await (await fetch("/api/items/" + id)).json();
  const p = i.payload;
  $("#drawer-body").innerHTML = `
    <div class="space-y-1">
      <div class="flex flex-wrap gap-1.5">${chip(i.kind)}${i.priority ? chip(i.score + " · " + i.priority, PRIORITY_STYLE[i.priority]) : ""}
        ${chip(i.status.replace("_", " "), STATUS_STYLE[i.status])}${i.risk_level ? chip("risk: " + i.risk_level, i.risk_level === "high" ? PRIORITY_STYLE.hot : "") : ""}
        ${i.engine ? chip("engine: " + i.engine) : ""}</div>
      <h4 class="font-semibold text-base pt-1">${esc(p.name) || "Anonymous"} <span class="text-slate-500 font-normal text-sm">${esc(p.email || "")}</span></h4>
      ${p.subject ? `<p class="text-slate-400">Subject: ${esc(p.subject)}</p>` : ""}
      <p class="text-slate-300 bg-ink/50 border border-edge rounded-lg p-3 mt-2 whitespace-pre-wrap">${esc(p.message || p.body)}</p>
    </div>
    ${i.summary ? `<div><h5 class="text-xs uppercase tracking-wide text-slate-500 mb-1">AI Summary</h5><p>${esc(i.summary)}</p></div>` : ""}
    ${i.draft ? `<div><h5 class="text-xs uppercase tracking-wide text-slate-500 mb-1">Drafted Reply</h5>
      <pre class="whitespace-pre-wrap font-sans bg-ink/50 border border-edge rounded-lg p-3 text-slate-300">${esc(i.draft)}</pre></div>` : ""}
    ${i.risk_notes ? `<div><h5 class="text-xs uppercase tracking-wide text-slate-500 mb-1">Compliance Notes</h5><p class="text-slate-400">${esc(i.risk_notes)}</p></div>` : ""}
    ${i.status === "pending_approval" ? `
      <div class="flex gap-2 pt-1">
        <button onclick="decide('${i.id}','approve')" class="flex-1 py-2 rounded-lg bg-emerald-500/90 text-ink font-semibold hover:opacity-90">✓ Approve & send</button>
        <button onclick="decide('${i.id}','reject')" class="flex-1 py-2 rounded-lg bg-rose-500/80 text-white font-semibold hover:opacity-90">✕ Reject</button>
      </div>` : ""}
    <div><h5 class="text-xs uppercase tracking-wide text-slate-500 mb-2">Agent Trace</h5>
      <ol class="relative border-l border-edge ml-2 space-y-3">
        ${i.trace.map((t) => `
          <li class="ml-4">
            <span class="absolute -left-2.5 mt-0.5 w-5 h-5 rounded-full bg-panel border border-edge text-xs flex items-center justify-center">${AGENT_ICON[t.agent] || "•"}</span>
            <div class="text-xs text-slate-500">${esc(t.agent)} · ${new Date(t.ts * 1000).toLocaleTimeString()}</div>
            <div class="font-medium">${esc(t.title)}</div>
            ${t.detail ? `<div class="text-xs text-slate-400 mt-0.5">${esc(t.detail)}</div>` : ""}
          </li>`).join("")}
      </ol></div>`;
  $("#drawer").classList.remove("translate-x-full");
  $("#drawer-overlay").classList.remove("hidden");
}
window.openDrawer = openDrawer;

async function decide(id, action) {
  await fetch(`/api/items/${id}/${action}`, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({ note: "" }) });
  await Promise.all([loadItems(), loadMetrics()]);
  openDrawer(id);
}
window.decide = decide;

function closeDrawer() {
  $("#drawer").classList.add("translate-x-full");
  $("#drawer-overlay").classList.add("hidden");
}
$("#drawer-close").onclick = closeDrawer;
$("#drawer-overlay").onclick = closeDrawer;

/* ---- Live SSE feed ---- */
function startFeed() {
  const es = new EventSource("/api/stream");
  es.onmessage = (e) => {
    let ev;
    try { ev = JSON.parse(e.data); } catch { return; }
    if (ev.type === "done") { loadItems(); loadMetrics(); return; }
    $("#feed-empty")?.remove();
    const el = document.createElement("div");
    el.className = "trace-enter flex gap-2.5 bg-ink/50 border border-edge rounded-lg p-2.5 text-sm";
    el.innerHTML = `<div class="text-lg leading-none pt-0.5">${AGENT_ICON[ev.agent] || "•"}</div>
      <div class="min-w-0">
        <div class="flex items-baseline gap-2 flex-wrap">
          <span class="font-medium text-accent/90">${esc(ev.agent)}</span>
          <span class="text-xs text-slate-500">${new Date(ev.ts * 1000).toLocaleTimeString()}</span>
          <button class="text-xs text-slate-500 hover:text-accent" onclick="openDrawer('${ev.item_id}')">#${ev.item_id.slice(0, 6)}</button>
        </div>
        <div>${esc(ev.title)}</div>
        ${ev.detail ? `<div class="text-xs text-slate-400 truncate">${esc(ev.detail)}</div>` : ""}
      </div>`;
    const feed = $("#feed");
    feed.prepend(el);
    while (feed.children.length > 60) feed.lastChild.remove();
  };
  es.onerror = () => { es.close(); setTimeout(startFeed, 3000); };
}

/* ---- Form ---- */
function setMode(m) {
  mode = m;
  $("#tab-lead").className = "tab px-3 py-1.5 rounded-lg " + (m === "lead" ? "bg-accent/15 text-accent border border-accent/40" : "border border-edge text-slate-400");
  $("#tab-email").className = "tab px-3 py-1.5 rounded-lg " + (m === "email" ? "bg-accent/15 text-accent border border-accent/40" : "border border-edge text-slate-400");
  $("[name=subject]").classList.toggle("hidden", m === "lead");
  $("[name=company]").classList.toggle("hidden", m === "email");
}
$("#tab-lead").onclick = () => setMode("lead");
$("#tab-email").onclick = () => setMode("email");

document.querySelectorAll(".sample").forEach((b) => b.onclick = () => {
  const s = SAMPLES[b.dataset.sample];
  const f = $("#inbound-form");
  f.name.value = s.name; f.email.value = s.email; f.company.value = s.company;
  f.subject.value = s.subject; f.message.value = s.message;
});

$("#inbound-form").onsubmit = async (e) => {
  e.preventDefault();
  const f = e.target;
  const body = mode === "lead"
    ? { name: f.name.value, email: f.email.value, company: f.company.value, message: f.message.value }
    : { name: f.name.value, email: f.email.value, subject: f.subject.value, body: f.message.value };
  const r = await fetch(mode === "lead" ? "/api/leads" : "/api/emails", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (r.ok) { f.reset(); loadItems(); }
  else alert("Validation error — message is required (min 3 chars).");
};

/* ---- Filters ---- */
document.querySelectorAll(".filter").forEach((b) => b.onclick = () => {
  filter = b.dataset.f;
  document.querySelectorAll(".filter").forEach((x) =>
    x.className = "filter px-2.5 py-1 rounded-full " + (x === b ? "bg-accent/15 text-accent border border-accent/40" : "border border-edge text-slate-400"));
  loadItems();
});

/* ---- Channel badges ---- */
async function loadChannels() {
  const c = await (await fetch("/api/config")).json();
  $("#engine-badge").textContent = "engine: " + c.engine;
  const on = (ok) => ok ? "border-emerald-500/40 text-emerald-300 bg-emerald-500/10"
                        : "border-edge text-slate-500";
  const badges = [
    c.telegram.enabled && c.telegram.bot_username
      ? `<a href="https://t.me/${c.telegram.bot_username}" target="_blank" class="px-2 py-1 rounded border ${on(true)} hover:border-emerald-400">✈️ Telegram @${c.telegram.bot_username}</a>`
      : `<span class="px-2 py-1 rounded border ${on(c.telegram.enabled)}">✈️ Telegram ${c.telegram.enabled ? "(live)" : "(off)"}</span>`,
    `<span class="px-2 py-1 rounded border ${on(c.email_out)}">📧 Email out ${c.email_out ? "(live)" : "(off)"}</span>`,
    `<span class="px-2 py-1 rounded border ${on(c.slack_alerts)}">💬 Slack alerts ${c.slack_alerts ? "(live)" : "(off)"}</span>`,
    `<a href="/integrations" class="px-2 py-1 rounded border border-edge text-slate-400 hover:border-accent/50">🔌 Webhooks / n8n →</a>`,
  ];
  $("#channel-badges").innerHTML = badges.join("");
}

/* ---- Boot ---- */
(async function init() {
  await Promise.all([loadChannels(), loadMetrics(), loadItems()]);
  startFeed();
  setInterval(loadMetrics, 15000);
})();
