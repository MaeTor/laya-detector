// Three steps: testimony -> speakers -> results. All server text is inserted with textContent.
const $ = (id) => document.getElementById(id);
const VERDICT_LABEL = {
  supported: "Supported", contradicted: "Contradicted", not_covered: "Not covered",
  not_checkable: "Not a checkable fact", evidence_unavailable: "No evidence",
};
let segments = [];

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}
const pct = (x) => `${(x * 100).toFixed(1)}%`;
const time = (t) => (t == null ? "" : `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`);

function showStep(n) {
  for (const i of [1, 2, 3]) $(`step-${i}`).hidden = i !== n;
  document.querySelectorAll(".steps__item").forEach((li) => {
    const s = Number(li.dataset.step);
    if (s === n) li.setAttribute("aria-current", "step");
    else li.removeAttribute("aria-current");
    li.classList.toggle("is-done", s < n);
  });
  $(`step-${n}`).querySelector("h1, h2").focus?.();
}

function showError(msg) {
  $("error-text").textContent = msg;
  $("error").hidden = false;
}
$("error-dismiss").onclick = () => { $("error").hidden = true; };

function busy(btn, on, label) {
  btn.disabled = on;
  btn.setAttribute("aria-busy", String(on));
  if (label) btn.textContent = label;
  $("status").textContent = on ? label : "";
}

async function call(url, opts) {
  const r = await fetch(url, opts);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail ? (typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail)) : `HTTP ${r.status}`);
  return body;
}

// Tabs (arrow keys move between them)
const tabs = [$("tab-text"), $("tab-audio")];
function selectTab(tab) {
  for (const t of tabs) {
    const on = t === tab;
    t.setAttribute("aria-selected", String(on));
    t.tabIndex = on ? 0 : -1;
    $(t.getAttribute("aria-controls")).hidden = !on;
  }
  tab.focus();
}
tabs.forEach((t, i) => {
  t.onclick = () => selectTab(t);
  t.onkeydown = (e) => {
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") selectTab(tabs[(i + 1) % tabs.length]);
  };
});

// Step 1 -> 2
$("input-form").onsubmit = async (e) => {
  e.preventDefault();
  $("error").hidden = true;
  const audioMode = $("tab-audio").getAttribute("aria-selected") === "true";
  const fd = new FormData();
  if (audioMode) {
    if (!$("audio").files.length) return showError("Choose an audio file first.");
    fd.append("audio", $("audio").files[0]);
    fd.append("whisper_size", $("whisper-size").value);
  } else {
    if (!$("text").value.trim()) return showError("Paste a transcript first.");
    fd.append("text", $("text").value);
  }
  const btn = $("to-speakers");
  busy(btn, true, audioMode ? "Transcribing…" : "Reading…");
  try {
    segments = (await call("/api/segments", { method: "POST", body: fd })).segments;
    renderSegments();
    showStep(2);
  } catch (err) {
    showError(err.message);
  } finally {
    busy(btn, false, "Continue");
  }
};

function renderSegments() {
  const list = $("segments");
  list.replaceChildren();
  for (const s of segments) {
    const li = el("li", "segment");
    const body = el("div");
    if (s.t0 != null) body.append(el("div", "segment__time", `${time(s.t0)}–${time(s.t1)} · ${s.lang}`));
    body.append(el("div", null, s.english));
    if (s.original !== s.english) body.append(el("div", "segment__orig", s.original));
    const group = el("div", "role");
    group.setAttribute("role", "radiogroup");
    group.setAttribute("aria-label", `Speaker of segment ${s.id + 1}`);
    for (const [value, label] of [["interviewer", "Interviewer"], ["witness", "Witness"]]) {
      const id = `role-${s.id}-${value}`;
      const input = Object.assign(el("input"), { type: "radio", name: `role-${s.id}`, id, value, checked: s.role === value });
      input.onchange = () => { s.role = value; };
      const lab = el("label", null, label);
      lab.htmlFor = id;
      group.append(input, lab);
    }
    li.append(body, group);
    list.append(li);
  }
}

$("back-1").onclick = () => showStep(1);

