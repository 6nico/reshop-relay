/* Reshop Relay dashboard. The simulation itself is the Python package in /reshop_relay,
   run in the browser with Pyodide, so the web demo and the command line give identical results. */
const PY_FILES = ["__init__.py", "store.py", "sim.py", "metrics.py", "web.py"];
const SCENARIOS = { low: "Low volume", medium: "Medium volume", high: "High volume" };
const S = ["dedicated", "opportunistic", "hybrid"];
const LABEL = { dedicated: "Dedicated trips", opportunistic: "During existing trips", hybrid: "Hybrid" };
const SHORT = { dedicated: "Dedicated", opportunistic: "During trips", hybrid: "Hybrid" };
const COLOR = { dedicated: "var(--c-ded)", opportunistic: "var(--c-opp)", hybrid: "var(--c-hyb)" };
const SWEEP = {
  arrival_volume_multiplier: { label: "Reshop volume", vals: [0.5, 0.75, 1, 1.25, 1.5, 1.75] },
  cart_capacity: { label: "Items per cart", vals: [6, 8, 10, 12, 14] },
  max_detour_m_per_item: { label: "Max detour per item (m)", vals: [10, 15, 20, 30, 40] },
  coordination_sec: { label: "Extra coordination per pickup (sec)", vals: [0, 20, 40, 60, 90] },
  scan_sec: { label: "Scan time per item (sec)", vals: [1, 3, 5, 8, 12] },
  walk_speed_m_per_min: { label: "Walking speed (m/min)", vals: [45, 52, 60, 70, 80] },
  hybrid_backlog_trigger: { label: "Hybrid backlog trigger", vals: [8, 12, 15, 20, 30] },
};

const $ = (s) => document.querySelector(s);
let py, base = {}, cfg, last, busy = false;

const clone = (o) => JSON.parse(JSON.stringify(o));
const val = (k) => { const a = cfg.assumptions[k]; return typeof a === "object" ? a.value : a; };
const fmt = (n, d = 1) => (n === null || n === undefined || Number.isNaN(n)) ? "—" : Number(n).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
const pct = (n) => (n === null || n === undefined) ? "—" : (n >= 0 ? "" : "−") + Math.abs(n * 100).toFixed(1) + "%";
function clock(min) {
  const [h, m] = (cfg.clock_start || "00:00").split(":").map(Number);
  let t = h * 60 + m + Math.round(min); t = ((t % 1440) + 1440) % 1440;
  const hh = Math.floor(t / 60), mm = t % 60, ap = hh >= 12 ? "pm" : "am";
  return `${((hh + 11) % 12) + 1}:${String(mm).padStart(2, "0")}${ap}`;
}
function setEngine(text, ready) { const e = $("#engine"); e.lastChild.textContent = text; e.classList.toggle("ready", !!ready); }

// ---------------------------------------------------------------- boot
async function boot() {
  for (const k of Object.keys(SCENARIOS)) base[k] = await (await fetch(`scenarios/${k}.json`)).json();
  $("#scenario").innerHTML = Object.entries(SCENARIOS).map(([k, v]) => `<option value="${k}">${v}</option>`).join("");
  $("#scenario").value = "medium";
  loadScenario("medium");
  for (const sel of ["#mapStrategy", "#logStrategy"]) $(sel).innerHTML = S.map((s) => `<option value="${s}">${LABEL[s]}</option>`).join("");
  $("#mapStrategy").value = "hybrid"; $("#logStrategy").value = "hybrid";
  $("#sweepParam").innerHTML = Object.entries(SWEEP).map(([k, v]) => `<option value="${k}">${v.label}</option>`).join("");
  $("#legend1").innerHTML = $("#legend2").innerHTML = S.map((s) => `<span><i class="sw" style="background:${COLOR[s]}"></i>${LABEL[s]}</span>`).join("");
  $("#legend2").innerHTML = ["opportunistic", "hybrid"].map((s) => `<span><i class="sw" style="background:${COLOR[s]}"></i>${LABEL[s]}</span>`).join("") + `<span><i class="sw" style="background:var(--good)"></i>20% target</span>`;
  wire();
  try {
    py = await loadPyodide();
    py.FS.mkdir("/rr"); py.FS.mkdir("/rr/reshop_relay");
    for (const f of PY_FILES) py.FS.writeFile(`/rr/reshop_relay/${f}`, await (await fetch(`reshop_relay/${f}`)).text());
    py.runPython("import sys; sys.path.insert(0, '/rr'); from reshop_relay import web");
    setEngine("Live model", true);
    $("#run").disabled = false;
    run();
  } catch (err) {
    setEngine("Engine failed to load");
    $("#verdict").innerHTML = `<p class="hint">Could not load the Python engine (${err}). Try refreshing. You can also run it locally: <code>python -m reshop_relay run scenarios/medium.json</code></p>`;
  }
}

