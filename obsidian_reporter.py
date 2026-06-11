#!/usr/bin/env python3
"""
🧠 MemoryHub → Obsidian 週報/月報引擎

用途：從記憶系統提取數據，生成 Obsidian 格式的週報和月報
用法：
  python3 obsidian_reporter.py --mode weekly   --style concise
  python3 obsidian_reporter.py --mode weekly   --style detailed
  python3 obsidian_reporter.py --mode monthly  --style concise
  python3 obsidian_reporter.py --mode monthly  --style detailed
"""

import os, sys, json, re, argparse, ssl
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter, defaultdict

# === 配置 ===
WORKSPACE = Path(os.path.expanduser("~/.openclaw/workspace"))
VAULT = Path(os.path.expanduser("~/Documents/ObsidianVault"))
MEMORY_WEEKLY = WORKSPACE / "memory/weekly"  # 同步一份到 workspace
QDRANT_URL = "http://localhost:6333"
# 使用 DeepSeek 直連 API
LLM_API = "https://api.deepseek.com/v1/chat/completions"
LLM_KEY = os.getenv("LLM_API_KEY", "")

# === 數據讀取 ===

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
    """返回本週的起止日期 (ISO 格式)"""
    today = datetime.now()
    # 週一 = 0, 週日 = 6
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday

def get_month_range():
    """返回本月的起止日期"""
    today = datetime.now()
    first = today.replace(day=1)
    if today.month == 12:
        last = today.replace(year=today.year+1, month=1, day=1) - timedelta(days=1)
    else:
        last = today.replace(month=today.month+1, day=1) - timedelta(days=1)
    return first, last

def get_iso_week(dt):
    """返回 ISO 週數，如 2026-W21"""
    return dt.strftime("%G-W%V")

# === 數據採集 ===

def collect_memory_data(mode="weekly"):
    """從所有記憶來源收集數據"""
    start, end = get_week_range() if mode == "weekly" else get_month_range()
    
    data = {
        "mode": mode,
        "start": start.strftime("%Y-%m-%d"),
        "end": end.strftime("%Y-%m-%d"),
        "generated_at": datetime.now().isoformat(),
    }
    
    # 1. 任務追蹤
    tracker = read_json(WORKSPACE / "memory/follow_up_tracker.json")
    items = tracker.get("items", {})
    all_tasks = []
    for category in items.values():
        if isinstance(category, list):
            all_tasks.extend(category)
    data["tasks_total"] = len(all_tasks)
    data["tasks_pending"] = [t for t in all_tasks if t.get("status") not in ("已完成", "已取消", "完成")]
    data["tasks_done"] = [t for t in all_tasks if t.get("status") in ("已完成", "完成")][-10:]
    
    # 2. 郵件狀態
    emails = read_json(WORKSPACE / "memory/pending_email_replies.json")
    data["emails_pending"] = emails.get("pending", [])
    
    # 3. 每日日誌（掃描範圍內的）
    daily_entries = []
    daily_dir = WORKSPACE / "memory/daily"
    if daily_dir.exists():
        for f in sorted(daily_dir.glob("*.md"), reverse=True):
            fname = f.stem
            try:
                file_date = datetime.strptime(fname, "%Y-%m-%d")
                if start <= file_date <= end:
                    content = read_file(f)[:3000]
                    # 清洗第三人稱 → 第一人稱
                    content = _clean_third_person(content)
                    daily_entries.append({"date": fname, "content": content})
            except ValueError:
                pass
    data["daily_logs"] = daily_entries
    
    # 4. MEMORY.md 關鍵段落
    memory_md = read_file(WORKSPACE / "MEMORY.md")
    # 提取 Key Decisions 和 Lessons
    decisions = []
    lessons = []
    in_decisions = False
    in_lessons = False
    for line in memory_md.split("\n"):
        if "## 📌 Key Decisions" in line:
            in_decisions = True
            in_lessons = False
        elif "## 📝 Lessons Learned" in line:
            in_lessons = True
            in_decisions = False
        elif line.startswith("## ") or line.startswith("# "):
            in_decisions = False
            in_lessons = False
        elif in_decisions and line.strip().startswith(("-", "0", "1", "2", "3", "4", "5")):
            decisions.append(line.strip())
        elif in_lessons and line.strip().startswith(("-", "0", "1", "2", "3", "4", "5")):
            lessons.append(line.strip())
    data["key_decisions"] = decisions[-20:]
    data["lessons_learned"] = lessons[-15:]
    
    # 5. 專案狀態
    projects = []
    proj_dir = WORKSPACE / "memory/projects"
    if proj_dir.exists():
        for f in proj_dir.glob("*.md"):
            projects.append({"name": f.stem, "path": str(f.relative_to(WORKSPACE))})
    data["projects"] = projects
    
    # 6. 調研標的（從 MEMORY.md 提取）
    stocks = []
    for line in memory_md.split("\n"):
        if re.search(r'\d{4,5}\.HK', line):
            stocks.append(line.strip()[:100])
    data["stocks_researched"] = stocks[-20:]
    
    return data


