"use strict";
/* Diabetic CKD Risk Explorer - front end (plain JavaScript, no build step, no external libraries).
   Flow: build the form -> validate in the browser -> POST /predict -> render results -> POST /sensitivity for the what-if chart.
   Every number shown comes from the API; this file only formats and draws. */

const $ = (sel, el = document) => el.querySelector(sel);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = (x, d = 0) => (100 * x).toFixed(d) + "%";
const pctileSentence = (p) => (p >= 99.5 ? "Your score is higher than almost all (over 99%) of the study patients."
  : p < 0.5 ? "Your score is lower than almost all (over 99%) of the study patients." : `Your score is higher than <b>${p.toFixed(0)}%</b> of study patients.`);
const YN = [[1, "Yes"], [0, "No"]];

/* ---------- 1. Form definition (one place; the form HTML and the validation are both generated from it) ---------- */
const GROUPS = [
  { title: "About you", fields: [
    { id: "sex", type: "seg", label: "Sex", options: [[0, "Female"], [1, "Male"]] },
    { id: "age", type: "num", label: "Age", unit: "years", min: 15, max: 110, step: 1 },
    { id: "bmi", type: "num", label: "Body-mass index (BMI)", unit: "kg/m²", min: 10, max: 60, step: 0.1, helper: "bmi" },
    { id: "job", type: "seg", label: "Type of work", options: [[1, "Desk-type"], [2, "Moderate"], [3, "Heavy"]],
      hint: "Desk-type: e.g. banker. Moderate: e.g. delivery worker. Heavy: e.g. construction worker." },
    { id: "fam", type: "seg", label: "Did your parents have diabetes?", options: YN },
  ]},
  { title: "Your diabetes", fields: [
    { id: "dy", type: "num", label: "Years since diabetes diagnosis", unit: "years", min: 0, max: 70, step: 1,
      hint: "Most study patients were 1–15 years in; longer durations are less reliable." },
    { id: "diet", type: "seg", label: "Follow the diet your doctor suggested?", options: YN },
    { id: "med", type: "seg", label: "Take oral diabetes medicine?", options: YN },
    { id: "ins", type: "seg", label: "Take insulin?", options: YN },
  ]},
  { title: "Other health", fields: [
    { id: "htn", type: "seg", label: "High blood pressure (140/90 or on treatment)?", options: YN },
    { id: "hd", type: "seg", label: "Diagnosed heart disease?", options: YN },
    { id: "uti", type: "seg", label: "History of urinary infection or urinary problems?", options: YN },
    { id: "urin", type: "seg", label: "Able to urinate without discomfort?", options: YN },
    { id: "pk", type: "seg", label: "Take pain-killers regularly?", options: YN },
  ]},
  { title: "Lifestyle", fields: [
    { id: "sleep", type: "seg", label: "Sleep 7–9 hours a night?", options: YN },
    { id: "water", type: "seg", label: "Drink more than 2 litres of water a day?", options: YN },
    { id: "smoke", type: "seg", label: "Smoke (5+ cigarettes a day for years)?", options: YN },
    { id: "zarda", type: "seg", label: "Use zarda or betel leaf?", options: YN },
    { id: "walk", type: "seg", label: "Walk 30+ minutes a day, regularly?", options: YN },
    { id: "cal", type: "num", label: "Typical daily calories", unit: "kcal/day", min: 500, max: 6000, step: 50,
      hint: "Study patients ranged from 1000 to 2400 kcal/day." },
  ]},
];
const ALL_FIELDS = GROUPS.flatMap((g) => g.fields);
const FIELD = Object.fromEntries(ALL_FIELDS.map((f) => [f.id, f]));
const TIER_TEXT = { Low: "Lower relative risk", Medium: "Moderate relative risk", High: "Higher relative risk" };

const form = $("#form");
let INFO = null;          // /model-info
let lastProfile = null;   // last validated profile, reused by the what-if explorer