function loadScenario(k) {
  cfg = clone(base[k]);
  $("#scenarioDesc").textContent = cfg.description;
  $("#seed").value = cfg.seed;
  renderAssumptions();
}

const QUICK = {
  arrival_volume_multiplier: { label: "Reshop volume", min: 0.25, max: 2, step: 0.05, fmt: (v) => `${v}×` },
  cart_capacity: { label: "Items per cart", min: 4, max: 20, step: 1, fmt: (v) => `${v}` },
  max_detour_m_per_item: { label: "Max extra walk per item", min: 5, max: 60, step: 5, fmt: (v) => `${v} m` },
};
function renderAssumptions() {
  $("#quick").innerHTML = Object.entries(QUICK).filter(([k]) => cfg.assumptions[k]).map(([k, q]) => `
    <div class="slider">
      <div class="lbl"><span>${q.label}</span><b data-out="${k}">${q.fmt(val(k))}</b></div>
      <input type="range" min="${q.min}" max="${q.max}" step="${q.step}" value="${val(k)}" data-q="${k}">
    </div>`).join("");
  $("#quick").querySelectorAll("input").forEach((inp) => inp.addEventListener("input", () => {
    const k = inp.dataset.q, v = parseFloat(inp.value);
    cfg.assumptions[k].value = v;
    $(`[data-out="${k}"]`).textContent = QUICK[k].fmt(v);
    const adv = $(`#assumptions input[data-k="${k}"]`); if (adv) adv.value = v;
  }));
  const box = $("#assumptions");
  box.innerHTML = Object.entries(cfg.assumptions).filter(([k]) => !QUICK[k]).map(([k, a]) => `
    <div class="assump">
      <div class="lbl"><span>${a.label}</span><span class="src ${a.source}">${a.source}</span></div>
      <input type="number" step="any" data-k="${k}" value="${a.value}">
      ${a.note ? `<div class="note">${a.note}</div>` : ""}
    </div>`).join("");
  box.querySelectorAll("input").forEach((inp) => inp.addEventListener("change", () => {
    const v = parseFloat(inp.value);
    if (!Number.isNaN(v)) cfg.assumptions[inp.dataset.k].value = v;
  }));
}

function wire() {
  document.querySelectorAll("#tabs button").forEach((b) => b.onclick = () => {
    document.querySelectorAll("#tabs button").forEach((x) => x.classList.toggle("on", x === b));
    $("#view-results").hidden = b.dataset.tab !== "results";
    $("#view-track").hidden = b.dataset.tab !== "track";
    if (b.dataset.tab === "results" && last) render();
  });
  $("#scenario").onchange = (e) => { loadScenario(e.target.value); run(); };
  document.querySelectorAll("#busy button").forEach((b) => b.onclick = () => {
    document.querySelectorAll("#busy button").forEach((x) => x.classList.toggle("on", x === b));
    $("#scenario").value = b.dataset.s; loadScenario(b.dataset.s); run();
  });
  $("#reset").onclick = () => { loadScenario($("#scenario").value); run(); };
  $("#run").onclick = () => run();
  $("#mapStrategy").onchange = $("#mapWorker").onchange = () => drawMap();
  $("#logStrategy").onchange = () => drawDecisions();
  $("#sweepRun").onclick = () => runSweep();
  document.querySelectorAll("[data-exp]").forEach((b) => b.onclick = () => exportFile(b.dataset.exp));
  $("#import").onchange = async (e) => {
    const f = e.target.files[0]; if (!f) return;
    try { cfg = JSON.parse(await f.text()); $("#scenarioDesc").textContent = cfg.description || "Imported scenario"; $("#seed").value = cfg.seed || 1; renderAssumptions(); run(); }
    catch (err) { alertBox(`That file is not a valid scenario: ${err}`); }
  };
}
function alertBox(msg) { $("#verdict").innerHTML = `<p class="neg">${msg}</p>`; }

