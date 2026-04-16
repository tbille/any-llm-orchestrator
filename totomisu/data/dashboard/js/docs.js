/**
 * Document viewer logic: sidebar, content loading, keyboard nav, auto-refresh.
 * Depends on markdown.js being loaded first (for renderMarkdown and escapeHtml).
 */

const GROUP_ORDER = ["requirements", "specs", "reviews", "ci_and_pr", "other"];
const REFRESH_INTERVAL = 15000;  // 15 seconds for sidebar auto-refresh
const slug = location.pathname.split("/docs/")[1] || "";

let allDocs = [];    // flat list of {name, label, size} in sidebar order
let activeIdx = -1;  // currently selected index in allDocs
let docCache = {};   // filename -> fetched text
let prevDocNames = null; // for change detection on auto-refresh

// ── Helpers ─────────────────────────────────────────────

function fmtSize(b) {
  if (b >= 1048576) return (b / 1048576).toFixed(1) + "M";
  if (b >= 1024) return (b / 1024).toFixed(1) + "K";
  return b + "B";
}

// ── Sidebar rendering ───────────────────────────────────

function renderSidebar(data, preserveSelection) {
  const sb = document.getElementById("sidebar");
  const groups = data.groups || {};
  const labels = data.group_labels || {};
  const prevActive = preserveSelection && activeIdx >= 0 ? allDocs[activeIdx] : null;

  allDocs = [];
  let html = "";

  for (const gKey of GROUP_ORDER) {
    const docs = groups[gKey] || [];
    if (!docs.length) continue;
    html += '<div class="sb-group"><div class="sb-group-title">' + escapeHtml(labels[gKey] || gKey) + "</div>";
    for (const doc of docs) {
      const idx = allDocs.length;
      const isNew = prevDocNames && !prevDocNames.has(doc.name);
      allDocs.push({ name: doc.name, label: doc.label, size: doc.size_bytes });
      const ext = doc.name.split(".").pop();
      const iconCls = ext === "json" ? "sb-icon-json" : "sb-icon-md";
      const iconTxt = ext === "json" ? "{ }" : "MD";
      const newBadge = isNew ? '<span class="sb-new-badge">NEW</span>' : "";
      html += '<div class="sb-item" data-idx="' + idx + '">' +
        '<span class="sb-icon ' + iconCls + '">' + iconTxt + "</span>" +
        '<span class="sb-label">' + escapeHtml(doc.label) + newBadge + "</span>" +
        '<span class="sb-size">' + fmtSize(doc.size_bytes) + "</span></div>";
    }
    html += "</div>";
  }
  sb.innerHTML = html;

  // Restore selection if a previously active doc still exists.
  if (prevActive) {
    const newIdx = allDocs.findIndex(d => d.name === prevActive.name);
    if (newIdx >= 0) {
      activeIdx = newIdx;
      const el = sb.querySelector('.sb-item[data-idx="' + newIdx + '"]');
      if (el) el.classList.add("active");
    }
  }

  // Click handlers via delegation.
  sb.onclick = function(e) {
    const item = e.target.closest(".sb-item");
    if (item) selectDoc(parseInt(item.dataset.idx, 10));
  };

  // Track doc names for next refresh.
  prevDocNames = new Set(allDocs.map(d => d.name));
}

// ── Document selection ──────────────────────────────────

function selectDoc(idx) {
  if (idx < 0 || idx >= allDocs.length) return;
  activeIdx = idx;

  // Update active class.
  document.querySelectorAll(".sb-item").forEach(el => {
    el.classList.toggle("active", parseInt(el.dataset.idx, 10) === idx);
  });
  // Scroll active item into view.
  const activeEl = document.querySelector('.sb-item[data-idx="' + idx + '"]');
  if (activeEl) activeEl.scrollIntoView({ block: "nearest" });

  loadDocContent(allDocs[idx]);
}

async function loadDocContent(doc) {
  const contentEl = document.getElementById("content");
  contentEl.innerHTML = '<div class="content-header"><h2>' + escapeHtml(doc.label) +
    '</h2><div class="filename">' + escapeHtml(doc.name) + "</div></div>" +
    '<div id="doc-body" class="loading">Loading...</div>';

  // Use cache if available.
  let text = docCache[doc.name];
  if (!text) {
    try {
      const res = await fetch("/api/docs/" + encodeURIComponent(slug) + "/" + encodeURIComponent(doc.name));
      if (!res.ok) throw new Error("Failed to load");
      text = await res.text();
      docCache[doc.name] = text;
    } catch (e) {
      document.getElementById("doc-body").textContent = "Error loading document: " + e.message;
      return;
    }
  }

  const body = document.getElementById("doc-body");
  if (!body) return;
  body.className = "";

  if (doc.name.endsWith(".json")) {
    body.className = "doc-json";
    try { body.textContent = JSON.stringify(JSON.parse(text), null, 2); }
    catch (e) { body.textContent = text; }
  } else {
    body.className = "doc-md";
    body.innerHTML = renderMarkdown(text);
  }
  contentEl.scrollTop = 0;
}

// ── Keyboard navigation ─────────────────────────────────

document.addEventListener("keydown", function(e) {
  if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
  if (e.key === "ArrowDown" || e.key === "j") {
    e.preventDefault();
    selectDoc(activeIdx < 0 ? 0 : Math.min(activeIdx + 1, allDocs.length - 1));
  } else if (e.key === "ArrowUp" || e.key === "k") {
    e.preventDefault();
    selectDoc(activeIdx <= 0 ? 0 : activeIdx - 1);
  } else if (e.key === "Enter") {
    e.preventDefault();
    if (activeIdx >= 0) {
      // Re-fetch to bypass cache (useful if file was updated).
      delete docCache[allDocs[activeIdx].name];
      loadDocContent(allDocs[activeIdx]);
    }
  }
});

// ── Auto-refresh sidebar ────────────────────────────────

async function refreshSidebar() {
  if (!slug) return;
  try {
    const res = await fetch("/api/docs/" + encodeURIComponent(slug));
    if (!res.ok) return;
    const data = await res.json();
    renderSidebar(data, true);
  } catch (e) {
    // Silently ignore -- sidebar refresh is best-effort.
  }
}

// ── Init ────────────────────────────────────────────────

async function load() {
  if (!slug) {
    document.getElementById("content").innerHTML =
      '<div class="empty">No feature specified. <a href="/">Back to dashboard</a></div>';
    return;
  }
  try {
    const res = await fetch("/api/docs/" + encodeURIComponent(slug));
    if (!res.ok) throw new Error("Feature not found");
    const data = await res.json();

    document.getElementById("page-title").textContent = data.slug;
    let bHtml = '<span class="badge type-' + data.triage_type + '">' + escapeHtml(data.triage_type) + "</span>";
    if (data.current_phase) bHtml += ' <span class="badge badge-muted">' + escapeHtml(data.current_phase) + "</span>";
    if (data.repos && data.repos.length) bHtml += ' <span class="badge badge-muted">' + data.repos.length + " repos</span>";
    document.getElementById("page-badges").innerHTML = bHtml;

    renderSidebar(data, false);

    if (allDocs.length) selectDoc(0);
  } catch (e) {
    document.getElementById("content").innerHTML =
      '<div class="empty">' + escapeHtml(e.message) + '. <a href="/">Back to dashboard</a></div>';
  }
}

load();
setInterval(refreshSidebar, REFRESH_INTERVAL);
