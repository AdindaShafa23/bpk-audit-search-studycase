/* Frontend vanilla JS – tanpa build step. */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, opts) {
  const r = await fetch("/api" + path, opts);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch (_) {}
    throw new Error(msg);
  }
  return r.json();
}

function rp(n) {
  n = Number(n || 0);
  if (n >= 1e12) return "Rp " + (n / 1e12).toFixed(2).replace(".", ",") + " T";
  if (n >= 1e9) return "Rp " + (n / 1e9).toFixed(2).replace(".", ",") + " M";
  if (n >= 1e6) return "Rp " + (n / 1e6).toFixed(1).replace(".", ",") + " jt";
  return "Rp " + n.toLocaleString("id-ID");
}
const num = (n) => Number(n || 0).toLocaleString("id-ID");

/* ------------------------------------------------------------ tabs */
let activeTab = "search";
$$(".tab").forEach((b) => b.addEventListener("click", () => {
  activeTab = b.dataset.tab;
  $$(".tab").forEach((x) => x.classList.toggle("active", x === b));
  $$(".panel").forEach((p) => p.classList.toggle("active", p.id === "tab-" + activeTab));
  if (activeTab === "dashboard") loadDashboard();
  if (activeTab === "upload") loadDocs();
}));

/* ------------------------------------------------------------ lembaga */
async function loadInstitutions() {
  const list = await api("/institutions").catch(() => []);
  for (const id of ["f-inst", "d-inst"]) {
    const sel = $("#" + id), cur = sel.value;
    sel.innerHTML = `<option value="">${id === "d-inst" ? "Semua lembaga" : "Semua"}</option>` +
      list.map((i) => `<option>${esc(i)}</option>`).join("");
    sel.value = cur;
  }
  $("#inst-list").innerHTML = list.map((i) => `<option value="${esc(i)}">`).join("");
}

/* ------------------------------------------------------------ pencarian */
let page = 1;
async function runSearch(p = 1) {
  page = p;
  const params = new URLSearchParams({
    q: $("#q").value, page: p, size: 8,
    institution: $("#f-inst").value, category: $("#f-cat").value, doc_type: $("#f-type").value,
  });
  for (const [k, v] of [...params]) if (!v) params.delete(k);
  const t0 = performance.now();
  const box = $("#results");
  try {
    const res = await api("/search?" + params);
    const ms = Math.round(performance.now() - t0);
    $("#search-meta").textContent = `${num(res.total)} dokumen ditemukan · ${ms} ms`;
    if (!res.hits.length) {
      box.innerHTML = `<div class="empty">Tidak ada dokumen yang cocok. Coba kata kunci lain atau pastikan dokumen sudah selesai diproses.</div>`;
      $("#pager").innerHTML = "";
      return;
    }
    box.innerHTML = res.hits.map((h) => `
      <article class="hit">
        <h4><a href="/api/documents/${esc(h.doc_id)}/download" target="_blank" rel="noopener">${esc(h.filename)}</a></h4>
        <div class="tags">
          <span class="tag">${esc(h.institution)}</span>
          <span class="tag">${esc(h.doc_type)}</span>
          <span class="tag">${esc(h.category)}</span>
          ${h.contract_value ? `<span class="tag">${esc(rp(h.contract_value))}</span>` : ""}
          <span class="tag">${esc(h.doc_date || "")}</span>
          ${h.ocr_used ? `<span class="tag ocr">hasil OCR</span>` : ""}
        </div>
        ${(h.snippets || []).map((s) => `<div class="snip">… ${s} …</div>`).join("")}
      </article>`).join("");  // snippet sudah di-escape HTML oleh Elasticsearch (encoder html)

    const pages = Math.ceil(res.total / res.size);
    $("#pager").innerHTML = pages > 1
      ? `<button class="btn" ${p <= 1 ? "disabled" : ""} data-p="${p - 1}">‹ Sebelumnya</button>
         <span class="meta">Halaman ${p} / ${pages}</span>
         <button class="btn" ${p >= pages ? "disabled" : ""} data-p="${p + 1}">Berikutnya ›</button>` : "";
  } catch (e) {
    box.innerHTML = `<div class="empty">Gagal mencari: ${esc(e.message)}</div>`;
  }
}
$("#search-form").addEventListener("submit", (e) => { e.preventDefault(); runSearch(1); });
$("#pager").addEventListener("click", (e) => { const b = e.target.closest("button[data-p]"); if (b) runSearch(+b.dataset.p); });
["f-inst", "f-cat", "f-type"].forEach((id) => $("#" + id).addEventListener("change", () => runSearch(1)));
$$("#examples .chip").forEach((c) => c.addEventListener("click", () => { $("#q").value = c.textContent; runSearch(1); }));