function buildForm() {
  form.innerHTML = GROUPS.map((g) => `<div class="group"><h3>${esc(g.title)}</h3>${g.fields.map(fieldHtml).join("")}</div>`).join("");
  const h = $("#height"), w = $("#weight"), bmi = $("#bmi");
  const calc = () => {
    const hv = parseFloat(h.value), wv = parseFloat(w.value);
    if (hv > 90 && hv < 250 && wv > 20 && wv < 300) bmi.value = (wv / Math.pow(hv / 100, 2)).toFixed(1);
  };
  h.addEventListener("input", calc); w.addEventListener("input", calc);
  form.addEventListener("input", (e) => { const f = e.target.closest(".field"); if (f) f.classList.remove("invalid"); });
}

function fieldHtml(f) {
  const hint = f.hint ? `<div class="hint">${esc(f.hint)}</div>` : "";
  if (f.type === "seg") {
    const opts = f.options.map(([v, l]) => `<label><input type="radio" name="${f.id}" value="${v}"><span>${esc(l)}</span></label>`).join("");
    return `<div class="field" data-id="${f.id}"><div class="q" id="q-${f.id}">${esc(f.label)}</div><div class="seg" role="radiogroup" aria-labelledby="q-${f.id}">${opts}</div>${hint}</div>`;
  }
  const helper = f.helper === "bmi"
    ? `<div class="bmi-helper">Don't know your BMI? Height <input id="height" type="number" min="90" max="250" step="1" placeholder="cm" aria-label="Height in cm"> cm
       Weight <input id="weight" type="number" min="20" max="300" step="0.5" placeholder="kg" aria-label="Weight in kg"> kg</div>` : "";
  return `<div class="field num" data-id="${f.id}"><label class="q" for="${f.id}">${esc(f.label)} <span class="unit">${esc(f.unit)}</span></label>
    <input id="${f.id}" name="${f.id}" type="number" inputmode="decimal" min="${f.min}" max="${f.max}" step="${f.step}">${hint}${helper}</div>`;
}

/* ---------- 2. Reading and validating the form ---------- */
function readForm() {
  const profile = {}, problems = [];
  for (const f of ALL_FIELDS) {
    let v = null;
    if (f.type === "seg") {
      const c = form.querySelector(`input[name="${f.id}"]:checked`);
      v = c ? Number(c.value) : null;
    } else {
      const raw = form.querySelector(`#${f.id}`).value;
      v = raw === "" ? null : Number(raw);
    }
    if (v === null || Number.isNaN(v)) problems.push([f.id, "needs an answer"]);
    else if (f.type === "num" && (v < f.min || v > f.max)) problems.push([f.id, `must be between ${f.min} and ${f.max}`]);
    else profile[f.id] = v;
  }
  if (profile.dy !== undefined && profile.age !== undefined && profile.dy > profile.age) problems.push(["dy", "cannot be larger than age"]);
  return { profile, problems };
}

function showFormProblems(problems) {
  form.querySelectorAll(".field").forEach((el) => el.classList.remove("invalid"));
  const box = $("#form-error");
  if (!problems.length) { box.hidden = true; return; }
  problems.forEach(([id]) => { const el = form.querySelector(`.field[data-id="${id}"]`); if (el) el.classList.add("invalid"); });
  box.hidden = false;
  box.innerHTML = `Please fix ${problems.length} item${problems.length > 1 ? "s" : ""}:<ul>${problems.map(([id, m]) => `<li>${esc(FIELD[id] ? FIELD[id].label : id)}: ${esc(m)}</li>`).join("")}</ul>`;
  const first = form.querySelector(".field.invalid"); if (first) first.scrollIntoView({ block: "center", behavior: "smooth" });
}

