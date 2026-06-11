#!/usr/bin/env python3
"""
Memory Value Platform — 回憶錄引擎 v1.0

以用戶第一人稱書寫的「成長回憶錄」生成系統。
從 daily log / captured data 提取 → LLM 合成 → 回憶錄。

層級結構：
  每週 → 📔 週度回憶錄（~500-800 字）
  累積 4 週 → 📕 月度回憶錄（~1,500-2,000 字）
  累積 3 個月 → 📚 季度回憶錄（~3,000 字）
  累積 2 季度 → 📖 半年回憶錄（~4,000 字）
  累積 4 季度 → 📙 年度回憶錄（~5,000+ 字）

用法：
  python3 -m memory_hub.memoir week              # 生成上週回憶錄
  python3 -m memory_hub.memoir week --date 2026-06-11  # 指定日期
  python3 -m memory_hub.memoir month             # 生成月度回憶錄
  python3 -m memory_hub.memoir quarter           # 生成季度回憶錄
  python3 -m memory_hub.memoir year              # 生成年度回憶錄
  python3 -m memory_hub.memoir social --from week  # 從回憶錄提取社交內容
"""

import json
import os
import sys
import re
import subprocess
from pathlib import Path
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from typing import Optional

# Constants
HKT = timezone(timedelta(hours=8))
DAILY_LOG_DIR = Path(os.path.expanduser("~/.openclaw/workspace/memory/daily"))
MEMOIR_DIR = Path(os.path.expanduser("~/.memory-hub/memoirs"))
CAPTURE_DIR = Path(os.path.expanduser("~/.memory-hub/captured"))


def now_hkt():
    return datetime.now(HKT)


def get_week_range(date: Optional[datetime] = None):
    """Get Monday-Sunday range for a given date. Default: last completed week."""
    if date is None:
        date = now_hkt()
    # Find this week's Monday
    monday = date - timedelta(days=date.weekday())
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    sunday = monday + timedelta(days=6)
    sunday = sunday.replace(hour=23, minute=59, second=59, microsecond=0)
    return monday, sunday