// ---------------------------------------------------------------- run
async function run() {
  if (!py || busy) return;
  busy = true; $("#run").disabled = true; $("#run").textContent = "Running…";
  await new Promise((r) => setTimeout(r, 30));
  try {
    cfg.seed = parseInt($("#seed").value || "1", 10);
    py.globals.set("cfg_json", JSON.stringify(cfg));
    last = JSON.parse(py.runPython(`web.run(cfg_json, ${cfg.seed})`));
    render();
  } catch (err) {
    const msg = String(err).split("\n").filter((l) => l.includes("Error")).pop() || String(err);
    alertBox(msg.replace(/^.*Error: /, "Can't run this setup: ") + (cfg.store.blocked && cfg.store.blocked.length ? " Click the red segment on the map again to reopen it." : ""));
    if (last) drawMap();
  } finally {
    busy = false; $("#run").disabled = false; $("#run").textContent = "Run simulation";
  }
}

function render() {
  drawVerdict(); drawKpis(); drawBacklog();
  const ws = cfg.workers.map((w) => `<option value="${w.id}">${w.name}</option>`).join("");
  const cur = $("#mapWorker").value;
  $("#mapWorker").innerHTML = `<option value="all">All team members</option>` + ws;
  $("#mapWorker").value = cur && [...$("#mapWorker").options].some((o) => o.value === cur) ? cur : "all";
  drawMap(); drawDecisions(); drawBusiness(); drawChecks();
}

// ---------------------------------------------------------------- verdict + table
const GUARD = { errors_not_higher: "errors", task_deadlines_kept: "task deadlines", closing_backlog_not_higher: "pile at close", oldest_item_not_older: "oldest item" };
const passes = (s) => Object.values(last.comparison[s].guardrails).every(Boolean);
const fails = (s) => Object.entries(last.comparison[s].guardrails).filter(([, ok]) => !ok).map(([k]) => GUARD[k]);
function pick() {
  const C = last.comparison;
  const ok = ["hybrid", "opportunistic"].filter((s) => passes(s) && C[s].reduction_vs_dedicated > 0).sort((a, b) => C[b].reduction_vs_dedicated - C[a].reduction_vs_dedicated);
  return ok[0] || null;
}
function drawVerdict() {
  const R = last.results, C = last.comparison, B = last.business;
  const win = pick(), s = win || "hybrid", d = R.dedicated, r = R[s];
  let head, body;
  if (win) {
    head = `Switch to ${LABEL[win].toLowerCase()}: ${pct(C[win].reduction_vs_dedicated)} less labor per item`;
    body = `It returns items with less walking and passes every service check: no extra errors, no late tasks, no bigger pile at close.`;
  } else {
    const more = r.closing_backlog - d.closing_backlog;
    head = `Keep dedicated trips for now`;
    body = `Hybrid saves ${pct(C.hybrid.reduction_vs_dedicated)} labor per item, but ${more > 0 ? `leaves ${fmt(more, 0)} more items unshelved at close` : `misses on ${fails("hybrid").join(", ")}`}. Grabbing reshop only during other trips saves more labor, but ${fmt(R.opportunistic.closing_backlog - d.closing_backlog, 0)} more items are left at close.`;
  }
  const tile = (big, small, cls = "") => `<div class="tile"><b class="${cls}">${big}</b><span>${small}</span></div>`;
  $("#verdict").innerHTML = `<p class="eyebrow">${win ? "Recommendation" : "Finding"}</p><h1>${head}</h1><p class="big">${body}</p>
    <div class="tiles">
      ${tile(pct(C[s].reduction_vs_dedicated), `less labor per item (${SHORT[s]})`, C[s].reduction_vs_dedicated > 0 ? "pos" : "neg")}
      ${tile(`${fmt(r.items_correct, 0)} <small>vs ${fmt(d.items_correct, 0)}</small>`, `items back on shelf`)}
      ${tile(`${fmt(r.closing_backlog, 0)} <small>vs ${fmt(d.closing_backlog, 0)}</small>`, `items left at close`, r.closing_backlog > d.closing_backlog ? "neg" : "pos")}
      ${tile(`${fmt(B[s].daily_hours_released, 1)} hrs`, `freed per day`)}
    </div>`;
  $("#runmeta").textContent = `${d.items_arrived} reshop items · 8-hour shift · 4 team members`;
}

