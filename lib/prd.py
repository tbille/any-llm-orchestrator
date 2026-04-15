"""Phase 2-3.6: Product Manager, PRD debate, design classification, and designer."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from lib.config import ProjectPaths
from lib.intake import _extract_reply


# ── Phase 2: Product Manager (interactive TUI) ───────────────────────


def run_pm(slug: str, paths: ProjectPaths) -> Path:
    """Launch the PM agent in TUI mode to create a PRD.

    The user interacts with the PM until they are satisfied, then exits.
    The PM writes the PRD to ``specs/<slug>/prd.md``.
    """
    spec_dir = paths.spec_dir(slug)
    prd_file = paths.spec_file(slug, "prd.md")

    print("\n── Phase 2: Product Manager ─────────────────────────")
    print(f"  Working dir: {spec_dir}")
    print(f"  Input:       input.md")
    print(f"  Output:      prd.md")
    print("  The PM agent will open in a TUI session.")
    print("  Collaborate on the PRD, then exit when satisfied.")
    print("────────────────────────────────────────────────────\n")

    prompt = (
        f"You are acting as the Product Manager for this feature.\n\n"
        f"Read the input in input.md (in the current directory) and create a PRD.\n"
        f"Write the PRD to: prd.md (in the current directory)\n\n"
        f"ALL files you need to read or write are in the current directory.\n"
        f"Do NOT access files outside this directory.\n\n"
        f"If anything is unclear, ask me questions before writing.\n"
        f"When you write the PRD, use the template structure from your system prompt."
    )

    subprocess.run(
        [
            "opencode",
            "--agent",
            "product-manager",
            "--prompt",
            prompt,
            str(spec_dir),
        ],
        cwd=str(spec_dir),
    )

    if not prd_file.exists():
        print(f"[WARN] PRD not found at {prd_file}.", file=sys.stderr)
        print("       The PM session may not have written it yet.")
        answer = input("       Continue anyway? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            sys.exit(1)

    return prd_file


# ── Phase 3: PRD Debate (interactive TUI) ─────────────────────────────


def run_debate(slug: str, paths: ProjectPaths) -> Path:
    """Launch the reviewer agent to critique and refine the PRD.

    The user can participate in the debate. The PRD is refined in place.
    """
    spec_dir = paths.spec_dir(slug)
    prd_file = paths.spec_file(slug, "prd.md")

    print("\n── Phase 3: PRD Debate ──────────────────────────────")
    print(f"  Working dir: {spec_dir}")
    print(f"  PRD:         prd.md")
    print("  The reviewer will critique the PRD.")
    print("  You can participate in the discussion.")
    print("  Exit when the PRD is satisfactory.")
    print("────────────────────────────────────────────────────\n")

    prompt = (
        f"Review the PRD at prd.md (in the current directory).\n\n"
        f"ALL files you need to read or write are in the current directory.\n"
        f"Do NOT access files outside this directory.\n\n"
        f"Critique it thoroughly: check for missing edge cases, cross-repo "
        f"consistency, backwards compatibility, scope creep, and missing "
        f"acceptance criteria.\n\n"
        f"After the discussion, update prd.md in place with improvements."
    )

    subprocess.run(
        [
            "opencode",
            "--agent",
            "reviewer",
            "--prompt",
            prompt,
            str(spec_dir),
        ],
        cwd=str(spec_dir),
    )

    return prd_file


# ── Phase 3.5: Design need classification (headless) ─────────────────

_DESIGN_CLASSIFIER_PROMPT = """\
Read the PRD below and determine if this feature needs product design work.

Design IS needed when the feature involves:
- User-facing behavior changes (UI, CLI output, error messages)
- SDK API shape changes (new methods, changed signatures, new types)
- Developer experience changes (new workflows, changed configuration)
- Documentation-visible changes

Design is NOT needed when:
- The change is purely internal (refactoring, performance, infrastructure)
- The fix is a straightforward bug with no API/UX impact
- The change only affects tests or CI

Respond with ONLY a JSON object:
{{"needs_design": true/false, "reasoning": "one sentence"}}

## PRD content

{prd_content}
"""


def classify_design_need(slug: str, paths: ProjectPaths) -> bool:
    """Headless call to determine whether the designer phase is needed."""
    prd_file = paths.spec_file(slug, "prd.md")
    if not prd_file.exists():
        return False

    prd_content = prd_file.read_text(encoding="utf-8")
    prompt = _DESIGN_CLASSIFIER_PROMPT.format(prd_content=prd_content)

    result = subprocess.run(
        [
            "opencode",
            "run",
            "--dir",
            str(paths.root),
            "--dangerously-skip-permissions",
            "--format",
            "json",
            prompt,
        ],
        capture_output=True,
        text=True,
    )

    # Use the same JSON event stream parser as the triage classifier.
    reply = _extract_reply(result.stdout)

    # Extract the JSON object from the reply text.
    try:
        brace_start = reply.find("{")
        brace_end = reply.rfind("}")
        if brace_start != -1 and brace_end != -1:
            data = json.loads(reply[brace_start : brace_end + 1])
            needs = data.get("needs_design", False)
            reasoning = data.get("reasoning", "")
            print(f"  Design needed: {needs} -- {reasoning}")
            return bool(needs)
    except (json.JSONDecodeError, KeyError):
        pass

    # Default: assume design is needed (safer).
    print("  Could not parse design classifier output; assuming design needed.")
    return True


# ── Phase 3.6: Product Designer (interactive TUI, conditional) ────────


def run_designer(slug: str, paths: ProjectPaths) -> Path:
    """Launch the designer agent to create design proposals.

    Only called when ``classify_design_need`` returns True.
    """
    spec_dir = paths.spec_dir(slug)
    design_file = paths.spec_file(slug, "design.md")

    print("\n── Phase 3.6: Product Designer ──────────────────────")
    print(f"  Working dir: {spec_dir}")
    print(f"  PRD:         prd.md")
    print(f"  Output:      design.md")
    print("  The designer will create UX/DX proposals.")
    print("  Collaborate with the designer, then exit.")
    print("────────────────────────────────────────────────────\n")

    prompt = (
        f"Read the PRD at prd.md (in the current directory).\n\n"
        f"ALL files you need to read or write are in the current directory.\n"
        f"Do NOT access files outside this directory.\n\n"
        f"Create design proposals covering:\n"
        f"- User/developer flows and interactions\n"
        f"- SDK API ergonomics (method names, signatures, return types)\n"
        f"- Error handling UX\n"
        f"- CLI or configuration changes (if applicable)\n"
        f"- Documentation patterns\n\n"
        f"Write the design document to: design.md (in the current directory)"
    )

    subprocess.run(
        [
            "opencode",
            "--agent",
            "designer",
            "--prompt",
            prompt,
            str(spec_dir),
        ],
        cwd=str(spec_dir),
    )

    return design_file


# ── Convenience: check if phases already completed ────────────────────


def prd_exists(slug: str, paths: ProjectPaths) -> bool:
    return paths.spec_file(slug, "prd.md").exists()


def design_exists(slug: str, paths: ProjectPaths) -> bool:
    return paths.spec_file(slug, "design.md").exists()