function fillForm(profile) {
  for (const f of ALL_FIELDS) {
    if (profile[f.id] === undefined) continue;
    if (f.type === "seg") { const r = form.querySelector(`input[name="${f.id}"][value="${profile[f.id]}"]`); if (r) r.checked = true; }
    else form.querySelector(`#${f.id}`).value = profile[f.id];
  }
  $("#height").value = ""; $("#weight").value = "";
  showFormProblems([]);
}

/* ---------- 3. API calls ---------- */
async function api(path, body) {
  const res = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : undefined);
  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try {
      const d = await res.json();
      if (Array.isArray(d.detail)) msg = d.detail.map((e) => `${(e.loc || []).slice(-1)[0] || "input"}: ${e.msg}`).join("; ");
    } catch (_) { /* keep generic message */ }
    throw new Error(msg);
  }
  return res.json();
}

/* ---------- 4. Drawing helpers (inline SVG) ---------- */
function riskBarSvg(score, cuts) {
  const x = (p) => 20 + p * 560, y = 30, h = 20;
  const seg = (a, b, cls) => `<rect x="${x(a)}" y="${y}" width="${x(b) - x(a)}" height="${h}" style="fill:var(--${cls});opacity:.85"/>`;
  const mx = x(Math.min(Math.max(score, 0), 1));
  const tick = (p, label) => `<line x1="${x(p)}" x2="${x(p)}" y1="${y + h}" y2="${y + h + 5}" class="axis"/><text x="${x(p)}" y="${y + h + 18}" text-anchor="middle">${label}</text>`;
  return `<svg class="chart" viewBox="0 0 600 82" role="img" aria-label="Your model score ${pct(score)} on a scale from lower to higher relative risk">
    ${seg(0, cuts[0], "low")}${seg(cuts[0], cuts[1], "mid")}${seg(cuts[1], 1, "high")}
    <polygon points="${mx - 8},${y - 16} ${mx + 8},${y - 16} ${mx},${y - 2}" style="fill:var(--text)"/>
    <text x="${mx}" y="${y - 20}" text-anchor="${mx > 500 ? "end" : mx < 100 ? "start" : "middle"}" style="fill:var(--text);font-weight:600;font-size:12px">Your score ${pct(score)}</text>
    ${tick(0, "0%")}${tick(cuts[0], pct(cuts[0]))}${tick(cuts[1], pct(cuts[1]))}${tick(1, "100%")}</svg>`;
}

function histogramSvg(quantiles, score, cuts) {
  const bins = new Array(20).fill(0);
  quantiles.forEach((q) => { bins[Math.min(19, Math.floor(q * 20))] += 1; });
  const maxc = Math.max(...bins), W = 560, bw = W / 20, base = 120, H = 100;
  const x = (p) => 20 + p * W;
  const bg = (a, b, cls) => `<rect x="${x(a)}" y="10" width="${x(b) - x(a)}" height="${H + 10}" style="fill:var(--${cls});opacity:.12"/>`;
  const bars = bins.map((c, i) => { const hh = (c / maxc) * H; return `<rect x="${20 + i * bw + 2}" y="${base - hh}" width="${bw - 4}" height="${hh}" rx="2" style="fill:var(--muted);opacity:.55"/>`; }).join("");
  const mx = x(Math.min(Math.max(score, 0), 1));
  return `<svg class="chart" viewBox="0 0 600 150" role="img" aria-label="Distribution of study patients' scores with your score marked">
    ${bg(0, cuts[0], "low")}${bg(cuts[0], cuts[1], "mid")}${bg(cuts[1], 1, "high")}${bars}
    <line x1="20" x2="580" y1="${base}" y2="${base}" class="axis"/>
    <line x1="${mx}" x2="${mx}" y1="8" y2="${base}" style="stroke:var(--text);stroke-width:2;stroke-dasharray:4 3"/>
    <text x="${mx + (mx > 480 ? -6 : 6)}" y="20" text-anchor="${mx > 480 ? "end" : "start"}" style="fill:var(--text);font-weight:600">You</text>
    <text x="20" y="140">0%</text><text x="300" y="140" text-anchor="middle">model score of study patients →</text><text x="580" y="140" text-anchor="end">100%</text></svg>`;
}