/* ------------------------------------------------------------ dashboard */
const PALETTE = ["#2a6fb0", "#e0883a", "#2c9a78", "#b8508c", "#8a6fd1", "#c8a32b", "#4aa3b8", "#c4543d"];
const colorOf = (() => { const m = {}; return (name) => (m[name] ??= PALETTE[Object.keys(m).length % PALETTE.length]); })();
let chTrend, chCat;

function fillCategoryFilter(cats) {
  const sel = $("#f-cat"), cur = sel.value;
  const opts = cats.map((c) => c.name);
  if ([...sel.options].slice(1).map((o) => o.value).join("|") !== opts.join("|")) {
    sel.innerHTML = `<option value="">Semua</option>` + opts.map((c) => `<option>${esc(c)}</option>`).join("");
    sel.value = cur;
  }
}

async function loadDashboard() {
  const p = new URLSearchParams({ interval: $("#d-int").value });
  if ($("#d-inst").value) p.set("institution", $("#d-inst").value);
  let d;
  try { d = await api("/dashboard?" + p); } catch (e) { $("#d-updated").textContent = "gagal memuat"; return; }

  $("#k-in").textContent = num(d.incoming_docs);
  $("#k-in-sub").textContent = d.institution || "semua lembaga";
  $("#k-idx").textContent = num(d.indexed_docs);
  $("#k-ocr").textContent = `${num(d.ocr_docs)} lewat OCR`;
  $("#k-val").textContent = rp(d.total_contract_value);
  $("#k-cnt").textContent = `${num(d.contract_count)} dokumen kontrak`;
  const pl = d.pipeline || {};
  const inflight = (pl.queued || 0) + (pl.processing || 0) + (pl.waiting_ocr || 0);
  $("#k-q").textContent = num(inflight);
  $("#k-fail").textContent = pl.failed ? `${pl.failed} gagal` : "tidak ada yang gagal";
  $("#pipeline").innerHTML = [["queued", "Antre"], ["processing", "Diproses"], ["waiting_ocr", "Menunggu OCR"], ["done", "Selesai"], ["failed", "Gagal"]]
    .map(([k, l]) => `<span class="pill">${l}<b>${num(pl[k])}</b></span>`).join("");

  fillCategoryFilter(d.by_category || []);

  // --- tren (stacked bar) ---
  const t = d.trend || { labels: [], series: {} };
  const datasets = Object.entries(t.series).map(([name, data]) => ({ label: name, data, backgroundColor: colorOf(name), stack: "s" }));
  if (!chTrend) {
    chTrend = new Chart($("#c-trend"), {
      type: "bar", data: { labels: t.labels, datasets },
      options: { responsive: true, maintainAspectRatio: false, animation: false,
        scales: { x: { stacked: true, grid: { display: false } }, y: { stacked: true, beginAtZero: true, ticks: { precision: 0 }, title: { display: true, text: "Jumlah dokumen" } } },
        plugins: { legend: { position: "bottom" } } },
    });
  } else { chTrend.data.labels = t.labels; chTrend.data.datasets = datasets; chTrend.update(); }

  // --- komposisi ---
  const cats = d.by_category || [];
  const cdata = { labels: cats.map((c) => c.name), datasets: [{ data: cats.map((c) => c.count), backgroundColor: cats.map((c) => colorOf(c.name)), borderWidth: 0 }] };
  if (!chCat) {
    chCat = new Chart($("#c-cat"), { type: "doughnut", data: cdata, options: { responsive: true, maintainAspectRatio: false, animation: false, cutout: "58%", plugins: { legend: { position: "bottom" } } } });
  } else { chCat.data = cdata; chCat.update(); }

  // --- per lembaga ---
  $("#t-inst tbody").innerHTML = (d.by_institution || []).map((r) =>
    `<tr><td>${esc(r.name)}</td><td class="num">${num(r.incoming)}</td><td class="num">${num(r.indexed)}</td><td class="num">${esc(rp(r.contract_value))}</td></tr>`
  ).join("") || `<tr><td colspan="4" class="empty">Belum ada data. Unggah dokumen atau jalankan seeder.</td></tr>`;

  $("#d-updated").textContent = "diperbarui " + new Date().toLocaleTimeString("id-ID");
}
$("#d-inst").addEventListener("change", loadDashboard);
$("#d-int").addEventListener("change", loadDashboard);

