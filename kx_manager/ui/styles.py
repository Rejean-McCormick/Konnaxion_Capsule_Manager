"""Shared CSS for the FastAPI Manager GUI.

This module owns visual styling only. It must not import Manager services,
Agent clients, action dispatchers, Docker helpers, or runtime code.
"""

from __future__ import annotations


THEME_PRIMARY = "#1e6864"
THEME_PRIMARY_DARK = "#15524f"
THEME_PRIMARY_SOFT = "#e6f2f1"


BASE_CSS = f"""
:root {{
  color-scheme: light;
  --bg: #f6f8fb;
  --panel: #ffffff;
  --text: #172033;
  --muted: #667085;
  --line: #d9e0ea;
  --accent: {THEME_PRIMARY};
  --accent-dark: {THEME_PRIMARY_DARK};
  --accent-soft: {THEME_PRIMARY_SOFT};
  --ok: #166534;
  --warn: #92400e;
  --bad: #991b1b;
  --info: {THEME_PRIMARY};
  --soft-ok: #dcfce7;
  --soft-warn: #fef3c7;
  --soft-bad: #fee2e2;
  --soft-info: {THEME_PRIMARY_SOFT};
}}

* {{ box-sizing: border-box; }}

body {{
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}}

a {{
  color: var(--accent);
  text-decoration: none;
}}

a:hover {{ text-decoration: underline; }}

.kx-shell {{
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}}

.kx-header {{
  background: var(--panel);
  border-bottom: 1px solid var(--line);
  padding: 16px 24px;
}}

.kx-brand {{
  display: flex;
  align-items: center;
  gap: 12px;
}}

.kx-logo {{
  width: 40px;
  height: 40px;
  object-fit: contain;
  flex: 0 0 auto;
}}

.kx-brand-copy {{
  min-width: 0;
}}

.kx-title {{
  margin: 0;
  font-size: 22px;
}}

.kx-subtitle {{
  margin: 4px 0 0;
  color: var(--muted);
}}

.kx-nav {{
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 12px 24px;
  background: var(--panel);
  border-bottom: 1px solid var(--line);
}}

.kx-nav a {{
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 6px 10px;
  background: #fff;
}}

.kx-nav a.active {{
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}}

.kx-nav a:hover {{
  border-color: var(--accent);
  text-decoration: none;
}}

.kx-main {{
  width: min(1240px, 100%);
  margin: 0 auto;
  padding: 24px;
}}

.kx-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 16px;
}}

.kx-card {{
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 16px;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
}}

.kx-card h2,
.kx-card h3 {{
  margin-top: 0;
}}

.kx-muted {{
  color: var(--muted);
}}

.kx-actions {{
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-top: 12px;
}}

.kx-button,
button.kx-button {{
  appearance: none;
  border: 1px solid var(--accent);
  border-radius: 8px;
  background: var(--accent);
  color: #fff;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 36px;
  padding: 7px 12px;
  font-weight: 600;
}}

.kx-button:hover,
button.kx-button:hover {{
  background: var(--accent-dark);
  border-color: var(--accent-dark);
  text-decoration: none;
}}

.kx-button.secondary,
button.kx-button.secondary {{
  background: #fff;
  color: var(--accent);
}}

.kx-button.secondary:hover,
button.kx-button.secondary:hover {{
  background: var(--accent-soft);
  color: var(--accent-dark);
}}

.kx-button.danger,
button.kx-button.danger {{
  background: var(--bad);
  border-color: var(--bad);
}}

.kx-button:disabled {{
  opacity: 0.5;
  cursor: not-allowed;
}}

.kx-form {{
  display: grid;
  gap: 12px;
}}

.kx-field label {{
  display: block;
  font-weight: 650;
  margin-bottom: 4px;
}}

.kx-field input,
.kx-field select,
.kx-field textarea {{
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 8px 10px;
  font: inherit;
  background: #fff;
}}

.kx-field input:focus,
.kx-field select:focus,
.kx-field textarea:focus {{
  outline: 2px solid var(--accent-soft);
  border-color: var(--accent);
}}

.kx-field textarea {{
  min-height: 96px;
  resize: vertical;
}}

.kx-help {{
  color: var(--muted);
  font-size: 12px;
  margin-top: 4px;
}}

.kx-badge {{
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 3px 8px;
  font-size: 12px;
  font-weight: 650;
  border: 1px solid var(--line);
  background: #fff;
}}

.kx-badge.ok {{
  color: var(--ok);
  background: var(--soft-ok);
  border-color: #bbf7d0;
}}

.kx-badge.warn {{
  color: var(--warn);
  background: var(--soft-warn);
  border-color: #fde68a;
}}

.kx-badge.error {{
  color: var(--bad);
  background: var(--soft-bad);
  border-color: #fecaca;
}}

.kx-badge.info {{
  color: var(--info);
  background: var(--soft-info);
  border-color: var(--accent-soft);
}}

.kx-result {{
  margin-bottom: 16px;
}}

.kx-result.ok {{ border-left: 5px solid var(--ok); }}
.kx-result.error {{ border-left: 5px solid var(--bad); }}
.kx-result.info {{ border-left: 5px solid var(--info); }}
.kx-result.warn {{ border-left: 5px solid var(--warn); }}

.kx-table {{
  width: 100%;
  border-collapse: collapse;
  overflow: hidden;
}}

.kx-table th,
.kx-table td {{
  border-bottom: 1px solid var(--line);
  padding: 8px;
  text-align: left;
  vertical-align: top;
}}

.kx-table th {{
  color: var(--muted);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: .03em;
}}

.kx-defs {{
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 6px 12px;
}}

.kx-defs dt {{
  color: var(--muted);
  font-weight: 650;
}}

.kx-defs dd {{
  margin: 0;
  min-width: 0;
  word-break: break-word;
}}

.kx-log,
pre.kx-json {{
  margin: 0;
  padding: 12px;
  overflow: auto;
  border-radius: 10px;
  background: #101828;
  color: #f9fafb;
  font: 12px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  max-height: 520px;
}}

.kx-footer {{
  color: var(--muted);
  padding: 16px 24px 24px;
  text-align: center;
}}
"""


__all__ = [
    "BASE_CSS",
    "THEME_PRIMARY",
    "THEME_PRIMARY_DARK",
    "THEME_PRIMARY_SOFT",
]