function driversHtml(drivers) {
  const maxAbs = Math.max(...drivers.map((d) => Math.abs(d.contribution)), 1e-9);
  return `<div class="drivers">${drivers.map((d) => {
    const w = (Math.abs(d.contribution) / maxAbs) * 50;
    return `<div class="drv"><div class="name"><b>${esc(d.label)}</b><span>Your answer: ${esc(d.value_text)}</span></div>
      <div class="track" aria-hidden="true"><div class="bar ${d.direction}" style="width:${w}%"></div></div>
      <div class="val" title="Multiplies the odds by this factor, compared with an average study patient">odds ×${d.odds_multiplier.toFixed(2)}</div></div>`;
  }).join("")}</div>
  <div class="legend"><span><i style="background:var(--lower)"></i>lowers the score</span><span><i style="background:var(--raise)"></i>raises the score</span><span>compared with an average study patient</span></div>`;
}

function sensitivitySvg(s) {
  const pts = s.series, W = 560, H = 150, x0 = 40, y0 = 20;
  const scores = pts.map((p) => p.score).concat([s.current.score]);
  let lo = Math.max(0, Math.min(...scores) - 0.05), hi = Math.min(1, Math.max(...scores) + 0.05);
  if (hi - lo < 0.15) { hi = Math.min(1, lo + 0.15); }
  const y = (v) => y0 + H - ((v - lo) / (hi - lo)) * H;
  const grid = [lo, (lo + hi) / 2, hi].map((v) => `<line x1="${x0}" x2="${x0 + W}" y1="${y(v)}" y2="${y(v)}" class="axis"/><text x="${x0 - 6}" y="${y(v) + 4}" text-anchor="end">${pct(v)}</text>`).join("");
  let body = "";
  if (s.kind === "cont") {
    const xs = pts.map((p) => p.value), xmin = Math.min(...xs), xmax = Math.max(...xs);
    const x = (v) => x0 + 10 + ((v - xmin) / (xmax - xmin)) * (W - 20);
    const path = pts.map((p, i) => `${i ? "L" : "M"}${x(p.value)},${y(p.score)}`).join(" ");
    const inRange = s.current.value >= xmin && s.current.value <= xmax;
    body = `<path d="${path}" fill="none" style="stroke:var(--accent);stroke-width:2.5"/>` +
      pts.map((p) => `<circle cx="${x(p.value)}" cy="${y(p.score)}" r="3.5" style="fill:var(--accent)"/><text x="${x(p.value)}" y="${y0 + H + 18}" text-anchor="middle">${esc(p.value_text)}</text>`).join("") +
      (inRange ? `<line x1="${x(s.current.value)}" x2="${x(s.current.value)}" y1="${y0}" y2="${y0 + H}" style="stroke:var(--text);stroke-dasharray:4 3"/><circle cx="${x(s.current.value)}" cy="${y(s.current.score)}" r="6" style="fill:none;stroke:var(--text);stroke-width:2"/><text x="${x(s.current.value)}" y="${y0 - 6}" text-anchor="middle" style="fill:var(--text);font-weight:600">you</text>` : "");
  } else {
    const n = pts.length, bw = Math.min(110, (W - 20) / n - 20);
    body = pts.map((p, i) => {
      const cx = x0 + 10 + (i + 0.5) * ((W - 20) / n), top = y(p.score), isCur = Math.abs(p.value - s.current.value) < 1e-9;
      return `<rect x="${cx - bw / 2}" y="${top}" width="${bw}" height="${y0 + H - top}" rx="4" style="fill:var(--accent);opacity:${isCur ? 1 : 0.45}"/>
        <text x="${cx}" y="${top - 5}" text-anchor="middle" style="fill:var(--text);font-weight:600">${pct(p.score)}</text>
        <text x="${cx}" y="${y0 + H + 18}" text-anchor="middle" style="${isCur ? "fill:var(--text);font-weight:700" : ""}">${esc(p.value_text)}${isCur ? " (you)" : ""}</text>`;
    }).join("");
  }
  return `<svg class="chart" viewBox="0 0 620 205" role="img" aria-label="Model score as ${esc(s.label)} changes">${grid}${body}</svg>`;
}

