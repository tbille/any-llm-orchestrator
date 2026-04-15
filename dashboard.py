"""Web dashboard for monitoring any-llm-world orchestrator progress.

Usage:
    uv run dashboard.py              # start on port 8080
    uv run dashboard.py --port 9090  # custom port
"""

from __future__ import annotations

import argparse
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

from lib.config import get_project_paths
from lib.costs import get_feature_costs
from lib.status import (
    ALL_PHASES,
    PHASE_LABELS,
    PHASES_BY_TYPE,
    get_live_tmux_sessions,
    get_log_tails,
    get_pr_info_for_feature,
    load_all_statuses,
)


# ── API ───────────────────────────────────────────────────────────────


def _build_api_response() -> dict:
    """Collect all data the dashboard needs in a single JSON payload."""
    paths = get_project_paths()
    features = load_all_statuses(paths)
    tmux = get_live_tmux_sessions()

    # Enrich each feature with live data.
    for feat in features:
        slug = feat.get("slug", "")
        feat["tmux_sessions"] = tmux.get(slug, [])

        # Log tails for active agents.
        feat["log_tails"] = get_log_tails(slug, feat.get("repos", []), paths)

        # Only query PR/CI info if we're past the PR phase.
        current = feat.get("current_phase", "")
        pr_phase = feat.get("phases", {}).get("pr", {})
        if pr_phase.get("status") in ("done", "running") or current == "ci":
            feat["pr_info"] = get_pr_info_for_feature(
                slug, feat.get("repos", []), paths
            )
        else:
            feat["pr_info"] = {}

        # Cost data from the opencode DB.
        feat["costs"] = get_feature_costs(slug, paths) or {}

    return {
        "features": features,
        "phase_labels": PHASE_LABELS,
        "phases_by_type": {k: list(v) for k, v in PHASES_BY_TYPE.items()},
        "all_phases": list(ALL_PHASES),
    }


# ── HTML ──────────────────────────────────────────────────────────────

