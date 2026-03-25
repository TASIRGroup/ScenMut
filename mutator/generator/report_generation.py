from typing import List, Optional, Union, Tuple
import os
import shutil
import html
from pathlib import Path

from transition_graph import ScriptPath
from mutator.generator.script_generation import generate_script_of_mutated_path

STATIC_CSS = """
* { box-sizing: border-box; }
body { font-family: system-ui, -apple-system, sans-serif; margin: 0; padding: 1rem 2rem; background: #f5f5f5; color: #222; }
h1, h2, h3 { margin-top: 1.5em; margin-bottom: 0.5em; color: #111; }
a { color: #0566c8; text-decoration: none; }
a:hover { text-decoration: underline; }
section { background: #fff; border-radius: 8px; padding: 1rem 1.5rem; margin-bottom: 1rem; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #ddd; padding: 0.5rem 0.75rem; text-align: left; }
th { background: #eee; font-weight: 600; }
pre, .code { background: #f8f8f8; border: 1px solid #e0e0e0; border-radius: 4px; padding: 0.75rem; overflow-x: auto; font-size: 0.9em; white-space: pre-wrap; word-break: break-all; }
.node-type-normal { color: #0a6b0a; }
.node-type-internal { color: #6b4c0a; }
.badge { display: inline-block; padding: 0.2em 0.5em; border-radius: 4px; font-size: 0.85em; }
.badge-success { background: #d4edda; color: #155724; }
.badge-fail { background: #f8d7da; color: #721c24; }
.details-toggle { cursor: pointer; user-select: none; }
summary { cursor: pointer; }
"""


def _esc(s: str) -> str:
    return html.escape(str(s)) if s is not None else ""


def _path_summary(path: ScriptPath) -> str:
    arr = path.to_array()
    parts = []
    for pn in arr:
        d = pn.to_dict() if hasattr(pn, "to_dict") else {}
        node_type = d.get("node_type", "normal")
        state_id = d.get("state_id", getattr(pn.state, "id", "?") if pn else "?")
        event_id = d.get("event_id")
        if event_id is None and getattr(pn, "event", None) is not None:
            event_id = getattr(pn.event, "event_id", "-")
        parts.append(f"{state_id}({node_type},e{event_id})")
    return " → ".join(parts)


def _path_to_html(path: ScriptPath, title: str = "Path") -> str:
    d = path.to_dict()
    path_type = d.get("path_type", "")
    mutation_desc = d.get("mutation_description") or ""
    nodes = d.get("path_nodes", [])
    name = d.get("path_name", "")
    script = generate_script_of_mutated_path(path)

    out = [f'<section><h3>{_esc(title)}</h3>']
    if path_type:
        out.append(f'<p><strong>Path type:</strong> {_esc(path_type)}</p>')
    if name:
        out.append(f'<p><strong>Path name:</strong> {_esc(name)}</p>')
    if mutation_desc:
        if isinstance(mutation_desc, dict):
            import json
            mutation_desc = json.dumps(mutation_desc, ensure_ascii=False, indent=2)
        out.append(f'<p><strong>Mutation description:</strong></p><pre>{_esc(str(mutation_desc))}</pre>')
    out.append("<p><strong>Nodes:</strong></p>")
    for i, node in enumerate(nodes):
        ntype = node.get("node_type", "normal")
        state_id = node.get("state_id", "?")
        event_id = node.get("event_id")
        raw_state = node.get("raw_state_dict") or {}
        raw_event = node.get("raw_event_dict") or {}
        screenshot = raw_state.get("screenshot_path") or ""
        oracles = node.get("oracles") or []
        out.append(f'<div style="margin-bottom:1rem;">')
        out.append(f'<strong>Node {i}</strong> <span class="node-type-{ntype}">[{ntype}]</span> state_id={_esc(state_id)} event_id={_esc(str(event_id))}')
        if screenshot:
            out.append(f'<br>Screenshot: <img src="{_esc(screenshot)}" alt="Screenshot" style="max-width: 300px; height: auto;">')
            out.append(f'<br>Screenshot Path: <code>{_esc(screenshot)}</code>')
        if raw_event:
            out.append(f'<br>Event: <code>{_esc(str(raw_event))}</code>')
        if oracles:
            out.append(f'<br>Oracles({len(oracles)}): <code>{_esc(str(oracles))}</code>')
        out.append("</div>")
    out.append(f'<p><strong>Generated Script:</strong></p><pre>{_esc(str(script))}</pre>')
    out.append("</section>")
    return "\n".join(out)