/* ---------- 5. Rendering the result ---------- */
function renderResult(r, profile) {
  const prev = INFO ? INFO.cohort.prevalence : 0.4625;
  const warn = r.warnings.length ? `<div class="alert warn"><b>Input checks</b><ul>${r.warnings.map((w) => `<li>${esc(w.message)}</li>`).join("")}</ul></div>` : "";
  const notes = r.model_notes.length ? `<div class="section"><div class="alert warn"><b>Model notes: read before interpreting the drivers</b><ul>${r.model_notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul></div></div>` : "";
  const guid = r.guidance.map((g) => `<div class="g ${g.priority}"><div class="tag">${esc(g.topic)}</div><h4>${esc(g.title)}</h4><p>${esc(g.text)}</p></div>`).join("");
  const featOptions = Object.entries(INFO ? INFO.features : {}).map(([k, v]) => `<option value="${k}" ${k === "bmi" ? "selected" : ""}>${esc(v.label)}</option>`).join("");

  $("#result-body").innerHTML = `
    <div class="summary">
      <div><span class="tier-pill tier-${r.tier}">${TIER_TEXT[r.tier]}</span>
        <div class="big" style="margin-top:.6rem">${pct(r.tier_observed_ckd_rate)}</div>
        <div class="muted small">of similar study patients had a CKD diagnosis</div></div>
      <div><p class="lead">Patients in the study whose answers placed them in this group were diagnosed with CKD <b>${pct(r.tier_observed_ckd_rate)}</b> of the time
        (study average: ${pct(prev)}). ${pctileSentence(r.percentile)}</p>
        <p class="muted small">Model score: ${pct(r.score, 1)}. This is on the scale of a hospital sample in which almost half the patients had CKD; it is <b>not</b> your personal chance of getting CKD.</p></div>
    </div>
    ${warn}
    <div class="section"><h3>Where you sit</h3><p class="sub">Colours show the three groups the study patients were split into.</p>${riskBarSvg(r.score, r.cutpoints)}</div>
    <div class="section"><h3>How you compare with the 400 study patients</h3><p class="sub">Each bar is a slice of study patients by model score.</p>${histogramSvg(INFO ? INFO.cohort_score_quantiles : [], r.score, r.cutpoints)}</div>
    <div class="section"><h3>What shaped your score</h3><p class="sub">The six answers that moved your score most, compared with an average study patient. “Odds ×1.5” means that answer raised the odds of CKD in the model by half.</p>${driversHtml(r.drivers)}</div>
    ${notes}
    <div class="section"><h3>General health guidance</h3><p class="sub">${esc(r.guidance_status)}</p><div class="guid">${guid}</div>
      <details style="margin-top:.7rem"><summary>Where this guidance comes from</summary><ul>${r.guidance_sources.map((s) => `<li>${esc(s)}</li>`).join("")}</ul></details></div>
    <div class="section"><h3>What-if explorer</h3>
      <p class="sub">Change one answer and watch how the <b>model's score</b> reacts. This is not advice and not a prediction of what would happen to you.</p>
      <div class="whatif-controls"><label for="whatif-feature" class="muted small">Feature</label><select id="whatif-feature">${featOptions}</select></div>
      <div id="whatif-chart" aria-live="polite"></div><div id="whatif-note" class="alert info" hidden></div></div>
    <p class="muted small" style="margin-top:1.4rem">${esc(r.disclaimer)}</p>`;
  $("#placeholder").hidden = true; $("#result-body").hidden = false;
  $("#whatif-feature").addEventListener("change", () => loadSensitivity());
  loadSensitivity();
}

