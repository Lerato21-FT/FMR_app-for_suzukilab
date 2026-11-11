// Draws the page and handles interaction. Every derived value (fields,
// resonance estimates, limits, measured data) comes from the API.
"use strict";

const form = document.getElementById("settings");
const els = {
  mode: document.getElementById("mode"),
  instruments: document.getElementById("instruments"),
  identify: document.getElementById("identify"),
  previewSummary: document.getElementById("preview-summary"),
  previewRows: document.querySelector("#preview-table tbody"),
  previewErrors: document.getElementById("preview-errors"),
  sineDrive: document.getElementById("sine-drive"),
  dataDir: document.getElementById("data-dir"),
  start: document.getElementById("start"),
  skip: document.getElementById("skip"),
  stop: document.getElementById("stop"),
  runStatus: document.getElementById("run-status"),
  runErrors: document.getElementById("run-errors"),
  sweepSelect: document.getElementById("sweep-select"),
};

let run = null;          // latest RunStatus (without points)
let points = [];         // all points received for the current run
let nextIndex = 0;
let pollTimer = null;
let followLatest = true;

// ---------- form <-> JSON --------------------------------------------------

function fillForm(settings) {
  const values = flatten(settings);
  for (const input of form.elements) {
    if (!input.name || !(input.name in values)) continue;
    const value = values[input.name];
    if (input.type === "checkbox") input.checked = Boolean(value);
    else if (Array.isArray(value)) input.value = value.join(", ");
    else input.value = value;
  }
}

function flatten(obj, prefix = "") {
  const out = {};
  for (const [key, value] of Object.entries(obj)) {
    const name = prefix ? `${prefix}.${key}` : key;
    if (value && typeof value === "object" && !Array.isArray(value)) {
      Object.assign(out, flatten(value, name));
    } else {
      out[name] = value;
    }
  }
  return out;
}

function readForm() {
  const settings = {};
  for (const input of form.elements) {
    if (!input.name) continue;
    let value;
    if (input.type === "checkbox") value = input.checked;
    else if (input.name === "frequencies_ghz") {
      value = input.value.split(/[\s,;]+/).filter(Boolean).map(Number);
    } else if (input.type === "number") value = input.value === "" ? null : Number(input.value);
    else value = input.value;
    const path = input.name.split(".");
    let node = settings;
    for (const key of path.slice(0, -1)) node = node[key] ??= {};
    node[path.at(-1)] = value;
  }
  return settings;
}

// ---------- API helpers ----------------------------------------------------

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const error = new Error(`HTTP ${response.status}`);
    error.detail = body?.detail;
    throw error;
  }
  return body;
}

function describeDetail(detail) {
  if (!detail) return ["Request failed."];
  if (typeof detail === "string") return [detail];
  return detail.map((d) =>
    typeof d === "string" ? d : `${(d.loc || []).slice(1).join(".")}: ${d.msg}`
  );
}

function showList(list, items) {
  list.replaceChildren(...items.map((text) => {
    const li = document.createElement("li");
    li.textContent = text;
    return li;
  }));
}

// ---------- preview --------------------------------------------------------

let previewTimer = null;
function schedulePreview() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(updatePreview, 300);
}

async function updatePreview() {
  try {
    const p = await api("/api/preview", { method: "POST", body: JSON.stringify(readForm()) });
    const drive = `${p.sine_amplitude_v.toFixed(3)} V rms = ${p.modulation_rms_oe.toFixed(3)} Oe rms`;
    els.sineDrive.textContent = drive;
    const summary = [
      ["Field step", `${p.field_step_oe.toFixed(2)} Oe (after 1 mV rounding)`],
      ["Modulation", drive],
      ["Estimated time", `${(p.estimated_run_seconds / 60).toFixed(1)} min`],
    ];
    els.previewSummary.replaceChildren(...summary.flatMap(([k, v]) => {
      const dt = document.createElement("dt");
      dt.textContent = k;
      const dd = document.createElement("dd");
      dd.textContent = v;
      return [dt, dd];
    }));
    els.previewRows.replaceChildren(...p.sweeps.map((s) => {
      const tr = document.createElement("tr");
      const cells = [
        String(s.frequency_ghz),
        s.resonance_field_oe.toFixed(0),
        `${s.begin_field_oe.toFixed(0)} → ${s.end_field_oe.toFixed(0)}`,
        String(s.points),
        s.file_name,
      ];
      cells.forEach((text, i) => {
        const td = document.createElement("td");
        td.textContent = text;
        if (i === cells.length - 1) td.className = "file";
        tr.append(td);
      });
      return tr;
    }));
    markCurrentRow();
    showList(els.previewErrors, p.limit_errors);
  } catch (err) {
    els.previewSummary.replaceChildren();
    els.previewRows.replaceChildren();
    els.sineDrive.textContent = "…";
    showList(els.previewErrors, describeDetail(err.detail));
  }
}

// Highlight the preview row of the sweep being measured (same order as the run).
function markCurrentRow() {
  const current = run && run.state === "running" ? run.current_sweep_index : null;
  [...els.previewRows.children].forEach((tr, i) => tr.classList.toggle("current", i === current));
}

// ---------- tabs (instrument setup, as in the LabVIEW VI) -----------------

