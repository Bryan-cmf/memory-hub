#!/usr/bin/env python3
"""MemoryHub Yearbook — 年度記憶書 HTML/PDF (5.5)"""

import json, os; from pathlib import Path; from datetime import datetime
MR = Path(os.path.expanduser("~/.openclaw/workspace/memory"))
def gen(y=None,o=None):
    y=y or datetime.now().year; d=MR/str(y)
    if not d.exists(): return {"error":f"No memories for {y}"}
    ms=[f.read_text("utf-8")[:500] for f in sorted(d.glob("_monthly-*.md"))]
    h=f"""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><title>MemoryHub Yearbook {y}</title>
<style>body{{font-family:sans-serif;max-width:800px;margin:40px auto;line-height:1.8;}}
h1{{text-align:center}}h2{{border-bottom:2px solid #667eea;margin-top:2em}}
.stats{{display:flex;gap:20px;justify-content:center;margin:2em 0}}
.card{{background:#f5f5f5;padding:1em 2em;border-radius:8px;text-align:center}}
.card .n{{font-size:2em;font-weight:bold;color:#667eea}}
@media print{{body{{font-size:11pt}}}}</style></head><body>
<h1>MemoryHub Yearbook {y}</h1><p style="text-align:center;color:#666">Generated {datetime.now().strftime('%Y-%m-%d')}</p>
<div class="stats"><div class="card"><div class="n">{len(ms)}</div>月報</div></div>
<h2>Monthly Reviews</h2>{"".join(f'<pre>{s}</pre>' for s in ms)}
<hr><p style="text-align:center;color:#999">MemoryHub v1.1 · Print to PDF: Ctrl+P</p></body></html>"""
    p=Path(o) if o else Path(f"/tmp/memoryhub_yearbook_{y}.html");p.write_text(h,"utf-8")
    return {"status":"generated","year":y,"output":str(p),"size":len(h)}
if __name__=="__main__":r=gen();print(json.dumps(r,ensure_ascii=False,indent=2))
