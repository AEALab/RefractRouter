from __future__ import annotations

from pathlib import Path


def render_standalone_html(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 2rem auto; max-width: 960px; line-height: 1.65; }}
    h1 {{ border-bottom: 2px solid #2563eb; padding-bottom: .4rem; }}
    section {{ margin-top: 2rem; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #cbd5e1; padding: .5rem; text-align: left; }}
  </style>
</head>
<body>
{body}
</body>
</html>
"""


def save_html_report(path: str | Path, html: str) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    return output