function drawKpis() {
  const R = last.results, C = last.comparison;
  const rows = [
    ["Items back on shelf", (r) => fmt(r.items_correct, 0)],
    ["Items left at close", (r, s) => cmp(r.closing_backlog, R.dedicated.closing_backlog, s, 0)],
    ["Labor minutes per item", (r) => fmt(r.labor_min_per_correct_item, 2)],
    ["Labor saved vs today", (r, s) => s === "dedicated" ? `<span class="faint">baseline</span>` : `<span class="${C[s].reduction_vs_dedicated > 0 ? "pos" : "neg"}">${pct(C[s].reduction_vs_dedicated)}</span>`],
    ["Average wait before shelf", (r, s) => cmp(r.avg_wait_min, R.dedicated.avg_wait_min, s, 0, " min")],
    ["Placement errors", (r, s) => cmp(r.placement_errors, R.dedicated.placement_errors, s, 0)],
    ["Late tasks", (r, s) => cmp(r.tasks_late, R.dedicated.tasks_late, s, 0)],
    ["Passes all service checks", (r, s) => s === "dedicated" ? `<span class="faint">baseline</span>` : passes(s) ? `<span class="pos">Yes</span>` : `<span class="neg" title="Misses: ${fails(s).join(", ")}">No</span>`],
  ];
  let h = `<tr><th></th>${S.map((s) => `<th class="num"><i class="sw" style="background:${COLOR[s]}"></i>${LABEL[s]}</th>`).join("")}</tr>`;
  for (const [name, f] of rows) h += `<tr><td>${name}</td>${S.map((s) => `<td class="num">${f(R[s], s)}</td>`).join("")}</tr>`;
  $("#kpis").innerHTML = h;
}
function cmp(v, base, s, d, unit = "") {
  const t = fmt(v, d) + unit;
  if (s === "dedicated" || Math.abs(v - base) < 0.5) return t;
  return `<span class="${v > base ? "neg" : "pos"}">${t}</span>`;
}