# === 數據清洗 ===

def _clean_third_person(text):
    """將原始日誌中的第三人稱轉為第一人稱"""
    replacements = [
        ("老闆要求", "我需要"),
        ("老闆指示", "我決定"),
        ("老闆登入", "我登入"),
        ("老闆早上", "早上"),
        ("老闆說", "我想"),
        ("老闆提出", "我提出"),
        ("老闆回覆", "我回覆"),
        ("老闆確認", "我確認"),
        ("老闆查閱", "我查閱"),
        ("老闆", "我"),  # 最後才做廣義替換
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text


# === LLM 摘要生成 ===

def generate_summary(data, style="concise", mode="weekly"):
    """使用 DeepSeek 生成報告摘要"""
    
    # 先嘗試收集足夠的上下文
    context_parts = []
    
    # 每日日誌摘要
    if data.get("daily_logs"):
        context_parts.append(f"## 每日日誌（{len(data['daily_logs'])} 天）")
        for d in data["daily_logs"][:7]:
            context_parts.append(f"### {d['date']}\n{d['content'][:500]}\n")
    
    # 任務
    pending = data.get("tasks_pending", [])
    if pending:
        tasks_text = "\n".join([f"- [{t.get('priority','?')}] {t.get('title','')} ({t.get('status','')})" 
                                for t in pending[:15]])
        context_parts.append(f"## 待辦任務\n{tasks_text}")
    
    # 郵件
    emails = data.get("emails_pending", [])
    if emails:
        emails_text = "\n".join([f"- {e.get('from','')}: {e.get('subject','')}" 
                                 for e in emails[:5]])
        context_parts.append(f"## 待回覆郵件\n{emails_text}")
    
    context = "\n\n".join(context_parts)
    
    if not context.strip():
        return "（本週尚無足夠數據生成摘要）"
    
    # 數據清洗：將原始數據中的第三人稱轉為第一人稱
    context = context.replace("老闆要求", "我需要")
    context = context.replace("老闆指示", "我決定")
    context = context.replace("老闆登入", "我登入")
    context = context.replace("老闆早上", "早上")
    context = context.replace("老闆說", "我想")
    context = context.replace("老闆", "我")  # 最後才做廣義替換
    
    if style == "concise":
        prompt = f"""你正在協助用戶以第一人稱視角撰寫個人{'週' if mode=='weekly' else '月'}度回顧。

⚠️ 核心規則：
- 以「我」的第一人稱撰寫，這是用戶自己的日記/回憶錄
- 不要出現「老闆」、「團隊」、「用戶」等第三人稱詞彙（原始數據可能包含這些詞，全部轉化為第一人稱）
- 不要用「你」稱呼用戶——你就是用戶本人
- 語氣：真誠、自省、有洞察，像一個人在回顧自己的一週

要求：
1. 用繁體中文，總長度不超過 800 字
2. 包含三個段落：
   a) 這{'週' if mode=='weekly' else '月'}做了什麼（我完成了哪些事）
   b) 需要跟進的事（我還有哪些沒做完）
   c) 一個核心洞察（這{'週' if mode=='weekly' else '月'}我學到最重要的東西是什麼）
3. 條列格式，每條不超過 30 字
4. 唔好輸出標題（標題由模板生成）

數據：
{context[:4000]}

請直接輸出摘要內容（以第一人稱「我」）："""
    else:
        prompt = f"""你正在協助用戶以第一人稱視角撰寫個人{'週' if mode=='weekly' else '月'}度詳細回顧。
這份回顧的最終目的是積累 10 年的經驗與記憶，協助用戶日後撰寫個人傳記。

⚠️ 核心規則：
- 以「我」的第一人稱撰寫，這是用戶自己的回憶錄
- 不要出現「老闆」、「團隊」、「用戶」、「他」等第三人稱詞彙（原始數據可能包含這些詞，那是因為數據記錄方式不同，你必須全部轉化為第一人稱）
- 不要用「你」稱呼用戶——你就是用戶本人
- 不要寫「我處理了老闆的提醒」——應該寫「我處理了跟進事項」
- 不要寫「與老闆的互動」——應該寫「日常工作中的溝通」
- 語氣：像一個有智慧的人在寫自己的日記，真誠、深刻、有反思

要求：
1. 用繁體中文，總長度不超過 2000 字
2. 包含以下段落：
   a) 本{'週' if mode=='weekly' else '月'}脈絡 — 我這一週/月經歷了什麼，時間線
   b) 重要決定 — 我做了哪些關鍵決策，為什麼這樣選擇，背後的思考
   c) 學到的東西 — 踩了什麼坑、獲得什麼教訓、有什麼新的理解
   d) 人與關係 — 遇到了哪些值得記住的人、互動、合作
   e) 待跟進 — 哪些事還未完成，需要繼續關注
   f) 下一步 — 下{'週' if mode=='weekly' else '月'}的方向和重心
3. 格式為 Markdown 段落

數據：
{context[:6000]}

請直接輸出（以第一人稱「我」）："""

    # 嘗試調用 DeepSeek API
    try:
        import urllib.request
        req = urllib.request.Request(
            LLM_API,
            data=json.dumps({
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "你是一位專業的 AI 記憶分析師，擅長從數據中提取洞察。"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 2000 if style == "detailed" else 800,
            }).encode(),
            headers={
                "Authorization": f"Bearer {LLM_KEY}",
                "Content-Type": "application/json"
            }
        )
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        resp = urllib.request.urlopen(req, timeout=30, context=ctx)
        result = json.loads(resp.read())
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        # Fallback: 手動生成簡潔摘要
        return _manual_summary(data, style, mode)


def _manual_summary(data, style, mode):
    """無 API 時的備援摘要"""
    lines = []
    
    # 任務摘要
    pending = data.get("tasks_pending", [])
    done = data.get("tasks_done", [])
    
    if done:
        lines.append("## ✅ 近期完成")
        for t in done[-5:]:
            lines.append(f"- [x] {t.get('title', '')}")
    
    if pending:
        lines.append("\n## 🔴 待辦事項")
        for t in pending[:5]:
            priority = t.get("priority", "")
            lines.append(f"- [{priority}] {t.get('title', '')}")
    
    # 郵件
    emails = data.get("emails_pending", [])
    if emails:
        lines.append("\n## 📧 待回覆郵件")
        for e in emails[:3]:
            lines.append(f"- {e.get('from','').split('<')[0].strip()}: {e.get('subject','')[:30]}")
    
    # 每日摘要
    logs = data.get("daily_logs", [])
    if logs:
        lines.append(f"\n## 📅 本{'週' if mode=='weekly' else '月'}記錄")
        lines.append(f"共 {len(logs)} 天有工作日誌。")
    
    # 教訓
    lessons = data.get("lessons_learned", [])
    if lessons:
        lines.append(f"\n## 🧠 教訓")
        for l in lessons[-3:]:
            lines.append(f"- {l[:80]}")
    
    return "\n".join(lines) if lines else "（本週尚無足夠數據）"


# === 報告生成 ===

def generate_report(mode="weekly", style="concise"):
    """生成完整報告"""
    data = collect_memory_data(mode)
    summary = generate_summary(data, style, mode)
    
    now = datetime.now()
    week_str = get_iso_week(now)
    month_str = now.strftime("%Y-%m")
    
    if mode == "weekly":
        period = week_str
        date_range = f"{data['start']} → {data['end']}"
    else:
        period = month_str
        date_range = f"{data['start']} → {data['end']}"
    
    # YAML frontmatter
    frontmatter = f"""---
date: {now.strftime('%Y-%m-%d')}
{mode}_period: "{period}"
type: {mode}-report
style: {style}
tags: [{mode}-report, {style}]
generated: "{now.isoformat()}"
---

"""
    
    # 報告正文
    if mode == "weekly":
        title = f"# 🧠 {period} 週報"
        subtitle = f"*{date_range}*"
    else:
        title = f"# 🧠 {month_str} 月報"
        subtitle = f"*{date_range} — {style}版*"
    
    # 統計數字
    stats = f"""
## 📊 數據概覽

| 指標 | 數值 |
|------|------|
| 每日記錄 | {len(data['daily_logs'])} 天 |
| 待辦任務 | {len(data['tasks_pending'])} 項 |
| 待回郵件 | {len(data['emails_pending'])} 封 |
| 活躍專案 | {len(data['projects'])} 個 |
"""
    
    # 摘要
    summary_section = f"""
## 📝 {'週' if mode=='weekly' else '月'}度摘要

{summary}
"""
    
    # 詳細版追加內容
    detail_section = ""
    if style == "detailed":
        # 每日摘要
        if data["daily_logs"]:
            detail_section += "\n## 💬 每日摘要\n\n"
            for d in data["daily_logs"][:7]:
                detail_section += f"### {d['date']}\n\n{d['content'][:400]}...\n\n---\n\n"
        
        # 專案
        if data["projects"]:
            detail_section += "\n## 📂 活躍專案\n\n"
            for p in data["projects"]:
                detail_section += f"- [[{p['name']}]]\n"
    
    # 關聯筆記
    links = """
## 🔗 相關筆記

- [[MEMORY]]
- [[follow_up_tracker]]
"""
    if mode == "weekly":
        links += f"- [[{get_iso_week(now - timedelta(days=7))}]] ← 上週報\n"
    else:
        prev_month = now.replace(day=1) - timedelta(days=1)
        links += f"- [[{prev_month.strftime('%Y-%m')}]] ← 上月報\n"
    
    report = frontmatter + title + "\n" + subtitle + "\n" + stats + summary_section + detail_section + links
    
    return report, period


def save_report(report, mode, style, period):
    """寫入 Obsidian Vault + Workspace memory/weekly/ 雙份"""
    if mode == "weekly":
        if style == "detailed":
            filename = f"{period}-detail.md"
        else:
            filename = f"{period}.md"
        obsidian_path = VAULT / "週報" / filename
        workspace_path = MEMORY_WEEKLY / filename
    else:
        if style == "detailed":
            filename = f"{period}-detail.md"
        else:
            filename = f"{period}.md"
        obsidian_path = VAULT / "月報" / filename
        workspace_path = MEMORY_WEEKLY / filename
    
    # Obsidian Vault
    obsidian_path.parent.mkdir(parents=True, exist_ok=True)
    obsidian_path.write_text(report)
    print(f"✅ Obsidian: {obsidian_path}")
    
    # Workspace memory/weekly/（方便直接查看）
    workspace_path.parent.mkdir(parents=True, exist_ok=True)
    workspace_path.write_text(report)
    print(f"✅ Workspace: {workspace_path}")
    
    return obsidian_path


# === 主程式 ===

def main():
    parser = argparse.ArgumentParser(description="MemoryHub → Obsidian 報告引擎")
    parser.add_argument("--mode", choices=["weekly", "monthly"], required=True)
    parser.add_argument("--style", choices=["concise", "detailed"], default="concise")
    args = parser.parse_args()
    
    print(f"🧠 MemoryHub → Obsidian 報告引擎")
    print(f"   模式: {args.mode} | 風格: {args.style}")
    print(f"   Vault: {VAULT}")
    print()
    
    report, period = generate_report(args.mode, args.style)
    filepath = save_report(report, args.mode, args.style, period)
    
    print(f"\n📄 報告大小: {len(report)} 字符")
    print(f"📁 存放位置: {filepath}")
    print(f"✅ 完成")


if __name__ == "__main__":
    main()