DASHBOARD_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>any-llm-world dashboard</title>
<style>
  :root {
    --bg: #0d1117; --surface: #161b22; --border: #30363d;
    --text: #e6edf3; --muted: #8b949e; --accent: #58a6ff;
    --green: #3fb950; --red: #f85149; --yellow: #d29922;
    --blue: #58a6ff; --purple: #bc8cff;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
         background: var(--bg); color: var(--text); padding: 24px; }
  h1 { font-size: 20px; font-weight: 600; margin-bottom: 8px; }
  .header { display: flex; justify-content: space-between; align-items: center;
            margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid var(--border); }
  .header .meta { color: var(--muted); font-size: 13px; }
  .empty { color: var(--muted); text-align: center; padding: 64px 0; font-size: 15px; }

  /* Feature card */
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
          padding: 20px; margin-bottom: 16px; }
  .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
  .card-title { font-size: 16px; font-weight: 600; }
  .card-type { font-size: 12px; padding: 2px 8px; border-radius: 12px; font-weight: 500; }
  .type-feature { background: rgba(88,166,255,0.15); color: var(--blue); }
  .type-simple-bug { background: rgba(63,185,80,0.15); color: var(--green); }
  .type-complex-bug { background: rgba(210,153,34,0.15); color: var(--yellow); }

  /* Phase bar */
  .phases { display: flex; gap: 4px; margin-bottom: 16px; }
  .phase { flex: 1; text-align: center; padding: 8px 4px; border-radius: 6px;
           font-size: 11px; font-weight: 500; border: 1px solid transparent; }
  .phase-done { background: rgba(63,185,80,0.15); color: var(--green); border-color: rgba(63,185,80,0.3); }
  .phase-running { background: rgba(88,166,255,0.15); color: var(--blue); border-color: rgba(88,166,255,0.3);
                   animation: pulse 2s ease-in-out infinite; }
  .phase-pending { background: rgba(139,148,158,0.08); color: var(--muted); }
  .phase-failed { background: rgba(248,81,73,0.15); color: var(--red); border-color: rgba(248,81,73,0.3); }
  .phase-skipped { background: transparent; color: var(--muted); opacity: 0.4; text-decoration: line-through; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.6; } }

  /* Repo table */
  .repos { width: 100%; border-collapse: collapse; font-size: 13px; }
  .repos th { text-align: left; color: var(--muted); font-weight: 500; padding: 6px 12px;
              border-bottom: 1px solid var(--border); }
  .repos td { padding: 6px 12px; border-bottom: 1px solid var(--border); }
  .repos tr:last-child td { border-bottom: none; }
  .status-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }
  .dot-done, .dot-pass { background: var(--green); }
  .dot-running, .dot-pending { background: var(--blue); }
  .dot-fail { background: var(--red); }
  .dot-none, .dot-skipped { background: var(--muted); opacity: 0.4; }
  a { color: var(--accent); text-decoration: none; }
  a:hover { text-decoration: underline; }

  /* Log tail */
  .log-tail { margin-top: 4px; padding: 6px 10px; background: var(--bg); border-radius: 4px;
              font-family: 'SF Mono', Menlo, Monaco, 'Courier New', monospace; font-size: 11px;
              color: var(--muted); line-height: 1.5; white-space: pre-wrap; word-break: break-all;
              max-height: 80px; overflow: hidden; }
  .logs-hidden .log-tail { display: none; }
  .log-size { font-size: 11px; color: var(--muted); font-family: monospace; }
  .log-active { color: var(--green); }
  .log-idle { color: var(--yellow); }
  .log-phase { font-size: 10px; padding: 1px 5px; border-radius: 3px;
               background: rgba(139,148,158,0.12); color: var(--muted); margin-left: 6px; }
  .log-toggle { font-size: 12px; padding: 3px 10px; border-radius: 4px; cursor: pointer;
                background: rgba(139,148,158,0.1); color: var(--muted); border: 1px solid var(--border);
                margin-left: 8px; }

  /* Cost display */
  .cost-bar { display: flex; gap: 16px; flex-wrap: wrap; align-items: center;
              margin-top: 12px; padding: 10px 14px; background: var(--bg);
              border-radius: 6px; font-size: 13px; }
  .cost-total { font-weight: 600; color: var(--text); font-size: 15px; }
  .cost-detail { color: var(--muted); font-size: 12px; }
  .cost-repo { font-size: 11px; color: var(--muted); font-family: monospace; }
  .log-toggle:hover { background: rgba(139,148,158,0.2); color: var(--text); }

  .notif-banner { font-size: 12px; padding: 6px 12px; border-radius: 6px; cursor: pointer;
                  background: rgba(210,153,34,0.15); color: var(--yellow); border: 1px solid rgba(210,153,34,0.3); }
  .notif-banner:hover { background: rgba(210,153,34,0.25); }
  .notif-ok { background: rgba(63,185,80,0.1); color: var(--green); border-color: rgba(63,185,80,0.2); cursor: default; }

  /* Tmux badges */
  .tmux-badges { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 12px; }
  .tmux-badge { font-size: 11px; padding: 2px 8px; border-radius: 4px;
                background: rgba(188,140,255,0.15); color: var(--purple);
                font-family: monospace; }
</style>
</head>
<body>

<div class="header">
  <h1>any-llm-world</h1>
  <div class="meta">
    <span id="notif-status"></span>
    <button class="log-toggle" id="log-toggle-btn" onclick="toggleLogs()">Hide logs</button>
    Auto-refresh: 5s &middot; <span id="updated"></span>
  </div>
</div>
<div id="app"><div class="empty">Loading...</div></div>

<script>
const ICONS = { done: "\u2713", running: "\u21bb", pending: "\u00b7", failed: "\u2717", skipped: "\u2014" };

// ── Browser notifications ────────────────────────────────

const INTERACTIVE_PHASES = new Set(["pm", "debate", "designer", "architect"]);
const PHASE_NOTIFY_LABELS = {
  pm: "Product Manager is waiting for your input",
  debate: "PRD Reviewer is waiting for discussion",
  designer: "Designer is waiting for collaboration",
  architect: "Architect is waiting for guidance",
};
const notified = new Set(); // tracks "slug:phase" combos already notified

if ("Notification" in window && Notification.permission === "default") {
  Notification.requestPermission();
}