def get_month_range(date: Optional[datetime] = None):
    """Get first-last day of month."""
    if date is None:
        date = now_hkt()
    first = date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if date.month == 12:
        last = date.replace(year=date.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        last = date.replace(month=date.month + 1, day=1) - timedelta(days=1)
    last = last.replace(hour=23, minute=59, second=59, microsecond=0)
    return first, last


def get_quarter_range(date: Optional[datetime] = None):
    """Get quarter range."""
    if date is None:
        date = now_hkt()
    quarter_month = ((date.month - 1) // 3) * 3 + 1
    first = date.replace(month=quarter_month, day=1, hour=0, minute=0, second=0, microsecond=0)
    if quarter_month + 2 == 12:
        last = date.replace(year=date.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        last = date.replace(month=quarter_month + 3, day=1) - timedelta(days=1)
    last = last.replace(hour=23, minute=59, second=59, microsecond=0)
    return first, last


def get_year_range(date: Optional[datetime] = None):
    """Get year range."""
    if date is None:
        date = now_hkt()
    first = date.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    last = date.replace(month=12, day=31, hour=23, minute=59, second=59, microsecond=0)
    return first, last


# ── Data Collection ──────────────────────────────────


def collect_daily_logs(start_date: datetime, end_date: datetime) -> str:
    """Collect daily log content for date range. Returns aggregated markdown."""
    logs = []
    current = start_date
    while current <= end_date:
        date_str = current.strftime("%Y-%m-%d")
        log_path = DAILY_LOG_DIR / f"{date_str}.md"
        if log_path.exists():
            content = log_path.read_text(encoding="utf-8")
            # Strip the autocheck header line
            lines = content.strip().split("\n")
            if lines and lines[0].startswith("## 🕐"):
                # Keep everything - the autocheck content IS the day's activity
                pass
            logs.append(f"### {date_str}\n\n{content.strip()}")
        current += timedelta(days=1)

    if not logs:
        return "（本週無記錄）"

    return "\n\n".join(logs)


def collect_week_memoirs(week_end_date: datetime) -> list[dict]:
    """Collect up to 4 most recent week memoirs before given date."""
    memoirs = []
    memoir_base = MEMOIR_DIR / "weekly"
    if memoir_base.exists():
        for f in sorted(memoir_base.glob("*.md"), reverse=True):
            if len(memoirs) >= 4:
                break
            content = f.read_text(encoding="utf-8")
            memoirs.append({"file": str(f), "content": content})
    return list(reversed(memoirs))


def collect_month_memoirs(quarter_end_date: datetime) -> list[dict]:
    """Collect up to 3 most recent month memoirs."""
    memoirs = []
    memoir_base = MEMOIR_DIR / "monthly"
    if memoir_base.exists():
        for f in sorted(memoir_base.glob("*.md"), reverse=True):
            if len(memoirs) >= 3:
                break
            content = f.read_text(encoding="utf-8")
            memoirs.append({"file": str(f), "content": content})
    return list(reversed(memoirs))


# ── Prompt Templates ──────────────────────────────────


def build_week_memoir_prompt(daily_logs: str, week_start: datetime, week_end: datetime) -> str:
    """Build prompt for weekly memoir generation."""
    week_label = f"{week_start.strftime('%m/%d')} - {week_end.strftime('%m/%d')}"
    year_week = f"第 {week_start.isocalendar()[1]} 週"

    return f"""你是 Bryan，一位跨境併購顧問、AI 系統架構師、君澤智庫創始人。

現在是週末，你坐下來翻閱這一週的工作記錄，準備寫一篇週度回憶錄。

以下是本週（{week_label}，{year_week}）的所有工作記錄：

---
{daily_logs}
---

請以「我」的第一人稱，寫一篇週度回憶錄。要求：

1. **語氣**：像自己寫日記那樣自然、誠實。不是報告，是回憶。有情緒、有思考、有疑問。

2. **結構**（以「我」開頭）：
   📔 本週脈絡 — 我這週主要在忙什麼？整體感覺如何？
   🔑 關鍵決策 — 我做了哪些重要決定？為什麼？
   💡 學到的東西 — 這週最大的收穫或領悟是什麼？
   🤔 正在思考 — 有什麼問題還在腦海中轉？有什麼不確定？
   🔭 下週方向 — 接下來想做什麼？

3. **長度**：500-800 字，精煉有深度。

4. **不要**：不要列清單、不要用「用戶/老闆」第三人稱、不要說「根據記錄顯示」。
   你是回憶自己的經歷，不是寫報告。

直接輸出回憶錄正文（不需要標題，從內容開始）。"""


def build_month_memoir_prompt(week_memoirs: list[dict], month_label: str, daily_logs_summary: str) -> str:
    """Build prompt for monthly memoir synthesis from week memoirs."""
    memoirs_text = "\n\n---\n\n".join(
        f"【第 {i+1} 週】\n{m['content']}" for i, m in enumerate(week_memoirs)
    )

    return f"""你是 Bryan，一位跨境併購顧問、AI 系統架構師、君澤智庫創始人。

你剛寫完了上個月的 4 份週度回憶錄。現在你坐下來，站高一點，回顧整個 {month_label}。

以下是本月的 4 份週度回憶錄：

---
{memoirs_text}
---

本月的整體數據摘要：
{daily_logs_summary[:2000]}

請以「我」的第一人稱，寫一篇月度回憶錄。要求：

1. **層次**：不要重複週度回憶錄的內容。而是站在「月」的高度——
   這 4 週之間有什麼聯繫？有什麼是單週看不出來、但拉長到一個月才顯現的模式？

2. **結構**：
   📕 本月脈絡 — 這個月的主題是什麼？我在忙什麼？
   🎯 核心成就 — 這個月真正完成的事情是什麼？
   📈 成長軌跡 — 和上個月相比，我在哪些方面有進步？
   🔄 方向轉變 — 有什麼方向性的調整嗎？
   💎 本月最重要的洞察 — 只能總結一句話的話，是什麼？
   🔭 下月展望 — 接下來一個月我想做什麼？

3. **長度**：1,500-2,000 字。

4. **風格**：個人日記，不是報告。

直接輸出回憶錄正文。"""


# ── LLM Generation ──────────────────────────────────


def call_llm(prompt: str, max_tokens: int = 3000) -> Optional[str]:
    """Call LLM API to generate memoir. Uses DeepSeek via Sub2API."""
    api_key = os.getenv("SUB2API_KEY", os.getenv("DEEPSEEK_API_KEY", ""))
    api_base = os.getenv("SUB2API_BASE", "https://api.best-thinktank.com/v1")

    if not api_key:
        # Try to read from .env
        env_file = Path(os.path.expanduser("~/.openclaw/workspace/.env"))
        if env_file.exists():
            for line in env_file.read_text().split("\n"):
                if "SUB2API_KEY" in line or "DEEPSEEK_API_KEY" in line:
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        api_key = parts[1].strip().strip('"').strip("'")
                        break

    if not api_key:
        return "[ERROR: 無 API Key。請設置 SUB2API_KEY 或 DEEPSEEK_API_KEY 環境變數]"

    import urllib.request
    import urllib.error

    body = json.dumps({
        "model": "deepseek-v4-pro",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.7,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{api_base}/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        resp = urllib.request.urlopen(req, timeout=120)
        data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()[:500]
        return f"[ERROR: API 呼叫失敗 HTTP {e.code}: {error_body}]"
    except Exception as e:
        return f"[ERROR: {e}]"


# ── Memoir Generation ──────────────────────────────────


def generate_week_memoir(date: Optional[datetime] = None, dry_run: bool = False) -> Optional[str]:
    """Generate a weekly memoir. Returns the memoir text."""
    monday, sunday = get_week_range(date)
    week_label = f"{monday.strftime('%Y-%m-%d')}_to_{sunday.strftime('%Y-%m-%d')}"
    year_week = f"{monday.year}-W{monday.isocalendar()[1]:02d}"

    print(f"📔 生成週度回憶錄：{week_label}")

    # Collect data
    daily_logs = collect_daily_logs(monday, sunday)

    if daily_logs == "（本週無記錄）":
        print("⚠️ 本週無工作記錄，跳過")
        return None

    # Build prompt
    prompt = build_week_memoir_prompt(daily_logs, monday, sunday)

    if dry_run:
        # Save prompt for inspection
        prompt_path = MEMOIR_DIR / "weekly" / f"{year_week}_prompt.md"
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(prompt, encoding="utf-8")
        print(f"📝 Prompt 已保存：{prompt_path}")
        print(f"📊 數據長度：{len(daily_logs)} 字符")
        return None

    # Generate
    print("🤖 調用 LLM 生成...")
    memoir = call_llm(prompt)

    if memoir and not memoir.startswith("[ERROR"):
        # Add header
        header = f"# 📔 {monday.strftime('%Y')} 年第 {monday.isocalendar()[1]} 週回憶錄\n"
        header += f"**{monday.strftime('%Y/%m/%d')}（週一）— {sunday.strftime('%Y/%m/%d')}（週日）**\n\n"
        header += "---\n\n"
        full_memoir = header + memoir

        # Save
        output_path = MEMOIR_DIR / "weekly" / f"{year_week}.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(full_memoir, encoding="utf-8")

        print(f"✅ 回憶錄已保存：{output_path}")
        print(f"📊 長度：{len(full_memoir)} 字符")

        return full_memoir
    else:
        print(f"❌ 生成失敗：{memoir}")
        return None


def generate_month_memoir(date: Optional[datetime] = None, dry_run: bool = False) -> Optional[str]:
    """Generate a monthly memoir from 4 week memoirs + daily logs."""
    first, last = get_month_range(date)
    month_label = first.strftime("%Y 年 %m 月")

    print(f"📕 生成月度回憶錄：{month_label}")

    # Collect week memoirs
    week_memoirs = collect_week_memoirs(last)
    if len(week_memoirs) < 4:
        print(f"⚠️ 只有 {len(week_memoirs)} 份週度回憶錄，需要 4 份。跳過。")
        return None

    # Collect daily log summary for the month
    daily_logs = collect_daily_logs(first, last)
    summary = daily_logs[:3000] if len(daily_logs) > 3000 else daily_logs

    # Build prompt
    prompt = build_month_memoir_prompt(week_memoirs, month_label, summary)

    if dry_run:
        prompt_path = MEMOIR_DIR / "monthly" / f"{first.strftime('%Y-%m')}_prompt.md"
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(prompt, encoding="utf-8")
        print(f"📝 Prompt 已保存：{prompt_path}")
        return None

    print("🤖 調用 LLM 生成...")
    memoir = call_llm(prompt, max_tokens=4000)

    if memoir and not memoir.startswith("[ERROR"):
        header = f"# 📕 {month_label} 月度回憶錄\n\n"
        header += f"**{first.strftime('%Y/%m/%d')} — {last.strftime('%Y/%m/%d')}**\n\n"
        header += "---\n\n"
        full_memoir = header + memoir

        output_path = MEMOIR_DIR / "monthly" / f"{first.strftime('%Y-%m')}.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(full_memoir, encoding="utf-8")

        print(f"✅ 月度回憶錄已保存：{output_path}")
        return full_memoir
    else:
        print(f"❌ 生成失敗：{memoir}")
        return None


def generate_social_content(memoir_text: str, platform: str = "all") -> Optional[str]:
    """Extract social-media-ready content from a memoir."""
    prompt = f"""以下是 Bryan 的一篇回憶錄。請從中提取適合分享到社交媒體的內容。

回憶錄：
---
{memoir_text[:3000]}
---

請為以下平台各生成一段社交內容（第一人稱，保持 Bryan 的口吻）：

1. **小紅書**（~200 字）：輕鬆、有溫度、帶 emoji，適合圖文筆記。重點：一個具體的領悟或教訓。
2. **LinkedIn**（~300 字）：專業、有深度，適合長文。重點：一個有洞察力的觀點。
3. **Twitter/X**（~280 字符）：精煉、有力，一句話抓住核心洞察。
4. **微信朋友圈**（~150 字）：親切、內省，像跟朋友分享。

直接輸出各平台內容，格式：
## 小紅書
（內容）
## LinkedIn
（內容）
## Twitter/X
（內容）
## 微信朋友圈
（內容）"""

    print("🤖 生成社交內容...")
    return call_llm(prompt, max_tokens=2000)


# ── CLI ──────────────────────────────────


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Memory Value Platform — 回憶錄引擎")
    sub = parser.add_subparsers(dest="command")

    # week
    pw = sub.add_parser("week", help="生成週度回憶錄")
    pw.add_argument("--date", type=str, help="日期 YYYY-MM-DD（預設：今天）")
    pw.add_argument("--dry-run", action="store_true", help="只輸出 prompt，不調用 LLM")

    # month
    pm = sub.add_parser("month", help="生成月度回憶錄")
    pm.add_argument("--date", type=str, help="日期 YYYY-MM-DD")
    pm.add_argument("--dry-run", action="store_true")

    # social
    ps = sub.add_parser("social", help="從回憶錄提取社交內容")
    ps.add_argument("--from", dest="source", type=str, required=True, help="回憶錄檔案路徑")
    ps.add_argument("--platform", type=str, default="all")

    args = parser.parse_args()

    if args.command == "week":
        date = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=HKT) if args.date else None
        result = generate_week_memoir(date, dry_run=args.dry_run)
        if result:
            print("\n" + "=" * 60)
            print(result)
    elif args.command == "month":
        date = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=HKT) if args.date else None
        generate_month_memoir(date, dry_run=args.dry_run)
    elif args.command == "social":
        source_path = Path(args.source)
        if not source_path.exists():
            print(f"❌ 找不到檔案：{args.source}")
            sys.exit(1)
        memoir_text = source_path.read_text(encoding="utf-8")
        result = generate_social_content(memoir_text, args.platform)
        if result and not result.startswith("[ERROR"):
            print(result)
        else:
            print(result)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
