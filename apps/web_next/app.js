/* ProcuraMind AI web app: dependency-free, hash-routed SPA. All dynamic text is escaped via esc(). */
"use strict";
const API = "/api/v1";
const S = { platforms: [], token: null, user: null, orgs: [], org: null, projects: [], pid: null, agents: [], unread: 0, pollers: [] };
try { S.token = localStorage.getItem("pm_token"); S.pid = localStorage.getItem("pm_pid"); } catch (e) {}
const $ = (s, r = document) => r.querySelector(s);
const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtDate = s => s ? new Date(s.endsWith("Z") || s.includes("+") ? s : s + "Z").toLocaleString() : "";
const ago = s => { if (!s) return ""; const d = (Date.now() - new Date(s.endsWith("Z") || s.includes("+") ? s : s + "Z")) / 1000; return d < 60 ? "just now" : d < 3600 ? Math.floor(d / 60) + " min ago" : d < 86400 ? Math.floor(d / 3600) + " h ago" : Math.floor(d / 86400) + " d ago"; };
const tone = s => ({ completed: "ok", ready: "ok", approved: "ok", running: "info", processing: "info", awaiting_approval: "warn", needs_input: "warn", failed: "bad", rejected: "bad", cancelled: "", skipped: "" }[s] ?? "");
const badge = (t, c) => `<span class="badge ${c ?? tone(t)}">${esc(String(t).replaceAll("_", " "))}</span>`;

async function api(path, { method = "GET", body, form, raw } = {}) {
  const headers = {};
  if (S.token) headers.Authorization = "Bearer " + S.token;
  if (body) headers["Content-Type"] = "application/json";
  const res = await fetch(API + path, { method, headers, body: form || (body ? JSON.stringify(body) : undefined) });
  if (res.status === 401 && S.token) { logout(); throw new Error("Session expired. Please sign in again."); }
  if (raw && res.ok) return res;
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { const e = new Error(data.message || data.detail?.[0]?.msg || data.detail || "Request failed (" + res.status + ")"); e.status = res.status; e.code = data.code; throw e; }
  return data;
}
function toast(msg, kind = "") { const t = document.createElement("div"); t.className = "toast " + kind; t.textContent = msg; $("#toasts").append(t); setTimeout(() => t.remove(), 4500); }
const fail = e => toast(e.message || String(e), "bad");
function modal(html, onMount) {
  const root = $("#modal-root"); root.innerHTML = `<div class="modal-bg"><div class="modal" role="dialog" aria-modal="true">${html}</div></div>`;
  root.firstChild.addEventListener("mousedown", e => { if (e.target === root.firstChild) closeModal(); });
  onMount && onMount(root.firstChild);
}
const closeModal = () => { $("#modal-root").innerHTML = ""; };
function skeleton(n = 4) { return `<div class="card">${'<div class="skel"></div>'.repeat(n)}</div>`; }
const empty = (title, text, action = "") => `<div class="empty"><b>${esc(title)}</b>${esc(text)}${action ? `<div class="mt">${action}</div>` : ""}</div>`;
function setTheme(t) { document.documentElement.dataset.theme = t; try { localStorage.setItem("pm_theme", t); } catch (e) {} }
function logout() { S.token = null; S.user = null; try { localStorage.removeItem("pm_token"); } catch (e) {} location.hash = "#/"; render(); }

