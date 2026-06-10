#!/usr/bin/env python3
"""
🧠 MemoryHub → Obsidian 文章式報告引擎 v2

改進：從清單式報表 → 雜誌風格敘事文章
"""

import os, sys, json, re, argparse, ssl
from datetime import datetime, timedelta
from pathlib import Path

WORKSPACE = Path(os.path.expanduser("~/.openclaw/workspace"))
VAULT = Path(os.path.expanduser("~/Documents/ObsidianVault"))
LLM_API = "https://api.deepseek.com/v1/chat/completions"
LLM_KEY = "sk-f604ef02bef144119e62b21b0f430bd6"


def read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception: return {}

def read_file(path, default=""):
    try:
        with open(path) as f:
            return f.read()
    except Exception: return default

def get_week_range():
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday

def get_month_range():
    today = datetime.now()
    first = today.replace(day=1)
    if today.month == 12:
        last = today.replace(year=today.year+1, month=1, day=1) - timedelta(days=1)
    else:
        last = today.replace(month=today.month+1, day=1) - timedelta(days=1)
    return first, last

def get_iso_week(dt):
    return dt.strftime("%G-W%V")


def collect_rich_data(mode="weekly"):
    """收集豐富上下文，不只是任務清單"""
    start, end = get_week_range() if mode == "weekly" else get_month_range()
    
    ctx = {
        "mode": mode,
        "start": start.strftime("%Y-%m-%d"),
        "end": end.strftime("%Y-%m-%d"),
    }
    
    # 1. 完整每日日誌（不限字數）
    daily_dir = WORKSPACE / "memory/daily"
    daily_texts = []
    if daily_dir.exists():
        for f in sorted(daily_dir.glob("*.md"), reverse=True):
            try:
                file_date = datetime.strptime(f.stem, "%Y-%m-%d")
                if start <= file_date <= end:
                    content = read_file(f)
                    # 移除 consolidated 標記和空行
                    content = content.replace("<!-- consolidated -->", "")
                    daily_texts.append(f"### {f.stem}\n\n{content[:2000]}")
            except ValueError:
                pass
    
    ctx["daily_logs"] = daily_texts[:14]  # 最多 14 天
    
    # 2. MEMORY.md 完整上下文
    memory_md = read_file(WORKSPACE / "MEMORY.md")
    ctx["memory_excerpt"] = memory_md[:8000]
    
    # 3. 任務追蹤
    tracker = read_json(WORKSPACE / "memory/follow_up_tracker.json")
    all_items = []
    for cat_name, items in tracker.get("items", {}).items():
        if isinstance(items, list):
            for t in items:
                t["_category"] = cat_name
                all_items.append(t)
    ctx["all_tasks"] = all_items
    
    # 4. 郵件
    emails = read_json(WORKSPACE / "memory/pending_email_replies.json")
    ctx["emails"] = emails.get("pending", [])
    
    # 5. 專案
    proj_dir = WORKSPACE / "memory/projects"
    projects = []
    if proj_dir.exists():
        for f in proj_dir.glob("*.md"):
            projects.append({"name": f.stem})
    ctx["projects"] = projects
    
    return ctx