// ---------------------------------------------------------------- charts
function svgLine(el, series, opts) {
  const W = Math.max(320, el.clientWidth || 760), H = el.clientHeight || opts.h || 260, P = { l: 46, r: 14, t: 12, b: 30 };
  const xs = series.flatMap((s) => s.pts.map((p) => p[0])), ys = series.flatMap((s) => s.pts.flatMap((p) => [p[1], p[2] ?? p[1], p[3] ?? p[1]]));
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  const step = opts.step || niceStep(Math.max(...ys, opts.ymax ?? 0) - Math.min(0, ...ys));
  const y0 = Math.floor(Math.min(0, ...ys, opts.ymin ?? 0) / step) * step, y1 = Math.ceil((Math.max(...ys, opts.ymax ?? 0) * 1.02 || 1) / step) * step;
  const X = (x) => P.l + (x - x0) / (x1 - x0 || 1) * (W - P.l - P.r), Y = (y) => H - P.b - (y - y0) / (y1 - y0) * (H - P.t - P.b);
  let g = "";
  for (let v = y0; v <= y1 + 1e-9; v += step) {
    g += `<line x1="${P.l}" x2="${W - P.r}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line)" stroke-width="1"/>`;
    g += `<text x="${P.l - 8}" y="${Y(v) + 4}" text-anchor="end" font-size="11" fill="var(--faint)" font-family="var(--mono)">${opts.yfmt ? opts.yfmt(v) : Math.round(v)}</text>`;
  }
  const ticks = opts.xticks || [];
  for (const t of ticks) g += `<text x="${X(t)}" y="${H - 8}" text-anchor="middle" font-size="11" fill="var(--faint)" font-family="var(--mono)">${opts.xfmt ? opts.xfmt(t) : t}</text>`;
  for (const ref of opts.refs || []) g += `<line x1="${P.l}" x2="${W - P.r}" y1="${Y(ref.y)}" y2="${Y(ref.y)}" stroke="${ref.color}" stroke-dasharray="5 5" stroke-width="1.5"/>`;
  for (const s of series) {
    if (s.band) g += `<path d="M${s.pts.map((p) => `${X(p[0])},${Y(p[3])}`).join("L")}L${[...s.pts].reverse().map((p) => `${X(p[0])},${Y(p[2])}`).join("L")}Z" fill="${s.color}" opacity=".15"/>`;
    g += `<polyline points="${s.pts.map((p) => `${X(p[0])},${Y(p[1])}`).join(" ")}" fill="none" stroke="${s.color}" stroke-width="2.2" stroke-linejoin="round"/>`;
    if (s.dots) g += s.pts.map((p) => `<circle cx="${X(p[0])}" cy="${Y(p[1])}" r="3.5" fill="${s.color}"/>`).join("");
  }
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}">${g}</svg>`;
}
function niceStep(range) {
  const raw = (range || 1) / 5, p = Math.pow(10, Math.floor(Math.log10(raw)));
  return [1, 2, 2.5, 5, 10].map((m) => m * p).find((s) => s >= raw);
}

function drawBacklog() {
  const series = S.map((s) => ({ color: COLOR[s], pts: last.results[s].backlog_series.map((p) => [p.t, p.open]) }));
  const end = Math.max(...series[0].pts.map((p) => p[0]));
  svgLine($("#backlogChart"), series, { xticks: [0, 120, 240, 360, end].filter((v, i, a) => v <= end && a.indexOf(v) === i), xfmt: clock });
}

function drawBars() {
  const R = last.results, el = $("#barChart"), W = Math.max(320, el.clientWidth || 760), H = el.clientHeight || 260, P = 30;
  const vals = S.map((s) => R[s].labor_min_per_correct_item || 0), m = Math.max(...vals) * 1.15 || 1;
  const bw = (W - P * 2) / 3 * 0.55;
  let g = "";
  S.forEach((s, i) => {
    const cx = P + (W - P * 2) / 3 * (i + 0.5), h = vals[i] / m * (H - 70);
    g += `<rect x="${cx - bw / 2}" y="${H - 34 - h}" width="${bw}" height="${h}" rx="6" fill="${COLOR[s]}" opacity=".9"/>`;
    g += `<text x="${cx}" y="${H - 40 - h}" text-anchor="middle" font-size="14" fill="var(--text)" font-family="var(--mono)">${fmt(vals[i], 2)}</text>`;
    g += `<text x="${cx}" y="${H - 12}" text-anchor="middle" font-size="12" fill="var(--muted)">${LABEL[s]}</text>`;
  });
  $("#barChart").innerHTML = `<svg viewBox="0 0 ${W} ${H}">${g}</svg>`;
}