function setupTabs() {
  const tabs = [...document.querySelectorAll('[role="tab"]')];
  const select = (tab) => {
    for (const t of tabs) {
      const selected = t === tab;
      t.setAttribute("aria-selected", String(selected));
      t.tabIndex = selected ? 0 : -1;
      document.getElementById(t.getAttribute("aria-controls")).hidden = !selected;
    }
    tab.focus();
  };
  tabs.forEach((tab, i) => {
    tab.addEventListener("click", () => select(tab));
    tab.addEventListener("keydown", (event) => {
      const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
      if (step) select(tabs[(i + step + tabs.length) % tabs.length]);
      else if (event.key === "Home") select(tabs[0]);
      else if (event.key === "End") select(tabs.at(-1));
      else return;
      event.preventDefault();
    });
  });
}

// ---------- runs -----------------------------------------------------------

async function startRun() {
  els.start.disabled = true;
  showList(els.runErrors, []);
  try {
    const status = await api("/api/runs", {
      method: "POST",
      body: JSON.stringify(readForm()),
    });
    points = [];
    nextIndex = 0;
    followLatest = true;
    applyStatus(status);
    poll();
  } catch (err) {
    showList(els.runErrors, describeDetail(err.detail));
    els.start.disabled = false;
  }
}

async function control(action) {
  if (!run) return;
  try {
    await api(`/api/runs/${run.run_id}/${action}`, { method: "POST" });
  } catch (err) {
    showList(els.runErrors, describeDetail(err.detail));
  }
}

async function poll() {
  clearTimeout(pollTimer);
  if (!run) return;
  try {
    const status = await api(`/api/runs/${run.run_id}?since=${nextIndex}`);
    applyStatus(status);
  } catch (err) {
    showList(els.runErrors, describeDetail(err.detail));
  }
  if (run && run.state === "running") pollTimer = setTimeout(poll, 500);
}

function applyStatus(status) {
  points.push(...status.points);
  nextIndex = status.next_index;
  run = { ...status, points: [] };
  const running = status.state === "running";
  els.start.disabled = running;
  els.skip.disabled = !running;
  els.stop.disabled = !running;

  const current = status.current_sweep_index;
  const sweep = current === null ? null : status.sweeps[current];
  els.runStatus.textContent = running && sweep
    ? `Running: sweep ${current + 1} of ${status.sweeps.length}, ${sweep.frequency_ghz} GHz, ${sweep.point_count} points`
    : `Run ${status.state}.`;
  showList(els.runErrors, [status.error, ...status.shutdown_errors].filter(Boolean));

  const previous = els.sweepSelect.value;
  els.sweepSelect.replaceChildren(...status.sweeps.map((s) => {
    const option = document.createElement("option");
    option.value = String(s.sweep_index);
    option.textContent = `${s.frequency_ghz} GHz: ${s.state}${s.saved ? ", saved" : ""}`;
    return option;
  }));
  if (followLatest && current !== null) els.sweepSelect.value = String(current);
  else if (previous) els.sweepSelect.value = previous;
  markCurrentRow();
  draw();
}

// ---------- plots ----------------------------------------------------------

function draw() {
  if (!window.Plotly) {
    els.runStatus.textContent += " (Plotly missing: run make vendor)";
    return;
  }
  const index = Number(els.sweepSelect.value);
  const sweepPoints = points.filter((p) => p.sweep_index === index);
  const x = sweepPoints.map((p) => p.field_oe);
  const style = getComputedStyle(document.documentElement);
  const color = style.getPropertyValue("--text").trim();
  const accent = style.getPropertyValue("--accent").trim();
  const layout = (title, yTitle) => ({
    title: { text: title, font: { size: 13 } },
    margin: { l: 65, r: 15, t: 30, b: 40 },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { color },
    xaxis: { title: { text: "H (Oe)" }, gridcolor: "rgba(128,128,128,0.2)" },
    yaxis: { title: { text: yTitle }, gridcolor: "rgba(128,128,128,0.2)", exponentformat: "e" },
  });
  const trace = (y) => ({ x, y, mode: "lines+markers", marker: { size: 3, color: accent }, line: { color: accent, width: 1 } });
  const config = { responsive: true, displaylogo: false };
  Plotly.react("signal-plot", [trace(sweepPoints.map((p) => p.signal_x_v))], layout("Differential FMR signal", "X (V)"), config);
  Plotly.react("phase-plot", [trace(sweepPoints.map((p) => p.phase_deg))], layout("Lock-in phase", "θ (deg)"), config);
}

// ---------- instruments ----------------------------------------------------

async function identify() {
  els.instruments.textContent = "Identifying…";
  try {
    const info = await api("/api/instruments");
    els.instruments.textContent = info.instruments
      .map((i) => `${i.role} @ ${i.address}: ${i.identity ?? i.error ?? "unknown"}`)
      .join(" · ");
  } catch (err) {
    els.instruments.textContent = describeDetail(err.detail).join(" ");
  }
}

// ---------- start-up -------------------------------------------------------

async function init() {
  const defaults = await api("/api/settings/defaults");
  els.mode.textContent = `${defaults.instrument_mode} instruments`;
  els.dataDir.textContent = defaults.data_dir;
  fillForm(defaults.settings);
  setupTabs();
  form.addEventListener("input", schedulePreview);
  form.addEventListener("submit", (event) => event.preventDefault());
  els.start.addEventListener("click", startRun);
  els.skip.addEventListener("click", () => control("skip"));
  els.stop.addEventListener("click", () => control("stop"));
  els.identify.addEventListener("click", identify);
  els.sweepSelect.addEventListener("change", () => { followLatest = false; draw(); });
  updatePreview();
  try {
    const latest = await api("/api/runs/latest");
    applyStatus(latest);
    if (latest.state === "running") poll();
  } catch {
    // No run has started yet; nothing to restore.
  }
}

init().catch((err) => showList(els.runErrors, describeDetail(err.detail)));