/* ------------------------------------------------------------ unggah */
$("#u-date").valueAsDate = new Date();
const drop = $("#drop"), fileInput = $("#u-files");
let chosen = [];
function showFiles() { $("#u-list").innerHTML = chosen.map((f) => `<li>📄 ${esc(f.name)} <small>(${(f.size / 1024).toFixed(0)} KB)</small></li>`).join(""); }
$("#pick").addEventListener("click", (e) => { e.preventDefault(); fileInput.click(); });
fileInput.addEventListener("change", () => { chosen = [...fileInput.files]; showFiles(); });
["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", (e) => { chosen = [...e.dataTransfer.files]; showFiles(); });

$("#upload-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!chosen.length) { $("#u-msg").textContent = "Pilih minimal satu file."; return; }
  const fd = new FormData();
  chosen.forEach((f) => fd.append("files", f));
  fd.append("institution", $("#u-inst").value);
  if ($("#u-date").value) fd.append("doc_date", $("#u-date").value);
  $("#u-btn").disabled = true; $("#u-msg").textContent = "Mengunggah…";
  const t0 = performance.now();
  try {
    const res = await api("/documents", { method: "POST", body: fd });
    const ms = Math.round(performance.now() - t0);
    $("#u-msg").textContent = `✔ ${res.accepted.length} dokumen diterima dalam ${ms} ms. OCR/indeks berjalan di latar belakang.`;
    chosen = []; fileInput.value = ""; showFiles();
    loadDocs(); loadInstitutions();
  } catch (err) { $("#u-msg").textContent = "Gagal: " + err.message; }
  finally { $("#u-btn").disabled = false; }
});

const STATUS = { queued: "Antre", processing: "Diproses", waiting_ocr: "Menunggu OCR", done: "Selesai", failed: "Gagal" };
async function loadDocs() {
  const rows = await api("/documents?limit=15").catch(() => []);
  $("#t-docs tbody").innerHTML = rows.map((r) => `
    <tr><td>${esc(r.filename)}</td><td>${esc(r.institution)}</td>
    <td><span class="st ${esc(r.status)}" title="${esc(r.error || "")}">${STATUS[r.status] || esc(r.status)}</span></td>
    <td>${esc(r.doc_type || "–")}</td><td>${esc(r.category || "–")}</td>
    <td class="num">${r.contract_value ? esc(rp(r.contract_value)) : "–"}</td>
    <td>${r.status === "done" ? (r.ocr_used ? "ya" : "tidak") : "–"}</td></tr>`).join("")
    || `<tr><td colspan="7" class="empty">Belum ada dokumen.</td></tr>`;
}

/* ------------------------------------------------------------ polling */
setInterval(() => {
  if (document.hidden) return;
  if (activeTab === "dashboard") loadDashboard();
  if (activeTab === "upload") loadDocs();
}, 5000);
setInterval(() => { if (activeTab === "upload" && !document.hidden) loadDocs(); }, 2500);

loadInstitutions().then(() => loadDashboard().catch(() => {}));  // isi filter kategori
runSearch(1);