// Step 2 -> 3
$("run").onclick = async () => {
  $("error").hidden = true;
  const btn = $("run");
  busy(btn, true, "Analyzing… first run loads the model");
  try {
    const report = await call("/api/analyze", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ segments }),
    });
    renderReport(report);
    showStep(3);
  } catch (err) {
    showError(err.message);
  } finally {
    busy(btn, false, "Analyze");
  }
};

$("restart").onclick = () => showStep(1);

function probBar(p) {
  const wrap = el("div");
  const bar = el("div", "bar");
  bar.setAttribute("role", "img");
  bar.setAttribute("aria-label", `supports ${pct(p.supports)}, contradicts ${pct(p.contradicts)}, not covered ${pct(p.not_covered)}`);
  for (const [cls, v] of [["bar__sup", p.supports], ["bar__con", p.contradicts], ["bar__nc", p.not_covered]]) {
    const seg = el("span", cls);
    seg.style.width = pct(v);
    bar.append(seg);
  }
  const legend = el("div", "legend");
  legend.setAttribute("aria-hidden", "true");
  legend.append(el("span", null, `supports ${pct(p.supports)}`), el("span", null, `contradicts ${pct(p.contradicts)}`),
    el("span", null, `not covered ${pct(p.not_covered)}`));
  wrap.append(bar, legend);
  return wrap;
}

function safeUrl(u) {
  try { return ["http:", "https:"].includes(new URL(u).protocol) ? u : null; } catch { return null; }
}

function renderReport(r) {
  const cal = $("calibration");
  cal.hidden = r.calibrated;
  cal.textContent = "UNCALIBRATED — probabilities use the model's default temperatures. Run `laya calibrate` on labelled claims to calibrate them for this task.";

  $("notes").replaceChildren(...r.notes.map((n) => el("li", null, n)));

  const claims = $("claims");
  claims.replaceChildren();
  if (!r.claims.length) claims.append(el("li", "empty", "No witness sentences to check."));
  for (const c of r.claims) {
    const li = el("li", "claim");
    const head = el("div", "claim__head");
    const txt = el("div");
    txt.append(el("p", "claim__text", c.text), el("div", "claim__meta", `Checkable fact: ${pct(c.checkable)}`));
    head.append(txt, el("span", `chip chip--${c.verdict}`, VERDICT_LABEL[c.verdict] ?? c.verdict));
    li.append(head);
    if (c.passages.length) {
      const ul = el("ul", "sources");
      c.passages.forEach((p, i) => {
        const s = el("li", "source" + (i === c.deciding_passage ? " is-deciding" : ""));
        const url = p.url && safeUrl(p.url);
        if (url) {
          const a = el("a", "source__link", p.title || url);
          Object.assign(a, { href: url, target: "_blank", rel: "noopener noreferrer" });
          s.append(a);
        } else {
          s.append(el("span", "source__tag", "Unsourced LLM text (counts half)"));
        }
        s.append(el("p", "source__text", p.text), probBar(p.p));
        ul.append(s);
      });
      li.append(ul);
    }
    claims.append(li);
  }

  const seg = Object.fromEntries(r.segments.map((s) => [s.id, s]));
  const ev = $("evasion");
  ev.replaceChildren();
  if (!r.evasion.length) ev.append(el("li", "empty", "No interviewer → witness turns to score."));
  for (const e of r.evasion) {
    const li = el("li", "turn");
    const m = el("div", "meter");
    const prog = Object.assign(el("progress"), { max: 1, value: e.evasion });
    prog.setAttribute("aria-label", `Evasion ${pct(e.evasion)}`);
    m.append(el("span", null, "evasion"), prog, el("span", null, pct(e.evasion)));
    li.append(el("p", "turn__q", `Q: ${seg[e.question_segment].english}`),
      el("p", "turn__a", `A: ${seg[e.answer_segment].english}`), m);
    ev.append(li);
  }

  $("raw").textContent = JSON.stringify(r, null, 1);
}

document.querySelectorAll("section h1, section h2").forEach((h) => h.setAttribute("tabindex", "-1"));