function checkNotifications(features) {
  if (!("Notification" in window) || Notification.permission !== "granted") return;

  for (const f of features) {
    const phase = f.current_phase;
    if (!phase || !INTERACTIVE_PHASES.has(phase)) continue;
    const ps = (f.phases && f.phases[phase]) || {};
    if (ps.status !== "running") continue;

    const key = f.slug + ":" + phase;
    if (notified.has(key)) continue;
    notified.add(key);

    const label = PHASE_NOTIFY_LABELS[phase] || (phase + " is running");
    new Notification("any-llm-world", {
      body: f.slug + ": " + label,
      icon: "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🔔</text></svg>",
      tag: key, // prevents duplicate OS notifications for the same event
    });
  }
}

function updateNotifStatus() {
  const el = document.getElementById("notif-status");
  if (!("Notification" in window)) {
    el.innerHTML = "";
    return;
  }
  if (Notification.permission === "granted") {
    el.innerHTML = '<span class="notif-banner notif-ok">Notifications on</span> ';
  } else if (Notification.permission === "default") {
    el.innerHTML = '<span class="notif-banner" onclick="Notification.requestPermission().then(updateNotifStatus)">Enable notifications</span> ';
  } else {
    el.innerHTML = '<span class="notif-banner" style="opacity:0.5;cursor:default">Notifications blocked</span> ';
  }
}
updateNotifStatus();

// ── Log toggle ───────────────────────────────────────
let logsVisible = localStorage.getItem("logsVisible") !== "false";

function toggleLogs() {
  logsVisible = !logsVisible;
  localStorage.setItem("logsVisible", logsVisible);
  document.getElementById("app").classList.toggle("logs-hidden", !logsVisible);
  updateLogToggle();
}

function updateLogToggle() {
  const btn = document.getElementById("log-toggle-btn");
  if (btn) btn.textContent = logsVisible ? "Hide logs" : "Show logs";
}