def generate_report(
    mutated_paths: List[ScriptPath],
    html_output_path: str,
    application_name: Optional[str] = None,
    original_paths: Optional[List[Union[ScriptPath, Tuple[str, ScriptPath]]]] = None,
) -> None:
    """
    Generate a static HTML report.

    - index.html: Overview (application name, original path summaries, list of mutated paths, and links to each page)
    - mutation_details_[i].html: Details for each mutated path (type, description, path nodes, events, oracles, etc.)
    - llm_call_details.html: Summary of all LLM calls and per-call input/output, cost, duration, etc.

    Args:
        mutated_paths: List of mutated script paths.
        html_output_path: Output directory; files like `index.html` will be generated here.
        application_name: Optional application name (e.g., appPackage).
        original_paths: Optional list of original paths; elements can be `ScriptPath` or `(script_name, ScriptPath)`.
    """
    if os.path.exists(html_output_path):
        shutil.rmtree(html_output_path)
    os.makedirs(html_output_path, exist_ok=True)
    base = Path(html_output_path)

    # Normalize original_paths to [(name, path), ...].
    orig_list: List[Tuple[str, ScriptPath]] = []
    if original_paths:
        for p in original_paths:
            if isinstance(p, (list, tuple)) and len(p) == 2:
                orig_list.append((str(p[0]), p[1]))
            else:
                orig_list.append(("original", p))

    app_name = application_name or "N/A"

    # ---------- index.html ----------
    index_lines = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Mutation Report</title>",
        f"<style>{STATIC_CSS}</style></head><body>",
        "<h1>Mutation Report</h1>",
        "<section>",
        f"<h2>Summary</h2>",
        f"<p><strong>Application:</strong> {_esc(app_name)}</p>",
        f"<p><strong>Mutated paths count:</strong> {len(mutated_paths)}</p>",
    ]
    if orig_list:
        index_lines.append("<h3>Original script path(s)</h3>")
        for i, (name, path) in enumerate(orig_list):
            index_lines.append(f"<p><a href='original_details_{i}.html'><strong>{_esc(name)}</strong></a>: <code>{_esc(_path_summary(path))}</code></p>")
    index_lines.append("<h3>Mutated paths</h3><ul>")
    for i, path in enumerate(mutated_paths):
        index_lines.append(
            f'<li><a href="mutation_details_{i}.html">Mutation {i}</a>: <code>{_esc(_path_summary(path))}</code></li>'
        )
    index_lines.append("</ul>")
    index_lines.append("</section></body></html>")

    (base / "index.html").write_text("\n".join(index_lines), encoding="utf-8")

    # ---------- original_details_[i].html ----------
    for i, (name, path) in enumerate(orig_list):
        detail_lines = [
            "<!DOCTYPE html><html><head><meta charset='utf-8'>",
            f"<title>Original {i} Details</title>",
            f"<style>{STATIC_CSS}</style></head><body>",
            f"<p><a href='index.html'>← Back to index</a></p>",
            f"<h1>Original path #{i}</h1>",
            _path_to_html(path, "Original path"),
        ]
        detail_lines.append("</body></html>")
        (base / f"original_details_{i}.html").write_text("\n".join(detail_lines), encoding="utf-8")

    # ---------- mutation_details_[i].html ----------
    for i, path in enumerate(mutated_paths):
        detail_lines = [
            "<!DOCTYPE html><html><head><meta charset='utf-8'>",
            f"<title>Mutation {i} Details</title>",
            f"<style>{STATIC_CSS}</style></head><body>",
            f"<p><a href='index.html'>← Back to index</a></p>",
            f"<h1>Mutation details #{i}</h1>",
            _path_to_html(path, "Mutated path"),
        ]
        detail_lines.append("</body></html>")
        (base / f"mutation_details_{i}.html").write_text("\n".join(detail_lines), encoding="utf-8")