def write_article(ctx, style="concise", mode="weekly"):
    """讓 DeepSeek 寫一篇真正的文章"""
    
    period = "週" if mode == "weekly" else "月"
    
    # 構建豐富的 prompt
    daily_text = "\n\n".join(ctx.get("daily_logs", [])[:10])
    
    tasks_text = ""
    for t in ctx.get("all_tasks", [])[:20]:
        tasks_text += f"- [{t.get('priority','')}] {t.get('title','')} | 狀態: {t.get('status','')}\n"
    
    emails_text = ""
    for e in ctx.get("emails", [])[:5]:
        emails_text += f"- {e.get('from','')}: {e.get('subject','')}\n"
    
    projects_text = ", ".join([p['name'] for p in ctx.get("projects", [])])
    
    memory_excerpt = ctx.get("memory_excerpt", "")[:5000]
    
    if style == "concise":
        # 簡潔版：一篇 600-800 字的短文
        prompt = f"""你是君澤智庫 AI 助理 UltraClaw 的記憶寫手。請根據以下本{period}的工作數據，寫一篇{period}度回顧文章。

要求：
- 標題自擬（要有吸引力，不要「週報」這種乾癟字眼）
- 總長度 600-800 字
- 用繁體中文
- 語氣：專業但不僵硬，像寫給合作夥伴看的內部通訊
- 結構：
  1. 一段開場綜述：本{period}的整體基調和最重要的一件事
  2. 核心進展：2-3 個重點，每個有具體細節
  3. 值得關注：待辦事項中最重要的 1-2 件
  4. 一句收尾：對下{period}的期待或提醒

本{period}工作日誌：
{daily_text[:4000]}

待辦事項：
{tasks_text[:2000]}

待回郵件：
{emails_text[:500]}

活躍專案：{projects_text}

MEMORY.md 近期變更摘要：
{memory_excerpt[:3000]}

請直接輸出文章（Markdown 格式）："""

    else:
        # 詳細版：一篇 1500-2500 字的深度文章
        prompt = f"""你是君澤智庫 AI 助理 UltraClaw 的記憶寫手。請根據以下本{period}的工作數據，寫一篇{period}度深度回顧文章。

要求：
- 標題自擬（要有深度感）
- 總長度 1500-2500 字
- 用繁體中文
- 語氣：專業、有洞察、像智庫內部分析報告
- 結構：
  1. 開場：本{period}宏觀基調，一句話點題
  2. 核心進展（分 3-4 個小節，每節有小標題）：
     - 技術架構層面
     - 業務推進層面
     - 知識產出層面
  3. 關鍵決策回顧：最重要的 2-3 個決定及其影響
  4. 踩坑與反思：至少 1 個具體教訓
  5. 待辦聚焦：最緊急的 3-5 件事
  6. 下{period}展望：接下來最值得期待或最需關注的事

本{period}工作日誌：
{daily_text[:6000]}

待辦事項：
{tasks_text[:3000]}

待回郵件：
{emails_text[:500]}

活躍專案：{projects_text}

MEMORY.md 近期變更：
{memory_excerpt[:5000]}

請直接輸出文章（Markdown 格式）："""

    try:
        import urllib.request
        req = urllib.request.Request(
            LLM_API,
            data=json.dumps({
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "你是君澤智庫的內部寫手，擅長將技術工作日誌轉化為有洞察力的敘事文章。你的文章既有數據支撐，又有人文關懷。"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.6,
                "max_tokens": 3000 if style == "detailed" else 1200,
            }).encode(),
            headers={
                "Authorization": f"Bearer {LLM_KEY}",
                "Content-Type": "application/json"
            }
        )
        ctx_obj = ssl.create_default_context()
        ctx_obj.check_hostname = False
        ctx_obj.verify_mode = ssl.CERT_NONE
        resp = urllib.request.urlopen(req, timeout=45, context=ctx_obj)
        result = json.loads(resp.read())
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        return f"*（DeepSeek API 暫時無法使用：{e}）*\n\n## 本{period}摘要\n\n{daily_text[:500]}\n\n{tasks_text[:300]}"


def render_pdf(markdown_text, output_path, title="MemoryHub 報告"):
    """渲染為雜誌風格 PDF"""
    os.environ.setdefault('DYLD_LIBRARY_PATH', '/opt/homebrew/lib')
    from weasyprint import HTML
    
    # 簡單 Markdown → HTML
    html_body = []
    in_code = False
    
    for line in markdown_text.split('\n'):
        if line.startswith('```'):
            in_code = not in_code
            html_body.append('</pre>' if not in_code else '<pre>')
            continue
        if in_code:
            html_body.append(line)
            continue
        
        line = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
        line = re.sub(r'\*(.+?)\*', r'<em>\1</em>', line)
        
        if line.startswith('# ') and not html_body:
            pass  # skip title, we use our own
        elif line.startswith('# '):
            html_body.append(f'<h1>{line[2:]}</h1>')
        elif line.startswith('## '):
            html_body.append(f'<h2>{line[3:]}</h2>')
        elif line.startswith('### '):
            html_body.append(f'<h3>{line[4:]}</h3>')
        elif line.startswith('> '):
            html_body.append(f'<blockquote>{line[2:]}</blockquote>')
        elif line.startswith('---'):
            html_body.append('<hr>')
        elif line.strip() == '':
            html_body.append('')
        else:
            html_body.append(f'<p>{line}</p>')
    
    body = '\n'.join(html_body)
    
    css = """
    @page {
        size: A4;
        margin: 2.5cm 2cm 2.5cm 2cm;
        @bottom-center {
            content: "— " counter(page) " —";
            font-family: "Heiti TC", "PingFang TC", sans-serif;
            font-size: 8pt;
            color: #999;
        }
    }
    @page:first {
        @bottom-center { content: none; }
    }
    body {
        font-family: "Heiti TC", "PingFang TC", "Microsoft JhengHei", sans-serif;
        font-size: 11pt;
        line-height: 2;
        color: #222;
        background: white;
    }
    h1 {
        font-size: 22pt;
        font-weight: 800;
        color: #111;
        margin: 0 0 8pt 0;
        line-height: 1.3;
    }
    h2 {
        font-size: 14pt;
        font-weight: 700;
        color: #333;
        margin: 24pt 0 8pt 0;
        padding-bottom: 4pt;
        border-bottom: 1pt solid #ddd;
    }
    h3 {
        font-size: 12pt;
        font-weight: 600;
        color: #444;
        margin: 16pt 0 6pt 0;
    }
    p {
        margin: 0 0 8pt 0;
        text-align: justify;
    }
    blockquote {
        margin: 12pt 0;
        padding: 8pt 16pt;
        border-left: 3pt solid #5b9bd5;
        background: #f7f9fc;
        font-style: italic;
        color: #555;
    }
    hr {
        border: none;
        border-top: 1pt solid #ddd;
        margin: 20pt 0;
    }
    pre {
        background: #f5f5f5;
        padding: 8pt 12pt;
        border-radius: 3pt;
        font-size: 8pt;
        line-height: 1.5;
        overflow-x: auto;
    }
    strong { color: #1a1a1a; }
    em { color: #666; }
    """
    
    html = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head><meta charset="UTF-8"><style>{css}</style></head>