/* ------------------------------------------------------------------ charts (inline SVG) */
const PAL = ["#4f46e5", "#0ea5a4", "#f59e0b", "#e11d48", "#8b5cf6", "#22c55e", "#3b82f6", "#f97316"];
const nf = v => Math.abs(v) >= 1e6 ? (v / 1e6).toFixed(1) + "M" : Math.abs(v) >= 1e3 ? (v / 1e3).toFixed(1) + "k" : String(Math.round(v * 100) / 100);
function chartSvg(c) {
  const labels = c.labels || [], series = c.series || []; if (!labels.length || !series.length) return empty("No data", "Nothing to chart.");
  const W = 640, H = 260, L = 48, R = 12, T = 12, B = 44, pw = W - L - R, ph = H - T - B;
  const all = series.flatMap(s => s.values); let max = Math.max(...all, 0), min = Math.min(...all, 0); if (max === min) max = min + 1;
  const y = v => T + ph - (v - min) / (max - min) * ph;
  let g = "";
  for (let i = 0; i <= 4; i++) { const v = min + (max - min) * i / 4; g += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="var(--line)"/><text x="${L - 6}" y="${y(v) + 4}" text-anchor="end" font-size="10" fill="var(--muted)">${nf(v)}</text>`; }
  const step = Math.ceil(labels.length / 8), xl = i => L + (c.kind === "bar" ? (i + .5) / labels.length : labels.length === 1 ? .5 : i / (labels.length - 1)) * pw;
  labels.forEach((l, i) => { if (i % step === 0) g += `<text x="${xl(i)}" y="${H - B + 16}" text-anchor="middle" font-size="10" fill="var(--muted)">${esc(String(l).slice(0, 12))}</text>`; });
  if (c.kind === "bar") {
    const bw = pw / labels.length * .78 / series.length;
    series.forEach((s, si) => s.values.forEach((v, i) => { const x = xl(i) - bw * series.length / 2 + si * bw; g += `<rect x="${x}" y="${Math.min(y(v), y(0))}" width="${bw}" height="${Math.abs(y(v) - y(0))}" rx="3" fill="${PAL[si % 8]}"><title>${esc(s.name)} · ${esc(labels[i])}: ${v}</title></rect>`; }));
  } else {
    series.forEach((s, si) => { const pts = s.values.map((v, i) => `${xl(i)},${y(v)}`).join(" "); g += `<polyline points="${pts}" fill="none" stroke="${PAL[si % 8]}" stroke-width="2.5" stroke-linejoin="round"/>` + s.values.map((v, i) => `<circle cx="${xl(i)}" cy="${y(v)}" r="3.5" fill="${PAL[si % 8]}"><title>${esc(s.name)} · ${esc(labels[i])}: ${v}</title></circle>`).join(""); });
  }
  const legend = series.length > 1 ? `<div class="row small" style="margin-top:6px">${series.map((s, i) => `<span><i style="display:inline-block;width:10px;height:10px;border-radius:3px;background:${PAL[i % 8]}"></i> ${esc(s.name)}</span>`).join("")}</div>` : "";
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="${esc(c.title)}">${g}</svg>${legend}`;
}
function donut(map, title) {
  const ent = Object.entries(map).filter(([, v]) => v > 0), tot = ent.reduce((a, [, v]) => a + v, 0); if (!tot) return empty("No data yet", "Run an agent to see activity.");
  let acc = 0; const R = 54, C = 2 * Math.PI * R;
  const arcs = ent.map(([k, v], i) => { const len = v / tot * C, el = `<circle r="${R}" cx="70" cy="70" fill="none" stroke="${PAL[i % 8]}" stroke-width="22" stroke-dasharray="${len} ${C - len}" stroke-dashoffset="${-acc}" transform="rotate(-90 70 70)"><title>${esc(k)}: ${v}</title></circle>`; acc += len; return el; }).join("");
  return `<div class="row"><svg viewBox="0 0 140 140" width="140" role="img" aria-label="${esc(title)}">${arcs}<text x="70" y="75" text-anchor="middle" font-size="22" font-weight="700" fill="var(--text)">${tot}</text></svg><div>${ent.map(([k, v], i) => `<div class="small"><i style="display:inline-block;width:10px;height:10px;border-radius:3px;background:${PAL[i % 8]}"></i> ${esc(k.replaceAll("_", " "))} · <b>${v}</b></div>`).join("")}</div></div>`;
}

/* ------------------------------------------------------------------ generic agent-result renderer */
function renderSection(s) {
  const t = s.title ? `<h3>${esc(s.title)}</h3>` : "";
  switch (s.type) {
    case "text": return /^AI interpretation/.test(s.title || "") ? `<div class="sect card" style="border-color:var(--brand2);background:var(--brand-soft)"><h3>✦ ${esc(s.title)}</h3><div style="white-space:pre-wrap">${esc(s.text)}</div></div>` : `<div class="sect">${t}<div style="white-space:pre-wrap">${esc(s.text)}</div></div>`;
    case "bullets": return `<div class="sect">${t}<ul>${(s.items || []).map(i => `<li>${esc(i)}</li>`).join("")}</ul></div>`;
    case "kv": return `<div class="sect">${t}<div class="grid g4">${(s.items || []).map(([k, v]) => `<div class="card kpi"><div class="l">${esc(k)}</div><div class="v" style="font-size:18px;word-break:break-all">${esc(v)}</div></div>`).join("")}</div></div>`;
    case "table": return `<div class="sect">${t}<div class="tablewrap"><table><thead><tr>${(s.columns || []).map(c => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${(s.rows || []).map(r => `<tr>${r.map(c => `<td>${/^(MET|LOW|OVER budget)$/i.test(c) ? badge(c, /OVER/i.test(c) ? "bad" : "ok") : /^(HIGH|NOT_MET|MISSING)$/i.test(c) ? badge(c, "bad") : /^(MEDIUM|UNCERTAIN)$/i.test(c) ? badge(c, "warn") : esc(c)}</td>`).join("")}</tr>`).join("") || `<tr><td colspan="${(s.columns || []).length}" class="muted">No rows.</td></tr>`}</tbody></table></div></div>`;
    case "chart": return `<div class="sect">${t}${chartSvg(s)}</div>`;
    case "draft": return `<div class="sect">${t}<div class="muted small">Subject: ${esc(s.subject)} · DRAFT, not sent</div><div class="draft">${esc(s.body)}</div><button class="btn sm mt" data-copy="${esc(s.body)}">Copy draft</button></div>`;
    default: return "";
  }
}
function renderResult(o) {
  if (!o) return "";
  let h = `<p><b>${esc(o.summary || "")}</b></p>`;
  if (o.needs_input) h += `<div class="card" style="border-color:var(--warn)">${badge("needs input")} ${esc(o.needs_input)}</div>`;
  h += (o.sections || []).map(renderSection).join("");
  if ((o.evidence || []).length && !(o.sections || []).some(x => x.title === "Evidence")) h += `<div class="sect"><h3>Evidence (retrieved from your documents)</h3>${o.evidence.map(e => `<div class="ev"><b>${esc(e.document)}</b> · page ${esc(e.page)} <small>· score ${esc(e.score)}</small><br>${esc((e.snippet || "").slice(0, 320))}</div>`).join("")}</div>`;
  if (o.labels && Object.keys(o.labels).length) h += `<p class="small muted mt">${Object.entries(o.labels).map(([k, v]) => esc(v)).join(" · ")}</p>`;
  return h;
}
document.addEventListener("click", e => { const b = e.target.closest("[data-copy]"); if (b) navigator.clipboard?.writeText(b.dataset.copy).then(() => toast("Copied", "ok")); });

/* ------------------------------------------------------------------ shell, router */
const NAV = [
  ["Workspace", [["hub", "Platform Hub", "⌂"], ["dashboard", "Dashboard", "▦"], ["projects", "Projects", "▣"], ["assistant", "AI Assistant", "✦"], ["agents", "Agent Marketplace", "◎"], ["executions", "Execution Center", "⚡"]]],
  ["PLATFORMS", []],
  ["Across platforms", [["documents", "Documents", "▤"], ["workflows", "Workflows", "⇢"], ["reports", "Reports", "▥"]]],
  ["Account", [["notifications", "Notifications", "◔"], ["activity", "Activity & Audit", "☰"], ["team", "Team", "☺"], ["subscription", "Plan & Usage", "★"], ["settings", "Settings", "⚙"]]],
];
const PAGES = {};
function route() { const h = location.hash.replace(/^#\//, ""); const [name, ...rest] = h.split("/"); return { name: name || "", arg: rest.join("/") }; }
function stopPollers() { S.pollers.forEach(clearInterval); S.pollers = []; }
window.addEventListener("hashchange", () => { closeModal(); render(); });

async function boot() {
  if (S.token) {
    try { S.user = await api("/auth/me"); await loadCore(); } catch (e) { S.token = null; }
  }
  render();
}
async function loadCore() {
  [S.orgs, S.projects, S.agents, S.platforms] = await Promise.all([api("/orgs"), api("/projects"), api("/agents"), api("/platforms")]);
  S.org = S.orgs[0]; if (!S.projects.find(p => p.id === S.pid)) S.pid = S.projects[0]?.id || null;
  refreshUnread();
}
async function refreshUnread() { try { const n = await api("/notifications?unread_only=true"); S.unread = n.unread; const b = $("#bell-n"); if (b) { b.textContent = n.unread; b.style.display = n.unread ? "" : "none"; } } catch (e) {} }
const curProject = () => S.projects.find(p => p.id === S.pid);
function setProject(id) { S.pid = id; try { localStorage.setItem("pm_pid", id); } catch (e) {} render(); }

async function render() {
  stopPollers();
  const r = route(), app = $("#app");
  if (!S.token) { app.innerHTML = r.name === "login" || r.name === "register" ? authView(r.name) : landing(); bindAuth(); return; }
  if (!r.name) { location.hash = "#/hub"; return; }
  const page = PAGES[r.name] || PAGES.dashboard;
  app.innerHTML = `<div class="shell"><aside class="side" id="side"><div class="logo"><i>P</i>ProcuraMind AI</div><nav class="nav">${NAV.map(([h, items]) => (h === "PLATFORMS" ? ["Platforms", S.platforms.map(p => ["platform/" + p.id, p.name, p.icon])] : [h, items])).map(([h, items]) => `<div class="nav-h">${h}</div>${items.map(([k, l, ic]) => `<a href="#/${k}" class="${(r.name + (r.name === "platform" ? "/" + r.arg : "")) === k ? "on" : ""}"><span aria-hidden="true">${ic}</span>${l}</a>`).join("")}`).join("")}</nav></aside>
  <div class="main"><header class="top"><button class="btn icon-btn menu-btn" id="menu" aria-label="Menu">☰</button>
  <select id="proj" aria-label="Project" style="max-width:220px">${S.projects.length ? S.projects.map(p => `<option value="${p.id}" ${p.id === S.pid ? "selected" : ""}>${esc(p.title)}</option>`).join("") : `<option value="">No projects yet</option>`}</select>
  <div class="search"><input id="gs" placeholder="Search projects, documents, vendors, tasks…" autocomplete="off"><div id="gsr" class="results" hidden></div></div><div class="sp"></div>
  <span class="badge brand" title="Current plan">${esc(S.org?.name || "")} · ${esc(S.org?.plan || "")}</span>
  <button class="btn icon-btn" id="theme" aria-label="Toggle theme" style="width:auto;padding:0 10px">Theme</button>
  <a class="btn icon-btn" href="#/notifications" aria-label="Notifications">🔔<span class="dot" id="bell-n" style="display:none"></span></a>
  <button class="btn sm" id="out">${esc(S.user.full_name.split(" ")[0])} · Sign out</button></header>
  <main class="content" id="page">${skeleton()}</main></div></div>`;
  $("#menu").onclick = () => $("#side").classList.toggle("open");
  $("#side").onclick = () => $("#side").classList.remove("open");
  $("#proj").onchange = e => e.target.value && setProject(e.target.value);
  $("#theme").onclick = () => setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
  $("#out").onclick = logout; bindSearch(); refreshUnread();
  try { await page(r.arg, $("#page")); } catch (e) { $("#page").innerHTML = `<div class="card">${empty("Something went wrong", e.message)}</div>`; }
}
function bindSearch() {
  const i = $("#gs"), box = $("#gsr"); let t;
  i.oninput = () => { clearTimeout(t); const q = i.value.trim(); if (q.length < 2) { box.hidden = true; return; } t = setTimeout(async () => {
    try { const r = await api("/search?q=" + encodeURIComponent(q)); const rows = [...r.projects.map(p => `<a href="#/project/${p.id}">▣ ${esc(p.title)} <small>project</small></a>`), ...r.documents.map(d => `<a href="#/project/${d.project_id}">▤ ${esc(d.filename || d.original_filename)} <small>document</small></a>`), ...(r.vendors || []).map(v => `<a href="#/project/${v.project_id}">◈ ${esc(v.name)} <small>vendor</small></a>`), ...(r.workflows || []).map(w => `<a href="#/workflows">⇢ ${esc(w.name)} <small>workflow</small></a>`), ...(r.conversations || []).map(c => `<a href="#/assistant/${c.id}">✦ ${esc(c.title)} <small>chat</small></a>`)];
      box.innerHTML = rows.join("") || `<div class="empty">No results for “${esc(q)}”</div>`; box.hidden = false; } catch (e) { fail(e); } }, 250); };
  document.addEventListener("click", e => { if (!e.target.closest(".search")) box.hidden = true; }, { once: true });
}

/* ------------------------------------------------------------------ landing & auth */
function landing() {
  return `<div class="land"><nav><div class="logo"><i>P</i>ProcuraMind AI</div><div class="row"><button class="btn" id="theme0" aria-label="Toggle theme" style="width:auto;padding:0 10px">Theme</button><a class="btn" href="#/login">Sign in</a><a class="btn pri" href="#/register">Get started</a></div></nav>
  <section class="hero"><span class="badge brand">Multi-platform · Multi-organization · Multi-agent</span><h1>One AI workspace for procurement, HR, support, legal, finance and operations</h1>
  <p>Upload documents, ask grounded questions with page citations, compare vendors, review contracts and automate multi-step workflows with approval checkpoints. Agents analyse and draft; people approve.</p>
  <a class="btn pri" href="#/register">Create your workspace</a></section>
  <section class="content"><div class="grid g3">${[["Cited answers", "Hybrid vector + BM25 retrieval. Every answer shows its source page, and out-of-scope questions are refused."], ["12 specialist agents", "Research, RAG, data analysis, procurement, vendor, financial, contract, compliance, report, communication, workflow and a supervisor."], ["Approvals built in", "Workflows pause for human sign-off. Agents never send external messages, approve payments or take irreversible actions."], ["Multi-tenant", "Organizations, roles (owner / admin / member / viewer), project isolation, audit trail and usage limits per plan."], ["Any domain", "Procurement, contracts, finance, HR, legal, operations or general knowledge projects."], ["Honest by design", "Deterministic, explainable analysis. LLM is optional. Nothing is fabricated to fill a page."]].map(([t, d]) => `<div class="card"><h2>${t}</h2><p class="muted">${d}</p></div>`).join("")}</div></section></div>`;
}
function authView(mode) {
  const reg = mode === "register";
  return `<div class="land"><nav><a class="logo" href="#/"><i>P</i>ProcuraMind AI</a></nav><div class="card auth"><h1>${reg ? "Create your workspace" : "Welcome back"}</h1><p class="muted">${reg ? "A personal organization is created automatically." : "Sign in to continue."}</p>
  <form id="af" class="mt">${reg ? `<label class="f"><span>Full name</span><input name="full_name" required minlength="2" autocomplete="name"></label>` : ""}
  <label class="f"><span>Email</span><input name="email" type="email" required autocomplete="email"></label>
  <label class="f"><span>Password</span><input name="password" type="password" required minlength="${reg ? 10 : 1}" autocomplete="${reg ? "new-password" : "current-password"}">${reg ? `<small class="muted">At least 10 characters, with letters and digits.</small>` : ""}</label>
  <button class="btn pri" style="width:100%;justify-content:center" id="sub">${reg ? "Create account" : "Sign in"}</button></form>
  <p class="small muted mt">${reg ? `Have an account? <a href="#/login">Sign in</a>` : `New here? <a href="#/register">Create an account</a>`}</p></div></div>`;
}
function bindAuth() {
  const t = $("#theme0"); if (t) t.onclick = () => setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
  const f = $("#af"); if (!f) return;
  f.onsubmit = async e => {
    e.preventDefault(); const d = Object.fromEntries(new FormData(f)); $("#sub").disabled = true;
    try {
      if (d.full_name) await api("/auth/register", { method: "POST", body: d });
      const r = await api("/auth/login", { method: "POST", body: { email: d.email, password: d.password } });
      S.token = r.access_token; S.user = r.user; try { localStorage.setItem("pm_token", S.token); } catch (x) {}
      await loadCore(); location.hash = "#/hub"; render();
    } catch (err) { fail(err); $("#sub").disabled = false; }
  };
}

/* ------------------------------------------------------------------ shared helpers for pages */
const pageHead = (title, sub, actions = "") => `<div class="page-h"><div><h1>${esc(title)}</h1>${sub ? `<p>${esc(sub)}</p>` : ""}</div><div class="row">${actions}</div></div>`;
const needProject = () => curProject() ? "" : `<div class="card">${empty("Select or create a project", "This feature works inside a project.", `<a class="btn pri" href="#/projects">Go to projects</a>`)}</div>`;
const agentName = id => S.agents.find(a => a.id === id)?.name || id;
async function runAgent(agent, params = {}, { projectId = S.pid, btn } = {}) {
  if (btn) { btn.disabled = true; btn.innerHTML = `<span class="spin"></span> Running…`; }
  try { const t = await api(`/agents/${agent}/run`, { method: "POST", body: { project_id: projectId, params } }); return t; }
  catch (e) { if (e.status === 402) toast("Plan limit reached: " + e.message, "bad"); else fail(e); return null; }
}
function taskView(t) {
  const b = [badge(t.status)];
  let actions = "";
  if (t.status === "awaiting_approval") actions = `<div class="row mt"><button class="btn pri" data-dec="1" data-id="${t.id}">Approve</button><button class="btn bad" data-dec="0" data-id="${t.id}">Reject</button><span class="small muted">Nothing is sent or executed externally either way.</span></div>`;
  if (t.status === "failed" || t.status === "needs_input") actions = `<div class="row mt"><button class="btn" data-retry="${t.id}">Retry</button><button class="btn bad" data-cancel="${t.id}">Cancel</button></div>`;
  return `<div class="card"><div class="row"><h2>${esc(t.agent_name)}</h2>${b.join("")}<span class="sp"></span><span class="small muted">${t.duration_ms ?? 0} ms · attempts ${t.attempts} · ${esc(ago(t.created_at))}</span></div>${t.error ? `<p class="small" style="color:var(--bad)">${esc(t.error)}</p>` : ""}${renderResult(t.output)}${actions}</div>`;
}
function bindTaskActions(root, reload) {
  root.querySelectorAll("[data-dec]").forEach(b => b.onclick = async () => { const note = prompt("Optional note for the audit log:") ?? ""; try { await api(`/tasks/${b.dataset.id}/decision`, { method: "POST", body: { approve: b.dataset.dec === "1", note } }); toast("Decision recorded", "ok"); reload(); } catch (e) { fail(e); } });
  root.querySelectorAll("[data-retry]").forEach(b => b.onclick = async () => { b.disabled = true; try { await api(`/tasks/${b.dataset.retry}/retry`, { method: "POST" }); reload(); } catch (e) { fail(e); b.disabled = false; } });
  root.querySelectorAll("[data-cancel]").forEach(b => b.onclick = async () => { try { await api(`/tasks/${b.dataset.cancel}/cancel`, { method: "POST" }); reload(); } catch (e) { fail(e); } });
}
function uploadModal(pid, done) {
  modal(`<h2>Upload a document</h2><p class="muted small">PDF, DOCX, XLSX, CSV or TXT. Files are scanned for type and size, then indexed for search.</p><form id="uf" class="mt"><label class="f"><span>File</span><input type="file" name="file" required accept=".pdf,.docx,.xlsx,.csv,.txt"></label><label class="f"><span>Document type</span><select name="document_type">${["auto", "tender", "quotation", "policy", "historical", "contract", "financial", "dataset", "job_description", "resume", "tickets", "knowledge_base", "meeting_notes", "other"].map(t => `<option>${t}</option>`).join("")}</select></label><div class="row"><button class="btn pri" id="ub">Upload</button><button type="button" class="btn" onclick="closeModal()">Cancel</button></div></form>`, m => {
    $("#uf", m).onsubmit = async e => { e.preventDefault(); const fd = new FormData(e.target); $("#ub").disabled = true; try { await api(`/projects/${pid}/documents`, { method: "POST", form: fd }); toast("Uploaded. Processing started.", "ok"); closeModal(); done(); } catch (er) { fail(er); $("#ub").disabled = false; } };
  });
}
function agentForm(a, onRun) {
  const fields = Object.entries(a.input_schema || {});
  modal(`<div class="row"><h2>${esc(a.name)}</h2>${badge(a.domain, "brand")}${a.requires_approval ? badge("needs approval", "warn") : ""}</div><p class="muted">${esc(a.description)}</p>
  <p class="small muted">Tools: ${a.tools.map(esc).join(", ") || "none"} · Permissions: ${a.permissions.map(esc).join(", ")} · Timeout ${a.timeout_s}s · Cannot send externally</p>
  <form id="af2" class="mt">${a.requires_project ? (curProject() ? `<p class="small">Project: <b>${esc(curProject().title)}</b></p>` : `<p class="badge bad">Select a project first</p>`) : ""}
  ${fields.map(([k, d]) => `<label class="f"><span>${esc(k)} <small class="muted">${esc(d)}</small></span>${k === "question" || k === "request" || k === "ticket" ? `<textarea name="${esc(k)}" placeholder="${esc(a.example || "")}">${esc(a.example || "")}</textarea>` : `<input name="${esc(k)}">`}</label>`).join("")}
  <label class="small"><input type="checkbox" id="ul" checked> Allow AI interpretation (uses the configured LLM, if any)</label><div class="row mt"><button class="btn pri" id="rb">▶ Run agent</button><button type="button" class="btn" onclick="closeModal()">Close</button></div></form><div id="rr" class="mt"></div>`, m => {
    $("#af2", m).onsubmit = async e => {
      e.preventDefault(); const params = {}; new FormData(e.target).forEach((v, k) => { if (v !== "") params[k] = /^(top_k|expiring_days)$/.test(k) ? Number(v) : v === "true" ? true : v === "false" ? false : v; });
      if (!$("#ul", m).checked) params.use_llm = false;
      const t = await runAgent(a.id, params, { btn: $("#rb", m) }); $("#rb", m).disabled = false; $("#rb", m).textContent = "▶ Run again";
      if (t) { $("#rr", m).innerHTML = taskView(t); bindTaskActions($("#rr", m), () => { closeModal(); render(); }); onRun && onRun(t); }
    };
  });
}
window.closeModal = closeModal;

/* ------------------------------------------------------------------ pages */
PAGES.dashboard = async (_, el) => {
  const d = await api("/dashboard"); const k = d.kpis, u = d.usage;
  const kp = [["Projects", k.projects], ["Documents", k.documents], ["Vendors", k.vendors], ["Agent tasks", k.agent_tasks], ["Pending approvals", k.pending_approvals], ["Open review items", k.open_review_items], ["Reports", k.reports]];
  const bar = (l, x) => `<div class="small row"><span>${l}</span><span class="sp"></span><b>${x.used}${x.limit == null ? "" : " / " + x.limit}</b></div><div class="bar ${x.limit && x.used / x.limit > .9 ? "bad" : x.limit && x.used / x.limit > .7 ? "warn" : ""}"><i style="width:${x.limit ? Math.min(100, x.used / x.limit * 100) : 8}%"></i></div>`;
  el.innerHTML = pageHead("Dashboard", `${d.org.name} · your role: ${d.org.role}`, `<a class="btn pri" href="#/assistant">✦ Ask the assistant</a>`) +
    `<div class="grid g4">${kp.map(([l, v]) => `<div class="card kpi"><div class="l">${l}</div><div class="v">${v}</div></div>`).join("")}</div>
  <div class="grid g2 mt"><div class="card"><h2>Pending approvals</h2>${d.pending_approvals.length ? d.pending_approvals.map(p => `<div class="step"><div><b>${esc(agentName(p.agent))}</b><div class="small muted">${esc(p.summary)}</div></div><span class="sp"></span><a class="btn sm" href="#/executions/${p.id}">Review</a></div>`).join("") : empty("Nothing waiting", "Agent drafts that need your sign-off appear here.")}</div>
  <div class="card"><h2>Agent activity by status</h2>${donut(d.tasks_by_status, "Tasks by status")}</div>
  <div class="card"><h2>Tasks by agent</h2>${Object.keys(d.tasks_by_agent).length ? chartSvg({ title: "Tasks by agent", kind: "bar", labels: Object.keys(d.tasks_by_agent).map(agentName), series: [{ name: "Tasks", values: Object.values(d.tasks_by_agent) }] }) : empty("No agent runs yet", "Run an agent from the marketplace.", `<a class="btn" href="#/agents">Open marketplace</a>`)}</div>
  <div class="card"><h2>Plan usage (${esc(u.plan_name)})</h2>${bar("Projects", u.projects)}<br>${bar("Members", u.members)}<br>${bar("Agent tasks this month", u.agent_tasks_month)}<p class="small muted mt">${esc(u.token_tracking)}</p></div>
  <div class="card"><h2>Recent projects</h2>${d.recent_projects.length ? d.recent_projects.map(p => `<div class="step"><a href="#/project/${p.id}"><b>${esc(p.title)}</b></a>${badge(p.domain, "brand")}<span class="sp"></span><span class="small muted">${esc(ago(p.updated_at))}</span></div>`).join("") : empty("No projects", "Create your first project.", `<a class="btn pri" href="#/projects">New project</a>`)}</div>
  <div class="card"><h2>Recent activity</h2>${d.recent_activity.map(a => `<div class="small step"><span>${esc(a.action)}</span><span class="sp"></span><span class="muted">${esc(ago(a.timestamp))}</span></div>`).join("") || empty("No activity", "")}</div></div>`;
};

PAGES.projects = async (_, el) => {
  const draw = async () => {
    S.projects = await api("/projects");
    el.innerHTML = pageHead("Projects", "Each project has its own documents, evidence index and agent results.", `<button class="btn pri" id="np">＋ New project</button>`) +
      (S.projects.length ? `<div class="grid g3">${S.projects.map(p => `<div class="card agent-card" data-open="${p.id}"><div class="row"><h2>${esc(p.title)}</h2><span class="sp"></span>${badge(p.domain, "brand")}</div><p class="muted small">${esc(p.description || "No description")}</p><div class="row small"><span>▤ ${p.document_count} docs</span><span>◈ ${p.vendor_count} vendors</span>${p.latest_run_status ? badge(p.latest_run_status) : ""}</div></div>`).join("")}</div>` : `<div class="card">${empty("No projects yet", "Create a project to upload documents and run agents.")}</div>`);
    el.querySelectorAll("[data-open]").forEach(c => c.onclick = () => { setProject(c.dataset.open); location.hash = "#/project/" + c.dataset.open; });
    $("#np").onclick = () => modal(`<h2>New project</h2><form id="pf" class="mt"><label class="f"><span>Title</span><input name="title" required minlength="2" maxlength="255"></label><label class="f"><span>Description</span><textarea name="description"></textarea></label><label class="f"><span>Domain</span><select name="domain">${["general", ...S.platforms.map(p => p.id)].map(d => `<option value="${d}" ${d === (window.__newDomain || "general") ? "selected" : ""}>${esc(S.platforms.find(p => p.id === d)?.name || "General")}</option>`).join("")}</select></label><div class="row"><button class="btn pri">Create</button><button type="button" class="btn" onclick="closeModal()">Cancel</button></div></form>`, m => {
      $("#pf", m).onsubmit = async e => { e.preventDefault(); try { const p = await api("/projects", { method: "POST", body: Object.fromEntries(new FormData(e.target)) }); closeModal(); window.__newDomain = "general"; await loadCore(); S.pid = p.id; try { localStorage.setItem("pm_pid", p.id); } catch (x) {} toast("Project created", "ok"); location.hash = "#/project/" + p.id; } catch (er) { if (er.status === 402) { closeModal(); toast(er.message + " Open Plan & Usage to upgrade.", "bad"); } else fail(er); } };
    });
  };
  await draw();
};

PAGES.project = async (id, el) => {
  if (id && id !== S.pid) { S.pid = id; try { localStorage.setItem("pm_pid", id); } catch (e) {} }
  const p = curProject(); if (!p) { el.innerHTML = needProject(); return; }
  let tab = "overview";
  const draw = async () => {
    el.innerHTML = pageHead(p.title, `${p.domain} project · ${p.description || "no description"}`, `<button class="btn" id="up">⬆ Upload document</button>`) + `<div class="tabs">${["overview", "documents", "ask", "agents", "history"].map(t => `<button data-t="${t}" class="${t === tab ? "on" : ""}">${t[0].toUpperCase() + t.slice(1)}</button>`).join("")}</div><div id="tab">${skeleton()}</div>`;
    el.querySelectorAll("[data-t]").forEach(b => b.onclick = () => { tab = b.dataset.t; draw(); });
    $("#up").onclick = () => uploadModal(p.id, draw);
    const box = $("#tab");
    if (tab === "overview") {
      const [docs, tasks] = await Promise.all([api(`/projects/${p.id}/documents`), api(`/tasks?project_id=${p.id}&limit=5`)]);
      box.innerHTML = `<div class="grid g4">${[["Documents", docs.length], ["Pages", docs.reduce((a, d) => a + d.page_count, 0)], ["Vendors", p.vendor_count], ["Agent tasks", tasks.length]].map(([l, v]) => `<div class="card kpi"><div class="l">${l}</div><div class="v">${v}</div></div>`).join("")}</div>
      <div class="card mt"><h2>Quick actions</h2><div class="row">${(S.platforms.find(x => x.id === p.domain)?.agents || ["document_intelligence", "rag", "procurement", "vendor_intelligence", "compliance", "financial", "contract", "data_analyst", "report"]).map(a => `<button class="btn sm" data-run="${a}">${esc(agentName(a))}</button>`).join("")}</div></div>
      <div class="card mt"><h2>Recent agent tasks</h2>${tasks.map(t => `<div class="step"><b>${esc(t.agent_name)}</b>${badge(t.status)}<span class="small muted">${esc(t.summary.slice(0, 110))}</span><span class="sp"></span><a class="btn sm" href="#/executions/${t.id}">Open</a></div>`).join("") || empty("No runs yet", "Use a quick action above.")}</div>`;
      box.querySelectorAll("[data-run]").forEach(b => b.onclick = () => agentForm(S.agents.find(a => a.id === b.dataset.run), draw));
    } else if (tab === "documents") { await docsTable(box, `/projects/${p.id}/documents`, p.id, draw); }
    else if (tab === "ask") { chatView(box, p.id); }
    else if (tab === "agents") { box.innerHTML = agentGrid(); bindAgentGrid(box, draw); }
    else { const tasks = await api(`/tasks?project_id=${p.id}&limit=50`); box.innerHTML = tasksTable(tasks); }
  };
  await draw();
  S.pollers.push(setInterval(async () => { if (tab === "documents" && !$("#up")?.disabled) { const docs = await api(`/projects/${p.id}/documents`).catch(() => []); if (docs.some(d => ["pending", "processing"].includes(d.processing_status))) draw(); } }, 4000));
};
async function docsTable(box, url, pid, reload, showProject = false) {
  const docs = await api(url);
  box.innerHTML = docs.length ? `<div class="tablewrap"><table><thead><tr><th>File</th>${showProject ? "<th>Project</th>" : ""}<th>Type</th><th>Pages</th><th>Status</th><th>Uploaded</th><th></th></tr></thead><tbody>${docs.map(d => `<tr><td>${esc(d.filename || d.original_filename)}</td>${showProject ? `<td>${esc(d.project)}</td>` : ""}<td>${badge(d.type || d.document_type, "brand")}</td><td>${d.pages ?? d.page_count}</td><td>${badge(d.status || d.processing_status)}${d.processing_error ? `<div class="small" style="color:var(--bad)">${esc(d.processing_error)}</div>` : ""}</td><td class="small muted">${esc(ago(d.created_at))}</td><td><button class="btn sm bad" data-del="${d.id}">Delete</button></td></tr>`).join("")}</tbody></table></div>` : empty("No documents", "Upload a PDF, DOCX, XLSX, CSV or TXT file.", pid ? `<button class="btn pri" id="up2">Upload</button>` : "");
  const u = $("#up2", box); if (u) u.onclick = () => uploadModal(pid, reload);
  box.querySelectorAll("[data-del]").forEach(b => b.onclick = async () => { if (!confirm("Delete this document and its index entries?")) return; try { await api("/documents/" + b.dataset.del, { method: "DELETE" }); reload(); } catch (e) { fail(e); } });
}
const tasksTable = tasks => tasks.length ? `<div class="tablewrap"><table><thead><tr><th>Agent</th><th>Status</th><th>Summary</th><th>When</th><th></th></tr></thead><tbody>${tasks.map(t => `<tr><td>${esc(t.agent_name)}</td><td>${badge(t.status)}</td><td class="small">${esc(t.summary.slice(0, 140))}</td><td class="small muted">${esc(ago(t.created_at))}</td><td><a class="btn sm" href="#/executions/${t.id}">Open</a></td></tr>`).join("")}</tbody></table></div>` : empty("No agent tasks", "Run an agent to see its execution history here.");

function agentGrid() { return `<div class="grid g3">${S.agents.map(a => `<div class="card agent-card" data-agent="${a.id}"><div class="row"><h2>${esc(a.name)}</h2></div><div class="row">${badge(a.domain, "brand")}${a.requires_approval ? badge("approval", "warn") : ""}${a.writes ? badge("writes", "info") : badge("read-only")}</div><p class="muted small">${esc(a.description)}</p><p class="small"><i>“${esc(a.example)}”</i></p></div>`).join("")}</div>`; }
function bindAgentGrid(root, reload) { root.querySelectorAll("[data-agent]").forEach(c => c.onclick = () => agentForm(S.agents.find(a => a.id === c.dataset.agent), reload)); }
PAGES.agents = async (_, el) => { el.innerHTML = pageHead("Agent Marketplace", "12 specialist agents and a supervisor. Click an agent to see its tools and permissions, then run it.") + agentGrid(); bindAgentGrid(el, () => {}); };

/* assistant */
function chatView(box, pid, convId) {
  box.innerHTML = `<div class="card"><div class="chat" id="chat">${empty("Ask anything about your project documents", "Answers cite the document and page. If the documents don't contain it, the assistant says so.")}</div>
  <form id="cf" class="row mt"><input id="cm" class="sp" placeholder="e.g. What is the maximum delivery time allowed?" required maxlength="4000" autocomplete="off"><select id="ca" title="Agent">${`<option value="auto">Auto-route</option>` + S.agents.filter(a => a.id !== "workflow").map(a => `<option value="${a.id}">${esc(a.name)}</option>`).join("")}</select><button class="btn pri" id="cs">Send</button></form></div>`;
  const chat = $("#chat", box); let cid = convId || null;
  const add = (role, html) => { if (chat.querySelector(".empty")) chat.innerHTML = ""; chat.insertAdjacentHTML("beforeend", `<div class="msg ${role}">${html}</div>`); chat.scrollTop = chat.scrollHeight; };
  if (convId) api("/conversations/" + convId).then(c => { chat.innerHTML = ""; c.messages.forEach(m => add(m.role === "user" ? "user" : "ai", esc(m.content))); }).catch(fail);
  $("#cf", box).onsubmit = async e => {
    e.preventDefault(); const m = $("#cm", box).value.trim(); if (!m) return; $("#cm", box).value = ""; add("user", esc(m)); add("ai", `<span class="spin"></span> Thinking…`); $("#cs", box).disabled = true;
    try { const r = await api("/chat", { method: "POST", body: { message: m, project_id: pid, conversation_id: cid, agent: $("#ca", box).value } }); cid = r.conversation_id; chat.lastChild.remove(); add("ai", `${esc(r.reply)}${r.task ? `<div class="mt" style="white-space:normal">${renderResult({ ...r.task.output, summary: "" })}</div>` : ""}${r.task ? `<div class="small muted mt">${badge(r.task.status)} ${esc(r.task.agent_name)} · <a href="#/executions/${r.task.id}">open run</a></div>` : ""}`); }
    catch (er) { chat.lastChild.remove(); add("ai", `<span style="color:var(--bad)">${esc(er.message)}</span>`); } finally { $("#cs", box).disabled = false; }
  };
}
PAGES.assistant = async (arg, el) => {
  const convs = await api("/conversations");
  el.innerHTML = pageHead("AI Assistant", curProject() ? `Asking within “${curProject().title}”. Evidence is shown separately from interpretation.` : "No project selected: the assistant will search across your workspace.") + `<div class="grid" style="grid-template-columns:240px 1fr"><div class="card"><h3>Conversations</h3>${convs.map(c => `<div class="step small"><a href="#/assistant/${c.id}" class="sp">${esc(c.title.slice(0, 28))}</a><button class="btn sm bad" data-dc="${c.id}" aria-label="Delete">✕</button></div>`).join("") || `<p class="muted small">None yet</p>`}<a class="btn sm mt" href="#/assistant">New chat</a></div><div id="cv"></div></div>`;
  chatView($("#cv"), S.pid, arg || null);
  try { const q = sessionStorage.getItem("pm_q"); if (q) { $("#cm").value = q; sessionStorage.removeItem("pm_q"); } } catch (e) {}
  el.querySelectorAll("[data-dc]").forEach(b => b.onclick = async () => { await api("/conversations/" + b.dataset.dc, { method: "DELETE" }); location.hash = "#/assistant"; render(); });
};

/* execution center */
PAGES.executions = async (arg, el) => {
  if (arg) { const t = await api("/tasks/" + arg); const kids = t.children || []; el.innerHTML = pageHead("Execution detail", `${t.agent_name} · ${t.id}`, `<a class="btn" href="#/executions">← All executions</a>`) + `<div id="tv">${taskView(t)}</div>${kids.length ? `<h2 class="mt">Delegated tasks</h2>${kids.map(taskView).join("")}` : ""}`; bindTaskActions(el, () => render()); return; }
  const draw = async () => {
    const [all, pend] = await Promise.all([api("/tasks?limit=100"), api("/tasks?status=awaiting_approval")]);
    el.innerHTML = pageHead("Execution Center", "Every agent run with status, duration and retries. Human approvals are decided here.") + (pend.length ? `<div class="card" style="border-color:var(--warn)"><h2>Waiting for your approval (${pend.length})</h2>${pend.map(t => `<div class="step"><b>${esc(t.agent_name)}</b><span class="small muted sp">${esc(t.summary.slice(0, 120))}</span><a class="btn sm" href="#/executions/${t.id}">Review & decide</a></div>`).join("")}</div><div class="mt"></div>` : "") + tasksTable(all);
  };
  await draw(); S.pollers.push(setInterval(draw, 8000));
};

/* documents / reports */
PAGES.documents = async (_, el) => { el.innerHTML = pageHead("Documents", "All documents across your projects.", curProject() ? `<button class="btn pri" id="ud">⬆ Upload to ${esc(curProject().title)}</button>` : "") + `<div id="dt">${skeleton()}</div>`; const draw = () => docsTable($("#dt"), "/documents-all", null, () => render(), true); await draw(); const b = $("#ud"); if (b) b.onclick = () => uploadModal(S.pid, () => render()); };
PAGES.reports = async (_, el) => {
  const rs = await api("/reports-all");
  el.innerHTML = pageHead("Reports", "Generated PDF / Excel reports.", curProject() ? `<button class="btn pri" id="gr">Generate for ${esc(curProject().title)}</button>` : "") + (rs.length ? `<div class="tablewrap"><table><thead><tr><th>File</th><th>Project</th><th>Type</th><th>Generated</th><th></th></tr></thead><tbody>${rs.map(r => `<tr><td>${esc(r.filename)}</td><td>${esc(r.project)}</td><td>${badge(r.type, "brand")}</td><td class="small muted">${esc(ago(r.generated_at))}</td><td><button class="btn sm" data-dl="${r.id}" data-fn="${esc(r.filename)}">Download</button></td></tr>`).join("")}</tbody></table></div>` : `<div class="card">${empty("No reports yet", "Run the procurement agent, then generate a report.")}</div>`);
  el.querySelectorAll("[data-dl]").forEach(b => b.onclick = async () => { try { const res = await api(`/reports/${b.dataset.dl}/download`, { raw: true }); const u = URL.createObjectURL(await res.blob()); const a = document.createElement("a"); a.href = u; a.download = b.dataset.fn; a.click(); URL.revokeObjectURL(u); } catch (e) { fail(e); } });
  const g = $("#gr"); if (g) g.onclick = () => agentForm(S.agents.find(a => a.id === "report"), () => {});
};

/* module pages: procurement, vendors, financial, bi, contracts share one pattern */
function modulePage(title, sub, agents, extra) {
  return async (_, el) => {
    el.innerHTML = pageHead(title, sub) + needProject();
    if (!curProject()) return;
    const draw = async () => {
      const tasks = (await api(`/tasks?project_id=${S.pid}&limit=100`)).filter(t => agents.includes(t.agent));
      const latest = tasks.find(t => t.status === "completed") || tasks[0]; const full = latest ? await api("/tasks/" + latest.id) : null;
      if (!el.isConnected) return;
      el.innerHTML = pageHead(title, `${sub} Project: ${curProject().title}`, agents.map(a => `<button class="btn pri sm" data-run="${a}">▶ ${esc(agentName(a))}</button>`).join("")) + (extra ? await extra() : "") + (full ? taskView(full) : `<div class="card">${empty("No results yet", "Run an agent above. Results are computed from your uploaded documents only.")}</div>`) + (tasks.length > 1 ? `<h2 class="mt">History</h2>${tasksTable(tasks)}` : "");
      el.querySelectorAll("[data-run]").forEach(b => b.onclick = () => agentForm(S.agents.find(a => a.id === b.dataset.run), draw)); bindTaskActions(el, draw);
    };
    await draw();
  };
}
PAGES.procurement = modulePage("Procurement", "Requirements, quotations and the supervised comparison pipeline.", ["procurement", "compliance", "communication"]);
PAGES.financial = modulePage("Financial Intelligence", "Budget variance and quotation cost comparison.", ["financial"]);
PAGES.bi = modulePage("Business Intelligence", "Exploratory analysis of CSV / XLSX datasets.", ["data_analyst"]);
PAGES.contracts = modulePage("Contract Intelligence", "Clauses, dates, risks and renewal reminders.", ["contract"]);
PAGES.vendors = modulePage("Vendor Intelligence", "Transparent risk scoring from stored compliance and price results.", ["vendor_intelligence"], async () => {
  const vs = await api(`/projects/${S.pid}/vendors`);
  return vs.length ? `<div class="card" style="margin-bottom:16px"><h2>Vendors in this project</h2><div class="tablewrap"><table><thead><tr><th>Vendor</th><th>Quotations</th><th>Specifications</th></tr></thead><tbody>${vs.map(v => `<tr><td>${esc(v.vendor_name || v.name)}</td><td>${(v.quotations || []).length}</td><td>${(v.specifications || []).length}</td></tr>`).join("")}</tbody></table></div></div>` : "";
});

/* workflows */
PAGES.workflows = async (_, el) => {
  const wfs = await api("/workflows");
  el.innerHTML = pageHead("Workflows", "Chain agents with human approval checkpoints. Failures are recorded, never silent.", `<button class="btn pri" id="nw">＋ Build workflow</button>`) +
    (wfs.length ? `<div class="grid g2">${wfs.map(w => `<div class="card"><div class="row"><h2>${esc(w.name)}</h2><span class="sp"></span>${w.schedule_minutes ? badge("every " + w.schedule_minutes + " min", "info") : badge("manual")}</div><p class="muted small">${esc(w.description)}</p><div class="steps">${w.steps.map((s, i) => `<div class="step"><b>${i + 1}</b>${s.type === "approval" ? `${badge("approval", "warn")} ${esc(s.title || "Human approval")}` : esc(agentName(s.agent))}</div>`).join("")}</div><div class="row mt"><button class="btn pri sm" data-wr="${w.id}">▶ Run</button><button class="btn sm" data-wh="${w.id}">Runs</button></div><div id="wr-${w.id}"></div></div>`).join("")}</div>` : `<div class="card">${empty("No workflows", "Build one, e.g. Data analysis → Manager approval → Report.")}</div>`);
  el.querySelectorAll("[data-wr]").forEach(b => b.onclick = async () => { b.disabled = true; try { const r = await api(`/workflows/${b.dataset.wr}/run`, { method: "POST", body: {} }); toast("Run " + r.status.replaceAll("_", " "), r.status === "failed" ? "bad" : "ok"); showRuns(b.dataset.wr); } catch (e) { fail(e); } b.disabled = false; });
  el.querySelectorAll("[data-wh]").forEach(b => b.onclick = () => showRuns(b.dataset.wh));
  async function showRuns(id) { const runs = await api(`/workflows/${id}/runs`); $("#wr-" + id).innerHTML = `<div class="mt">${runs.slice(0, 5).map(r => `<div class="step small">${badge(r.status)} ${esc(r.trigger)} · step ${r.cursor}/${(r.step_results || []).length || "?"} <span class="sp"></span>${esc(ago(r.started_at || r.created_at))}${r.error ? `<span style="color:var(--bad)"> ${esc(r.error)}</span>` : ""}${r.status === "awaiting_approval" ? `<a class="btn sm" href="#/executions">Approve</a>` : ""}${["running", "awaiting_approval"].includes(r.status) ? `<button class="btn sm bad" data-cr="${r.id}">Cancel</button>` : ""}</div>`).join("") || `<span class="muted small">No runs yet</span>`}</div>`; el.querySelectorAll("[data-cr]").forEach(b => b.onclick = async () => { await api(`/workflow-runs/${b.dataset.cr}/cancel`, { method: "POST" }); showRuns(id); }); }
  $("#nw").onclick = () => {
    const steps = []; const ids = S.agents.filter(a => !["supervisor", "workflow"].includes(a.id));
    const paint = m => { $("#sl", m).innerHTML = steps.map((s, i) => `<div class="step"><b>${i + 1}</b>${s.type === "approval" ? badge("approval", "warn") : esc(agentName(s.agent))}<span class="sp"></span><button type="button" class="btn sm" data-rm="${i}">✕</button></div>`).join("") || `<span class="muted small">Add steps below</span>`; m.querySelectorAll("[data-rm]").forEach(b => b.onclick = () => { steps.splice(+b.dataset.rm, 1); paint(m); }); };
    modal(`<h2>Build workflow</h2><form id="wf" class="mt"><label class="f"><span>Name</span><input name="name" required minlength="2"></label><label class="f"><span>Description</span><input name="description"></label><label class="f"><span>Schedule (minutes, optional, paid plans)</span><input name="schedule_minutes" type="number" min="5"></label><div class="steps" id="sl"></div><div class="row mt"><select id="sa">${ids.map(a => `<option value="${a.id}">${esc(a.name)}</option>`).join("")}</select><button type="button" class="btn sm" id="aa">Add agent</button><button type="button" class="btn sm" id="ap">Add approval</button></div><p class="small muted">Scope: ${esc(curProject()?.title || "no project selected")}</p><div class="row mt"><button class="btn pri">Save</button><button type="button" class="btn" onclick="closeModal()">Cancel</button></div></form>`, m => {
      paint(m); $("#aa", m).onclick = () => { steps.push({ agent: $("#sa", m).value, params: {} }); paint(m); }; $("#ap", m).onclick = () => { steps.push({ type: "approval", title: "Human approval required" }); paint(m); };
      $("#wf", m).onsubmit = async e => { e.preventDefault(); const f = Object.fromEntries(new FormData(e.target)); const body = { name: f.name, description: f.description, steps, project_id: S.pid }; if (f.schedule_minutes) body.schedule_minutes = Number(f.schedule_minutes); try { await api("/workflows", { method: "POST", body }); closeModal(); toast("Workflow saved", "ok"); render(); } catch (er) { fail(er); } };
    });
  };
};

/* notifications, activity */
PAGES.notifications = async (_, el) => {
  const n = await api("/notifications");
  el.innerHTML = pageHead("Notifications", `${n.unread} unread`, `<button class="btn" id="mr">Mark all read</button>`) + (n.items.length ? n.items.map(x => `<div class="card" style="margin-bottom:10px;${x.is_read ? "opacity:.7" : ""}"><div class="row"><b>${esc(x.title)}</b>${badge(x.kind)}<span class="sp"></span><span class="small muted">${esc(ago(x.created_at))}</span></div><div class="muted small">${esc(x.body)}</div></div>`).join("") : `<div class="card">${empty("You're all caught up", "Approvals, failures and contract reminders will appear here.")}</div>`);
  $("#mr").onclick = async () => { await api("/notifications/read", { method: "POST" }); render(); };
};
PAGES.activity = async (_, el) => {
  const a = await api("/activity");
  el.innerHTML = pageHead("Activity & Audit", "Immutable record of who did what.") + (a.length ? `<div class="tablewrap"><table><thead><tr><th>When</th><th>Actor</th><th>Action</th><th>Resource</th></tr></thead><tbody>${a.map(x => `<tr><td class="small muted">${esc(fmtDate(x.timestamp))}</td><td>${esc(x.actor)}</td><td>${esc(x.action)}</td><td class="small">${esc(x.resource_type)}</td></tr>`).join("")}</tbody></table></div>` : `<div class="card">${empty("No activity yet", "")}</div>`);
};

/* team, subscription, settings */
PAGES.team = async (_, el) => {
  const draw = async () => {
    const m = await api(`/orgs/${S.org.id}/members`), canManage = ["owner", "admin"].includes(S.org.role);
    el.innerHTML = pageHead("Team", `${S.org.name}: roles control what members can do.`, canManage ? `<button class="btn pri" id="am">＋ Add member</button>` : "") + `<div class="tablewrap"><table><thead><tr><th>Name</th><th>Email</th><th>Role</th><th></th></tr></thead><tbody>${m.map(x => `<tr><td>${esc(x.full_name)}</td><td>${esc(x.email)}</td><td>${canManage && x.role !== "owner" ? `<select data-role="${x.user_id}">${["admin", "member", "viewer"].map(r => `<option ${r === x.role ? "selected" : ""}>${r}</option>`).join("")}</select>` : badge(x.role, "brand")}</td><td>${canManage && x.role !== "owner" ? `<button class="btn sm bad" data-rm="${x.user_id}">Remove</button>` : ""}</td></tr>`).join("")}</tbody></table></div><p class="small muted mt">Owner/admin manage members. Members run agents and upload. Viewers are read-only. Members must already have an account.</p>`;
    el.querySelectorAll("[data-role]").forEach(s => s.onchange = async () => { try { await api(`/orgs/${S.org.id}/members/${s.dataset.role}`, { method: "PATCH", body: { role: s.value } }); toast("Role updated", "ok"); } catch (e) { fail(e); draw(); } });
    el.querySelectorAll("[data-rm]").forEach(b => b.onclick = async () => { if (confirm("Remove this member?")) { try { await api(`/orgs/${S.org.id}/members/${b.dataset.rm}`, { method: "DELETE" }); draw(); } catch (e) { fail(e); } } });
    const a = $("#am"); if (a) a.onclick = () => modal(`<h2>Add member</h2><form id="mf" class="mt"><label class="f"><span>Email of an existing user</span><input name="email" type="email" required></label><label class="f"><span>Role</span><select name="role"><option>member</option><option>viewer</option><option>admin</option></select></label><div class="row"><button class="btn pri">Add</button><button type="button" class="btn" onclick="closeModal()">Cancel</button></div></form>`, mm => { $("#mf", mm).onsubmit = async e => { e.preventDefault(); try { await api(`/orgs/${S.org.id}/members`, { method: "POST", body: Object.fromEntries(new FormData(e.target)) }); closeModal(); draw(); } catch (er) { fail(er); } }; });
  };
  await draw();
};
PAGES.subscription = async (_, el) => {
  const [plans, u] = await Promise.all([api("/plans"), api(`/orgs/${S.org.id}/usage`)]);
  const L = x => x == null ? "Unlimited" : x;
  el.innerHTML = pageHead("Plan & Usage", "Limits are enforced by the API. Billing is not connected: switching plan changes limits only, no payment is taken.") +
    `<div class="grid g4" style="margin-bottom:16px">${[["Projects", u.projects], ["Members", u.members], ["Agent tasks / month", u.agent_tasks_month], ["Webhooks", u.webhooks]].map(([l, x]) => `<div class="card kpi"><div class="l">${l}</div><div class="v">${x.used}<small class="muted"> / ${L(x.limit)}</small></div></div>`).join("")}</div>
  <div class="grid g4">${plans.map(p => `<div class="card" style="${p.key === u.plan ? "border-color:var(--brand)" : ""}"><h2>${esc(p.name)} ${p.key === u.plan ? badge("current", "ok") : ""}</h2><div class="v" style="font-size:24px;font-weight:700">$${p.price_usd_month}<small class="muted">/mo (display only)</small></div><ul class="small"><li>${L(p.projects)} projects</li><li>${L(p.members)} members</li><li>${L(p.agent_tasks_month)} agent tasks/mo</li><li>${L(p.webhooks)} webhooks</li>${(p.features || []).map(f => `<li>${esc(f)}</li>`).join("")}</ul>${p.key !== u.plan && S.org.role === "owner" ? `<button class="btn sm" data-plan="${p.key}">Switch to ${esc(p.name)}</button>` : ""}</div>`).join("")}</div>`;
  el.querySelectorAll("[data-plan]").forEach(b => b.onclick = async () => { try { await api(`/orgs/${S.org.id}/plan`, { method: "PUT", body: { plan: b.dataset.plan } }); await loadCore(); toast("Plan limits updated (no payment taken)", "ok"); render(); } catch (e) { fail(e); } });
};
PAGES.settings = async (_, el) => {
  const canManage = ["owner", "admin"].includes(S.org.role); let hooks = [], events = [];
  if (canManage) { try { [hooks, events] = await Promise.all([api(`/orgs/${S.org.id}/webhooks`), api("/webhook-events")]); } catch (e) {} }
  el.innerHTML = pageHead("Settings", "Profile, appearance and integrations.") + `<div class="grid g2"><div class="card"><h2>Profile</h2><p><b>${esc(S.user.full_name)}</b><br><span class="muted">${esc(S.user.email)}</span></p><p class="small muted">Organization: ${esc(S.org.name)} (${esc(S.org.role)})</p></div>
  <div class="card" id="llmc"><h2>AI model (LLM)</h2><div class="skel"></div></div>
  <div class="card"><h2>Appearance</h2><div class="row"><button class="btn" data-th="light">☀ Light</button><button class="btn" data-th="dark">☾ Dark</button></div></div>
  <div class="card" style="grid-column:1/-1"><div class="row"><h2>Webhooks</h2><span class="sp"></span>${canManage ? `<button class="btn sm pri" id="nh">＋ Add webhook</button>` : ""}</div><p class="small muted">Signed with HMAC-SHA256 in the <code>X-ProcuraMind-Signature</code> header. HTTPS only; private addresses are blocked. Requires a paid plan.</p>${hooks.length ? `<div class="tablewrap"><table><thead><tr><th>URL</th><th>Events</th><th>Last status</th><th></th></tr></thead><tbody>${hooks.map(h => `<tr><td>${esc(h.url)}</td><td class="small">${esc((h.events || []).join(", ") || "all")}</td><td>${esc(h.last_status ?? "-")}</td><td><button class="btn sm" data-ht="${h.id}">Test</button> <button class="btn sm bad" data-hd="${h.id}">Delete</button></td></tr>`).join("")}</tbody></table></div>` : empty("No webhooks", canManage ? "Add an HTTPS endpoint to receive agent events." : "Only owners/admins can manage webhooks.")}</div></div>`;
  api("/llm/status").then(l => { $("#llmc").innerHTML = `<h2>AI model (LLM)</h2><p>${l.configured ? badge("connected", "ok") : badge("not configured", "warn")} <b>${esc(l.provider)}</b> ${esc(l.model || "")}</p><p class="small muted">${esc(l.mode)}. Agents always compute results deterministically first; the LLM only adds a labelled, advisory interpretation, routing and grounded answers.</p>${l.configured ? (canManage ? `<button class="btn sm" id="lt">Test connection</button>` : "") : `<p class="small">${esc(l.how_to_enable)}</p>`}`; const t = $("#lt"); if (t) t.onclick = async () => { t.disabled = true; const r = await api(`/orgs/${S.org.id}/llm/test`, { method: "POST" }).catch(fail); toast(r?.ok ? "LLM reachable: " + r.model : "LLM test failed: " + (r?.error || ""), r?.ok ? "ok" : "bad"); t.disabled = false; }; }).catch(() => { $("#llmc").innerHTML = "<h2>AI model (LLM)</h2><p class='muted'>Status unavailable.</p>"; });
  el.querySelectorAll("[data-th]").forEach(b => b.onclick = () => setTheme(b.dataset.th));
  el.querySelectorAll("[data-ht]").forEach(b => b.onclick = async () => { try { const r = await api(`/webhooks/${b.dataset.ht}/test`, { method: "POST" }); toast("Delivered: " + r.last_status, r.delivered ? "ok" : "bad"); } catch (e) { fail(e); } });
  el.querySelectorAll("[data-hd]").forEach(b => b.onclick = async () => { await api("/webhooks/" + b.dataset.hd, { method: "DELETE" }); render(); });
  const nh = $("#nh"); if (nh) nh.onclick = () => modal(`<h2>Add webhook</h2><form id="hf" class="mt"><label class="f"><span>HTTPS URL</span><input name="url" type="url" required placeholder="https://example.com/hook"></label><label class="f"><span>Events (none selected = all)</span></label>${events.map(e => `<label class="small" style="display:block"><input type="checkbox" name="ev" value="${esc(e)}"> ${esc(e)}</label>`).join("")}<div class="row mt"><button class="btn pri">Create</button><button type="button" class="btn" onclick="closeModal()">Cancel</button></div></form>`, m => { $("#hf", m).onsubmit = async e => { e.preventDefault(); const fd = new FormData(e.target); try { const h = await api(`/orgs/${S.org.id}/webhooks`, { method: "POST", body: { url: fd.get("url"), events: fd.getAll("ev") } }); modal(`<h2>Webhook created</h2><p>Copy the signing secret now. It will not be shown again.</p><div class="draft">${esc(h.secret)}</div><div class="row mt"><button class="btn" data-copy="${esc(h.secret)}">Copy</button><button class="btn pri" onclick="closeModal();render()">Done</button></div>`); } catch (er) { er.status === 402 ? toast(er.message + " Upgrade the plan to use webhooks.", "bad") : fail(er); } }; });
};

PAGES.hub = async (_, el) => {
  const counts = {}; S.projects.forEach(p => counts[p.domain] = (counts[p.domain] || 0) + 1);
  el.innerHTML = pageHead("Platform Hub", "Each platform is a workspace type with its own agents and document types, all on one shared engine: projects, RAG, approvals, workflows and the LLM layer.", `<a class="btn" href="#/assistant">✦ Ask the assistant</a>`) +
    `<div class="grid g3">${S.platforms.map(p => `<div class="card agent-card" data-pl="${p.id}"><div class="row"><span style="font-size:26px">${p.icon}</span><h2>${esc(p.name)}</h2><span class="sp"></span>${badge((counts[p.id] || 0) + " projects", "brand")}</div><p class="muted">${esc(p.tagline)}</p><div class="row">${p.agents.slice(0, 6).map(a => badge(agentName(a).replace(" Agent", ""), "")).join("")}</div><div class="row mt"><button class="btn pri sm" data-open="${p.id}">Open</button><button class="btn sm" data-new="${p.id}">＋ New project</button></div></div>`).join("")}</div>
    <div class="card mt"><h2>${S.agents.length} agents, one orchestrator</h2><p class="muted small">Agents are deterministic and traceable; a configured LLM adds an advisory interpretation and can route requests. Anything that sends, approves or changes the outside world needs a human.</p></div>`;
  el.querySelectorAll("[data-pl]").forEach(c => c.onclick = () => location.hash = "#/platform/" + c.dataset.pl);
  el.querySelectorAll("[data-new]").forEach(b => b.onclick = e => { e.stopPropagation(); window.__newDomain = b.dataset.new; location.hash = "#/projects"; setTimeout(() => $("#np")?.click(), 400); });
};
PAGES.platform = async (id, el) => {
  const pl = S.platforms.find(p => p.id === id); if (!pl) { el.innerHTML = `<div class="card">${empty("Unknown platform", "")}</div>`; return; }
  const mine = S.projects.filter(p => p.domain === id), cur = curProject();
  let sel = pl.core_agents[0] || pl.agents[0];
  const draw = async () => {
    const tasks = cur ? (await api(`/tasks?project_id=${cur.id}&limit=100`)).filter(t => t.agent === sel) : [];
    const latest = tasks.find(t => t.status === "completed") || tasks[0]; const full = latest ? await api("/tasks/" + latest.id) : null;
    if (!el.isConnected) return;
    el.innerHTML = pageHead(pl.icon + " " + pl.name, pl.tagline, `<a class="btn" href="#/hub">← Hub</a>`) +
      `<div class="card"><div class="row"><b>Project:</b>${cur ? esc(cur.title) + " " + badge(cur.domain, "brand") : "none selected"}<span class="sp"></span>${mine.filter(p => !cur || p.id !== cur.id).slice(0, 4).map(p => `<button class="btn sm" data-sw="${p.id}">${esc(p.title)}</button>`).join("")}<button class="btn sm pri" id="npp">＋ New ${esc(pl.name)} project</button></div>
      <p class="small muted mt">Document types for this platform: ${pl.doc_types.map(t => badge(t.replaceAll("_", " "), "info")).join(" ")} · set the type when uploading, or let auto-classification detect it.</p>${cur && cur.domain !== id && cur.domain !== "general" ? `<p class="small" style="color:var(--warn)">The selected project belongs to another platform. Agents will still run on it.</p>` : ""}</div>
      <div class="tabs mt">${pl.agents.map(a => `<button data-ag="${a}" class="${a === sel ? "on" : ""}">${esc(agentName(a).replace(" Agent", ""))}</button>`).join("")}</div>
      <div class="row" style="margin-bottom:12px"><button class="btn pri" id="ra">▶ Run ${esc(agentName(sel))}</button><span class="small muted">${esc(S.agents.find(a => a.id === sel)?.description || "")}</span></div>
      ${!cur ? needProject() : full ? taskView(full) : `<div class="card">${empty("No results yet", "Upload the documents this agent needs, then run it. Results come only from your documents.")}</div>`}
      <div class="card mt"><h3>Try asking the assistant</h3><div class="row">${pl.starters.map(q => `<a class="btn sm" href="#/assistant" data-q="${esc(q)}">${esc(q)}</a>`).join("")}</div></div>`;
    el.querySelectorAll("[data-sw]").forEach(b => b.onclick = () => setProject(b.dataset.sw));
    el.querySelectorAll("[data-ag]").forEach(b => b.onclick = () => { sel = b.dataset.ag; draw(); });
    $("#ra").onclick = () => agentForm(S.agents.find(a => a.id === sel), draw);
    $("#npp").onclick = () => { window.__newDomain = id; location.hash = "#/projects"; setTimeout(() => $("#np")?.click(), 400); };
    el.querySelectorAll("[data-q]").forEach(a => a.onclick = () => { try { sessionStorage.setItem("pm_q", a.dataset.q); } catch (e) {} });
    bindTaskActions(el, draw);
  };
  await draw();
};
window.render = render;
boot();
