# Plan: Per-Repository Log Chevron Toggle

## Problem

The dashboard has a single global "Hide logs" / "Show logs" button that toggles all log tails at once. Users want per-repository control to fold/unfold logs individually.

## Strategy

Replace the global log toggle with a clickable chevron (`▸`/`▾`) on each repository row. Clicking the chevron expands or collapses that specific repo's log tail. All logs start collapsed. State survives poll refreshes but not page reloads.

---

## File: `dashboard/index.html`

### Change 1: Remove global log toggle button

Remove the `<button class="log-toggle" id="log-toggle-btn" onclick="toggleLogs()">Hide logs</button>` from the header `.meta` div (line 18). Keep the rest of the meta line intact.

---

## File: `dashboard/js/dashboard.js`

### Change 1: Remove global log state and functions

- Remove `let logsVisible = localStorage.getItem("logsVisible") !== "false";` (line 23)
- Remove `toggleLogs()` function (lines 110-115)
- Remove `updateLogToggle()` function (lines 117-120)

### Change 2: Add per-repo expanded state and toggle function

Add a `Set` called `expandedLogs` to track which repo logs are expanded, keyed by `"slug-repo"`. Add a `toggleRepoLog(slug, repo)` function that toggles the key in/out of the set and updates the DOM:
- Toggle the log tail row's `display` between `none` and `""`.
- Toggle the chevron text between `▸` and `▾`.

### Change 3: Update `buildRepoRows()`

- Before each repo name, add a chevron span (`.log-chevron`) if there are log lines. The chevron is `▾` if expanded, `▸` if collapsed.
- The chevron calls `toggleRepoLog(slug, repo)` on click with `event.stopPropagation()`.
- The log tail `<tr>` uses `style="display:none"` by default, or `style=""` if the key is in `expandedLogs`.

### Change 4: Preserve expanded log state in patchSection()

In the `patchSection()` function, when patching the `"repos"` section (which already preserves history toggles), also preserve which log tail rows are visible by checking `expandedLogs` and restoring visibility after innerHTML replacement.

### Change 5: Remove global toggle references from refresh()

- Remove `document.getElementById("app").classList.toggle("logs-hidden", !logsVisible);` from `refresh()`.
- Remove `updateLogToggle();` call from `refresh()`.

---

## File: `dashboard/css/dashboard.css`

### Change 1: Remove global log toggle styles

- Remove `.logs-hidden .log-tail { display: none; }` (line 79)
- Remove `.log-toggle` block (lines 84-89)
- Remove `.log-toggle:hover` block (line 89)

### Change 2: Add chevron styles

Add `.log-chevron` styles:
- Inline cursor pointer
- Color: `var(--muted)`, hover: `var(--accent)`
- `user-select: none`
- Slight margin-right for spacing from repo name
- Transition on color for smooth hover effect

---

## Behavior Summary

- Each repo row shows a `▸` chevron before the repo name (only if logs exist)
- Clicking it expands to `▾` and reveals the log tail below
- Clicking the log tail itself still opens the full SSE log modal
- State is preserved across 5-second auto-refresh polls via the `expandedLogs` Set and DOM patching
- All logs start collapsed on page load
- The global "Hide logs" button is removed entirely