<body>
<div class="header">
    <p style="font-size:9pt;color:#999;margin:0 0 24pt 0;text-transform:uppercase;letter-spacing:2pt;">
        MemoryHub · {title} · {datetime.now().strftime('%Y年%m月%d日')}
    </p>
</div>
{body}
<div class="footer" style="margin-top:40pt;padding-top:12pt;border-top:1pt solid #eee;">
    <p style="font-size:8pt;color:#bbb;text-align:center;">
        由 MemoryHub AI 自動生成 · 數據來源: Qdrant + Daily Log + MEMORY.md<br>
        此報告儲存於 Obsidian Vault: ~/Documents/ObsidianVault
    </p>
</div>
</body>
</html>"""
    
    HTML(string=html).write_pdf(str(output_path))
    return output_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["weekly", "monthly"], required=True)
    parser.add_argument("--style", choices=["concise", "detailed"], default="concise")
    args = parser.parse_args()
    
    mode = args.mode
    style = args.style
    period_label = "週" if mode == "weekly" else "月"
    
    print(f"🧠 MemoryHub 文章引擎 v2 | {period_label}報 · {style}版")
    
    # Step 1: 收集數據
    ctx = collect_rich_data(mode)
    
    # Step 2: AI 寫文章
    print("   ✍️ DeepSeek 撰稿中...")
    article = write_article(ctx, style, mode)
    
    # Step 3: 儲存 Markdown
    now = datetime.now()
    if mode == "weekly":
        period = get_iso_week(now)
        subdir = "週報"
        fname = f"{period}{'-detail' if style=='detailed' else ''}.md"
    else:
        period = now.strftime("%Y-%m")
        subdir = "月報"
        fname = f"{period}{'-detail' if style=='detailed' else ''}.md"
    
    # 加 YAML frontmatter
    md_content = f"""---
date: {now.strftime('%Y-%m-%d')}
{('weekly' if mode=='weekly' else 'monthly')}_period: "{period}"
type: {mode}-report
style: {style}
tags: [{mode}-report, article]
---

{article}

---

*本報告由 MemoryHub AI 自動生成 · {now.strftime('%Y-%m-%d %H:%M')}*
"""
    
    md_path = VAULT / subdir / fname
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md_content)
    print(f"   ✅ Markdown: {md_path} ({len(md_content)} 字)")
    
    # Step 4: 渲染 PDF
    title = f"{'週' if mode=='weekly' else '月'}度回顧 · {style}版"
    pdf_path = Path(f"/tmp/obsidian_reports/{'週報' if mode=='weekly' else '月報'}-{style}版.pdf")
    pdf_path.parent.mkdir(exist_ok=True)
    render_pdf(article, pdf_path, title)
    print(f"   ✅ PDF: {pdf_path} ({pdf_path.stat().st_size/1024:.0f} KB)")
    
    print(f"\n🎉 完成！")


if __name__ == "__main__":
    main()