function render(data) {
  const { features, phase_labels, phases_by_type, all_phases } = data;
  const app = document.getElementById("app");

  if (!features.length) {
    app.innerHTML = '<div class="empty">No features in progress.<br>Start one with: uv run orchestrate.py --issue &lt;url&gt;</div>';
    return;
  }

  app.innerHTML = features.map(f => {
    const applicable = phases_by_type[f.triage_type] || all_phases;
    const typeClass = "type-" + f.triage_type;

    // Phase bar
    const phaseBar = all_phases.map(p => {
      if (!applicable.includes(p)) return "";
      const ps = (f.phases && f.phases[p]) || {};
      const st = ps.status || "pending";
      const label = phase_labels[p] || p;
      return '<div class="phase phase-' + st + '">' + ICONS[st] + " " + label + "</div>";
    }).join("");

    // Repo table with log tails
    let repoRows = "";
    if (f.repos && f.repos.length) {
      const currentPhase = f.current_phase || "";
      const phaseRepos = (f.phases && f.phases[currentPhase] && f.phases[currentPhase].repos) || {};
      const prInfo = f.pr_info || {};
      const logTails = f.log_tails || {};

      function fmtSize(b) {
        if (b >= 1048576) return (b / 1048576).toFixed(1) + " MB";
        if (b >= 1024) return (b / 1024).toFixed(1) + " KB";
        return b + " B";
      }
      function escHtml(s) { return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }

      const repoProgress = f.repo_progress || {};

      repoRows = f.repos.map(r => {
        const pr = prInfo[r] || {};
        const prLink = pr.url ? '<a href="' + pr.url + '" target="_blank">PR</a>' : "";
        const ciSt = pr.ci || "none";
        const log = logTails[r] || {};
        const logLines = (log.last_lines || []).map(escHtml).join("\\n");
        const logSize = log.size_bytes ? '<span class="log-size">' + fmtSize(log.size_bytes) + '</span>' : '';
        const logPhase = log.phase ? '<span class="log-phase">' + log.phase + '</span>' : '';
        const logHtml = logLines
          ? '<div class="log-tail">' + logLines + '</div>'
          : '';

        // Per-repo build step from repo_progress (set by repo_runner.py).
        const progress = repoProgress[r] || {};
        const step = progress.step || phaseRepos[r] || "";

        // Derive display status from step + log activity.
        let displayStep = step;
        let dotClass = "dot-running";
        if (step === "done") {
          dotClass = "dot-done";
        } else if (step && log.size_bytes && !log.active) {
          dotClass = "dot-pending";
          displayStep = step + ' <span class="log-idle">(idle)</span>';
        }

        return "<tr>" +
          "<td><strong>" + r + "</strong> " + logSize + logPhase + "</td>" +
          "<td>" + (step ? '<span class="status-dot ' + dotClass + '"></span>' + displayStep : "") + "</td>" +
          "<td>" + prLink + "</td>" +
          "<td>" + (pr.url ? '<span class="status-dot dot-' + ciSt + '"></span>' + ciSt : "") + "</td>" +
          "</tr>" +
          (logHtml ? "<tr><td colspan='4'>" + logHtml + "</td></tr>" : "");
      }).join("");
    }

    // Tmux badges
    const tmuxHtml = (f.tmux_sessions || []).map(s =>
      '<span class="tmux-badge">' + s + "</span>"
    ).join("");

    // Cost display
    const costs = f.costs || {};
    let costHtml = "";
    if (costs.total_cost > 0) {
      const repoCosts = Object.entries(costs.by_repo || {})
        .sort((a, b) => b[1].cost - a[1].cost)
        .map(([name, d]) => '<span class="cost-repo">' + name + ": $" + d.cost.toFixed(2) + "</span>")
        .join(" &middot; ");
      const outputTok = costs.total_output_tokens || 0;
      const tokStr = outputTok >= 1000000 ? (outputTok / 1000000).toFixed(1) + "M" :
                     outputTok >= 1000 ? (outputTok / 1000).toFixed(1) + "K" : outputTok;
      costHtml = '<div class="cost-bar">' +
        '<span class="cost-total">$' + costs.total_cost.toFixed(2) + '</span>' +
        '<span class="cost-detail">' + tokStr + ' output tokens &middot; ' +
          (costs.sessions || 0) + ' sessions &middot; ' +
          (costs.messages || 0) + ' messages</span>' +
        (repoCosts ? '<div style="width:100%">' + repoCosts + '</div>' : '') +
        '</div>';
    }

    return '<div class="card">' +
      '<div class="card-header">' +
        '<span class="card-title">' + f.slug + '</span>' +
        '<span class="card-type ' + typeClass + '">' + f.triage_type + '</span>' +
      '</div>' +
      '<div class="phases">' + phaseBar + '</div>' +
      (repoRows ? '<table class="repos"><tr><th>Repo</th><th>Status</th><th>PR</th><th>CI</th></tr>' + repoRows + '</table>' : '') +
      (tmuxHtml ? '<div class="tmux-badges">tmux: ' + tmuxHtml + '</div>' : '') +
      costHtml +
      '</div>';
  }).join("");
}

async function refresh() {
  try {
    const res = await fetch("/api/status");
    const data = await res.json();
    render(data);
    // Apply log visibility state after render replaces the DOM.
    document.getElementById("app").classList.toggle("logs-hidden", !logsVisible);
    updateLogToggle();
    checkNotifications(data.features || []);
    document.getElementById("updated").textContent = new Date().toLocaleTimeString();
  } catch (e) {
    console.error("Refresh failed:", e);
  }
}

refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>
"""


# ── HTTP server ───────────────────────────────────────────────────────


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/status":
            self._json_response(_build_api_response())
        elif self.path in ("/", "/index.html"):
            self._html_response(DASHBOARD_HTML)
        else:
            self.send_error(404)

    def _json_response(self, data: dict) -> None:
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html_response(self, html: str) -> None:
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        # Suppress default stderr logging for clean terminal output.
        pass


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="dashboard",
        description="Web dashboard for the any-llm-world orchestrator.",
    )
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on")
    args = parser.parse_args()

    server = HTTPServer(("0.0.0.0", args.port), DashboardHandler)
    print(f"Dashboard running at http://localhost:{args.port}")
    print("Press Ctrl-C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