// ---------------------------------------------------------------- map
function drawMap() {
  if (!last) return;
  const st = cfg.store, N = st.nodes, Hm = 80;
  const blocked = new Set((st.blocked || []).map(([a, b]) => [a, b].sort().join("|")));
  const sx = (n) => N[n].x + 4, sy = (n) => Hm - N[n].y - 2;
  let g = "";
  for (const [a, b] of st.edges) {
    const key = [a, b].sort().join("|");
    g += `<line class="edge ${blocked.has(key) ? "blocked" : ""}" data-e="${a}|${b}" x1="${sx(a)}" y1="${sy(a)}" x2="${sx(b)}" y2="${sy(b)}"><title>${N[a].label} ↔ ${N[b].label}${blocked.has(key) ? " (blocked)" : ""}</title></line>`;
  }
  const strat = $("#mapStrategy").value, who = $("#mapWorker").value;
  const evs = last.results[strat].events.filter((e) => e.kind === "walk" && e.path.length > 1 && (who === "all" || e.worker === who));
  for (const e of evs) {
    const rs = e.reshop_meters > 0.5;
    const pts = e.path.map((n) => `${sx(n)},${sy(n)}`).join(" ");
    g += `<polyline points="${pts}" fill="none" stroke="${rs ? "var(--accent)" : "var(--faint)"}" stroke-width="${rs ? 0.7 : 0.45}" opacity="${rs ? 0.35 : 0.18}" stroke-linejoin="round" pointer-events="none"/>`;
  }
  const deptNodes = new Set(Object.values(st.departments));
  for (const [k, n] of Object.entries(N)) {
    const isDept = deptNodes.has(k), isGS = k === st.guest_services;
    if (!isDept && !isGS && k !== "BR" && k !== "BRK" && k !== "CL") continue;
    g += `<g class="${isGS ? "gs" : "dept"}"><circle cx="${sx(k)}" cy="${sy(k)}" r="${isGS ? 1.8 : 1.3}"/>`;
    g += `<text x="${sx(k)}" y="${sy(k) - 2.4}" text-anchor="middle">${n.label}</text></g>`;
  }
  $("#map").innerHTML = `<svg viewBox="0 0 124 80">${g}</svg>`;
  $("#map").querySelectorAll(".edge").forEach((el) => el.onclick = () => toggleEdge(el.dataset.e.split("|")));
  const bl = st.blocked || [];
  const walked = evs.reduce((a, e) => a + e.reshop_meters, 0);
  $("#blocked").innerHTML = `${LABEL[strat]}: ${fmt(walked, 0)} m walked for reshop${who === "all" ? "" : " by this team member"}.` +
    (bl.length ? ` Blocked: ${bl.map(([a, b]) => `${N[a].label} ↔ ${N[b].label}`).join(", ")}. <a href="#" id="unblock">Clear</a>` : "");
  const ub = $("#unblock"); if (ub) ub.onclick = (e) => { e.preventDefault(); cfg.store.blocked = []; run(); };
}
function toggleEdge([a, b]) {
  const key = [a, b].sort().join("|");
  const bl = cfg.store.blocked || [];
  const i = bl.findIndex(([x, y]) => [x, y].sort().join("|") === key);
  if (i >= 0) bl.splice(i, 1); else bl.push([a, b]);
  cfg.store.blocked = bl; run();
}

// ---------------------------------------------------------------- decisions, business, checks
function drawDecisions() {
  if (!last) return;
  const d = last.results[$("#logStrategy").value].decisions;
  if (!d.length) { $("#decisions").innerHTML = `<tr><td class="hint">This strategy only makes separate reshop trips, so there are no pickup decisions during other work.</td></tr>`; return; }
  $("#decisions").innerHTML = `<tr><th>Time</th><th>Team member</th><th>Trip</th><th>Decision</th><th class="num">Items</th><th>Departments</th><th>Why</th></tr>` +
    d.map((x) => `<tr><td class="tag">${clock(x.t)}</td><td>${x.worker}</td><td>${x.task}</td><td class="${x.decision === "collect" ? "collect" : x.decision === "skip" ? "skip" : "dedicated"}">${x.decision}</td><td class="num">${x.items}</td><td>${x.departments.join(", ")}</td><td class="hint wrap">${x.reason}${x.extra_m != null ? ` · +${fmt(x.extra_m, 0)} m` : ""}</td></tr>`).join("");
}

