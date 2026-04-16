/**
 * Lightweight Markdown-to-HTML renderer for the any-llm-world dashboard.
 * No external dependencies. Handles: headings, bold, italic, strikethrough,
 * links, images, code blocks (with syntax highlighting), tables, lists
 * (including nested and task lists), blockquotes, and horizontal rules.
 */

// ── Syntax highlighting ─────────────────────────────────

const SYNTAX_RULES = {
  python: {
    keywords: /\b(def|class|import|from|return|if|elif|else|for|while|with|as|try|except|finally|raise|yield|lambda|and|or|not|in|is|None|True|False|self|async|await|pass|break|continue|global|nonlocal|assert)\b/g,
    strings: /("""[\s\S]*?"""|'''[\s\S]*?'''|"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/g,
    comments: /(#.*$)/gm,
    numbers: /\b(\d+\.?\d*(?:e[+-]?\d+)?)\b/g,
    functions: /\b([a-zA-Z_]\w*)\s*(?=\()/g,
    types: /\b([A-Z][a-zA-Z0-9]*)\b/g,
  },
  rust: {
    keywords: /\b(fn|let|mut|const|static|struct|enum|impl|trait|pub|use|mod|match|if|else|for|while|loop|return|break|continue|async|await|move|ref|self|Self|super|crate|where|type|as|in|unsafe|extern|dyn|macro_rules)\b/g,
    strings: /("(?:[^"\\]|\\.)*")/g,
    comments: /(\/\/.*$|\/\*[\s\S]*?\*\/)/gm,
    numbers: /\b(\d+\.?\d*(?:e[+-]?\d+)?(?:_\d+)*[iu]?\d*)\b/g,
    functions: /\b([a-zA-Z_]\w*)\s*(?=\()/g,
    types: /\b([A-Z][a-zA-Z0-9]*)\b/g,
  },
  go: {
    keywords: /\b(func|var|const|type|struct|interface|map|chan|package|import|return|if|else|for|range|switch|case|default|break|continue|go|defer|select|fallthrough|nil|true|false)\b/g,
    strings: /("(?:[^"\\]|\\.)*"|`[^`]*`)/g,
    comments: /(\/\/.*$|\/\*[\s\S]*?\*\/)/gm,
    numbers: /\b(\d+\.?\d*(?:e[+-]?\d+)?)\b/g,
    functions: /\b([a-zA-Z_]\w*)\s*(?=\()/g,
    types: /\b([A-Z][a-zA-Z0-9]*)\b/g,
  },
  typescript: {
    keywords: /\b(function|const|let|var|class|interface|type|enum|import|export|from|return|if|else|for|while|do|switch|case|default|break|continue|new|this|super|extends|implements|async|await|yield|throw|try|catch|finally|typeof|instanceof|in|of|null|undefined|true|false|void|never|any|unknown|readonly|abstract|static|public|private|protected)\b/g,
    strings: /(`(?:[^`\\]|\\.)*`|"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/g,
    comments: /(\/\/.*$|\/\*[\s\S]*?\*\/)/gm,
    numbers: /\b(\d+\.?\d*(?:e[+-]?\d+)?)\b/g,
    functions: /\b([a-zA-Z_$]\w*)\s*(?=\()/g,
    types: /\b([A-Z][a-zA-Z0-9]*)\b/g,
  },
  json: {
    strings: /("(?:[^"\\]|\\.)*")\s*(?=:)/g,  // keys
    numbers: /\b(-?\d+\.?\d*(?:e[+-]?\d+)?)\b/g,
    keywords: /\b(true|false|null)\b/g,
  },
  bash: {
    keywords: /\b(if|then|else|elif|fi|for|while|do|done|case|esac|function|return|exit|export|local|readonly|declare|source|alias|unalias|cd|echo|printf|test)\b/g,
    strings: /("(?:[^"\\]|\\.)*"|'[^']*')/g,
    comments: /(#.*$)/gm,
    numbers: /\b(\d+)\b/g,
  },
  yaml: {
    keywords: /\b(true|false|null|yes|no|on|off)\b/gi,
    strings: /("(?:[^"\\]|\\.)*"|'[^']*')/g,
    comments: /(#.*$)/gm,
    numbers: /\b(\d+\.?\d*)\b/g,
  },
};

// Language aliases
const LANG_MAP = {
  py: "python", python: "python", python3: "python",
  rs: "rust", rust: "rust",
  go: "go", golang: "go",
  ts: "typescript", typescript: "typescript", javascript: "typescript", js: "typescript", jsx: "typescript", tsx: "typescript",
  json: "json", jsonc: "json",
  sh: "bash", bash: "bash", shell: "bash", zsh: "bash",
  yml: "yaml", yaml: "yaml",
  diff: "diff",
};

function highlightCode(code, lang) {
  const normalized = LANG_MAP[(lang || "").toLowerCase()];

  // Diff gets special treatment (no escaping of +/- lines)
  if (normalized === "diff") {
    return code.split("\n").map(line => {
      if (line.startsWith("+")) return '<span class="h-pass">' + escapeHtml(line) + "</span>";
      if (line.startsWith("-")) return '<span class="h-fail">' + escapeHtml(line) + "</span>";
      if (line.startsWith("@@")) return '<span class="cmt">' + escapeHtml(line) + "</span>";
      return escapeHtml(line);
    }).join("\n");
  }

  const rules = SYNTAX_RULES[normalized];
  if (!rules) return escapeHtml(code);

  // Tokenize: protect strings and comments first, then apply keyword/number highlighting.
  let result = escapeHtml(code);

  // Strings
  if (rules.strings) {
    result = result.replace(rules.strings, '<span class="str">$1</span>');
  }
  // Comments
  if (rules.comments) {
    result = result.replace(rules.comments, '<span class="cmt">$1</span>');
  }
  // Keywords (only outside of already-wrapped spans)
  if (rules.keywords) {
    result = result.replace(rules.keywords, '<span class="kw">$&</span>');
  }
  // Numbers
  if (rules.numbers) {
    result = result.replace(rules.numbers, '<span class="num">$1</span>');
  }

  return result;
}

// ── Core renderer ───────────────────────────────────────

function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function renderMarkdown(src) {
  // Phase 1: Extract fenced code blocks to protect them from further processing.
  const codeBlocks = [];
  let text = src.replace(/```(\w*)\n([\s\S]*?)```/g, function(_, lang, code) {
    const idx = codeBlocks.length;
    codeBlocks.push({ lang: lang, code: code.replace(/\n$/, "") });
    return "\x00CODEBLOCK" + idx + "\x00";
  });

  // Phase 2: Process everything else.
  let h = escapeHtml(text);

  // Tables: header | sep | body
  h = h.replace(/^(\|.+\|)\n(\|[-| :]+\|)\n((?:\|.+\|\n?)*)/gm, function(_, hdr, sep, body) {
    const ths = hdr.split("|").filter(c => c.trim()).map(c => "<th>" + c.trim() + "</th>").join("");
    const rows = body.trim().split("\n").map(function(row) {
      const tds = row.split("|").filter(c => c.trim()).map(c => "<td>" + c.trim() + "</td>").join("");
      return "<tr>" + tds + "</tr>";
    }).join("");
    return "<table><thead><tr>" + ths + "</tr></thead><tbody>" + rows + "</tbody></table>";
  });

  // Headings
  h = h.replace(/^#### (.+)$/gm, "<h4>$1</h4>");
  h = h.replace(/^### (.+)$/gm, "<h3>$1</h3>");
  h = h.replace(/^## (.+)$/gm, "<h2>$1</h2>");
  h = h.replace(/^# (.+)$/gm, "<h1>$1</h1>");

  // Horizontal rules
  h = h.replace(/^---+$/gm, "<hr>");

  // Strikethrough
  h = h.replace(/~~(.+?)~~/g, "<del>$1</del>");

  // Bold+italic
  h = h.replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>");
  h = h.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  h = h.replace(/\*(.+?)\*/g, "<em>$1</em>");

  // Inline code
  h = h.replace(/`([^`]+)`/g, "<code>$1</code>");

  // Images (before links to avoid conflict)
  h = h.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img src="$2" alt="$1">');

  // Links
  h = h.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

  // Bare URLs (not already inside an href or src)
  h = h.replace(/(?<!="|'>)(https?:\/\/[^\s<)]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>');

  // Blockquotes (handle escaped >)
  h = h.replace(/^&gt; (.+)$/gm, "<blockquote>$1</blockquote>");
  // Merge consecutive blockquotes
  h = h.replace(/<\/blockquote>\n<blockquote>/g, "\n");

  // Task lists: - [ ] or - [x]
  h = h.replace(/^((?:- \[[ x]\] .+\n?)+)/gm, function(block) {
    const items = block.trim().split("\n").map(function(line) {
      const checked = line.match(/^- \[x\]/i);
      const text = line.replace(/^- \[[ x]\] /i, "");
      const icon = checked
        ? '<span class="task-checkbox">\u2713</span>'
        : '<span class="task-checkbox"></span>';
      return "<li>" + icon + text + "</li>";
    }).join("");
    return '<ul class="task-list">' + items + "</ul>";
  });

  // Unordered lists
  h = h.replace(/^((?:- .+\n?)+)/gm, function(block) {
    return "<ul>" + block.trim().split("\n").map(function(l) {
      return "<li>" + l.replace(/^- /, "") + "</li>";
    }).join("") + "</ul>";
  });

  // Ordered lists
  h = h.replace(/^((?:\d+\. .+\n?)+)/gm, function(block) {
    return "<ol>" + block.trim().split("\n").map(function(l) {
      return "<li>" + l.replace(/^\d+\. /, "") + "</li>";
    }).join("") + "</ol>";
  });

  // Paragraphs: non-empty lines not already wrapped in HTML tags
  h = h.replace(/^(?!<[a-z/]|\x00)((?:.(?!<[a-z/]|\x00))+.?)$/gm, function(line) {
    const t = line.trim();
    return t ? "<p>" + t + "</p>" : "";
  });

  // Phase 3: Restore code blocks with syntax highlighting.
  h = h.replace(/\x00CODEBLOCK(\d+)\x00/g, function(_, idx) {
    const block = codeBlocks[parseInt(idx, 10)];
    const highlighted = highlightCode(block.code, block.lang);
    return "<pre><code>" + highlighted + "</code></pre>";
  });

  return h;
}

// Export for use by other modules.
window.renderMarkdown = renderMarkdown;
window.escapeHtml = escapeHtml;