async function loadSensitivity() {
  const feat = $("#whatif-feature").value, chart = $("#whatif-chart"), note = $("#whatif-note");
  try {
    const s = await api("/sensitivity", { profile: lastProfile, feature: feat });
    chart.innerHTML = sensitivitySvg(s);
    note.hidden = false; note.className = "alert " + (s.contradicts_expectation ? "warn" : "info"); note.textContent = s.note;
  } catch (e) { chart.innerHTML = `<div class="alert error">${esc(e.message)}</div>`; }
}

function renderAbout(info) {
  const m = info.cv_metrics;
  $("#about-body").innerHTML = `
    <p>${esc(info.model_name)} trained on ${info.cohort.n_patients} patients (${info.cohort.n_ckd} with CKD, ${pct(info.cohort.prevalence, 1)}). Target: ${esc(info.target)}.</p>
    <table><tr><th>Honest performance (${esc(info.cv_protocol)})</th><th></th></tr>
      <tr><td>ROC-AUC</td><td>${m.auc.toFixed(3)} (95% CI ${info.cv_auc_ci95[0].toFixed(2)}–${info.cv_auc_ci95[1].toFixed(2)}): useful for ranking, far from diagnostic</td></tr>
      <tr><td>PR-AUC / Brier score</td><td>${m.ap.toFixed(3)} / ${m.brier.toFixed(3)}</td></tr>
      <tr><td>Calibration slope (ideal 1)</td><td>${info.calibration.slope.toFixed(2)}</td></tr>
      <tr><td>Observed CKD rate by group</td><td>Lower ${pct(info.risk_tiers.observed_ckd_rate.Low)} · Moderate ${pct(info.risk_tiers.observed_ckd_rate.Medium)} · Higher ${pct(info.risk_tiers.observed_ckd_rate.High)}</td></tr></table>
    <p><b>Limitations</b></p><ul>${info.limitations.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>
    <p class="muted small">Model built with scikit-learn ${esc(info.versions.sklearn)}; running ${esc(info.runtime_sklearn)}${info.version_ok ? "" : " (version mismatch!)"}.</p>`;
}

/* ---------- 6. Wiring ---------- */
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const { profile, problems } = readForm();
  showFormProblems(problems);
  if (problems.length) return;
  const btn = $("#submit"); btn.disabled = true; const label = btn.textContent; btn.innerHTML = '<span class="spinner"></span>Calculating';
  try {
    lastProfile = profile;
    const r = await api("/predict", profile);
    renderResult(r, profile);
    if (window.innerWidth <= 980) $("#results").scrollIntoView({ behavior: "smooth" });
  } catch (err) {
    const box = $("#form-error"); box.hidden = false; box.textContent = "Could not calculate: " + err.message;
  } finally { btn.disabled = false; btn.textContent = label; }
});

$("#reset").addEventListener("click", () => {
  form.reset(); showFormProblems([]); lastProfile = null;
  $("#result-body").hidden = true; $("#result-body").innerHTML = ""; $("#placeholder").hidden = false;
  $("#example-select").value = "";
});

const EXAMPLE_LABELS = { median_profile: "Typical study patient", high_risk_example: "Higher-risk example", low_risk_example: "Lower-risk example" };
async function init() {
  buildForm();
  try {
    INFO = await api("/model-info"); renderAbout(INFO);
    const ex = await api("/examples");
    $("#example-select").insertAdjacentHTML("beforeend", Object.keys(ex).map((k) => `<option value="${k}">${esc(EXAMPLE_LABELS[k] || k)}</option>`).join(""));
    $("#example-select").addEventListener("change", (e) => {
      if (!e.target.value) return;
      fillForm(ex[e.target.value]); form.requestSubmit();
    });
  } catch (err) { $("#about-body").textContent = "Could not load model information: " + err.message; }
}
init();