function drawBusiness() {
  const B = last.business, win = pick(), s = win || "hybrid", b = B[s];
  $("#business").innerHTML = `
    <p class="hint" style="margin-bottom:12px">${LABEL[s]} compared with dedicated trips, one store.</p>
    <div class="biz">
      <div><b>${fmt(b.labor_min_saved_per_day, 0)}</b><span>labor minutes saved per day</span></div>
      <div><b>${fmt(b.daily_hours_released, 1)}</b><span>hours freed per day</span></div>
      <div><b>$${fmt(b.annual_capacity_value, 0)}</b><span>labor time per year</span></div>
    </div>
    <p class="hint">${win ? "" : `<span class="warn">Only counts once ${LABEL[s].toLowerCase()} passes every service check.</span> `}Freed hours go to other work; this is not a payroll cut. Uses ${val("operating_days")} days at $${val("hourly_labor_cost")}/hr.</p>`;
}

function drawChecks() {
  const names = { labor_matches_log: "Labor total matches event log", placed_matches_log: "Placed count matches event log", no_double_placement: "No item placed twice", every_placed_item_was_picked: "Every placed item was picked up first", items_conserved: "No item disappeared (placed + waiting = arrived)" };
  $("#checks").innerHTML = Object.keys(names).map((k) => `<div class="check"><span>${names[k]}</span><span>${S.map((s) => last.reconcile[s][k] ? `<span class="pos">✓</span>` : `<span class="neg">✗</span>`).join(" ")}</span></div>`).join("") +
    `<p class="hint" style="margin-top:8px">One mark each for dedicated, during trips, and hybrid. The same settings always give the same results.</p>`;
}

// ---------------------------------------------------------------- sensitivity
async function runSweep() {
  if (!py || busy) return;
  const p = $("#sweepParam").value, n = parseInt($("#sweepSeeds").value, 10);
  const seeds = Array.from({ length: n }, (_, i) => i + 1);
  busy = true; $("#sweepRun").disabled = true; $("#sweepRun").textContent = "Running…";
  await new Promise((r) => setTimeout(r, 30));
  try {
    py.globals.set("cfg_json", JSON.stringify(cfg));
    const rows = JSON.parse(py.runPython(`web.sweep(cfg_json, ${JSON.stringify(p)}, ${JSON.stringify(JSON.stringify(SWEEP[p].vals))}, ${JSON.stringify(JSON.stringify(seeds))})`));
    const series = ["opportunistic", "hybrid"].map((s) => ({ color: COLOR[s], band: true, dots: true, pts: rows.map((r) => [r.value, r[s].reduction_mean, r[s].reduction_min, r[s].reduction_max]) }));
    svgLine($("#sweepChart"), series, { h: 300, xticks: SWEEP[p].vals, yfmt: (v) => Math.round(v * 100) + "%", refs: [{ y: cfg.target_reduction || 0.2, color: "var(--good)" }, { y: 0, color: "var(--faint)" }], ymax: 0.25, step: 0.1 });
    $("#sweepTable").innerHTML = `<tr><th>${SWEEP[p].label}</th>${S.map((s) => `<th class="num">${LABEL[s]}: left at close</th>`).join("")}</tr>` +
      rows.map((r) => `<tr><td class="tag">${r.value}</td>${S.map((s) => `<td class="num ${s !== "dedicated" && r[s].closing_backlog_mean > r.dedicated.closing_backlog_mean ? "warn" : ""}">${fmt(r[s].closing_backlog_mean, 1)}</td>`).join("")}</tr>`).join("");
  } catch (err) { alertBox(String(err)); }
  finally { busy = false; $("#sweepRun").disabled = false; $("#sweepRun").textContent = "Run sweep"; }
}

// ---------------------------------------------------------------- export
function exportFile(kind) {
  let text, name, type = "text/csv";
  if (kind === "scenario") { text = JSON.stringify(cfg, null, 1); name = "scenario.json"; type = "application/json"; }
  else { if (!last) return; text = last.exports[kind]; name = { results_json: "results.json", summary_csv: "summary.csv", events_csv: "events.csv" }[kind]; if (kind === "results_json") type = "application/json"; }
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type }));
  a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

boot();
