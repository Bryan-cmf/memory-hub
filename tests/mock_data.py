#!/usr/bin/env python3
"""Mock session data generators for 4 AI platforms.

Creates realistic session files that the MemoryHub daemon can parse,
matching the exact format of each platform's session storage.
"""

import json
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta

HKT = timezone(timedelta(hours=8))

# ── Conversations in Traditional Chinese ──────────

CONVERSATIONS = [
    # OpenClaw conversation (financial research)
    [
        ("user", "幫我查一下騰訊最新股價"),
        ("assistant", "騰訊控股(0700.HK)目前報 HK$385.20，較前日上漲 1.2%。成交量 1,820 萬股。"),
        ("user", "和上週同期比較呢"),
        ("assistant", "上週同期報 HK$378.50，本週累計上漲 1.77%。同期恆指上漲 0.8%，騰訊跑贏大市。"),
        ("user", "技術面如何"),
        ("assistant", "MACD 黃金交叉已形成，RSI 報 62 未超買，20 日均線 HK$380 形成支撐。短期阻力位在 HK$392。"),
        ("user", "有分析師報告嗎"),
        ("assistant", "摩根士丹利維持增持評級，目標價 HK$450；高盛中性，目標價 HK$410。市場共識目標價 HK$428。"),
        ("user", "做一份完整的 DD 報告，PDF 格式"),
        ("assistant", "正在生成 00700_騰訊控股_DD報告.pdf…\n\n報告包含：\n1. 公司概況\n2. 五年財務分析\n3. 股權結構\n4. 技術面分析\n5. 風險因素\n6. 估值模型(DCF)"),
        ("user", "把這份報告發到飛書"),
        ("assistant", "已發送至飛書。文檔 ID: doc_00700_dd_20260520"),
    ],
    # Hermes conversation (morning briefing)
    [
        ("user", "今天有什麼重要新聞"),
        ("assistant", "## 📰 2026年5月20日 晨間快報\n\n### 港股\n- 恆指高開 120 點，報 19,850\n- 科技股領漲，騰訊 +1.2%、美團 +2.1%\n\n### A股\n- 上證指數開盤 +0.3%\n- 新能源板塊活躍"),
        ("user", "有沒有重要公告"),
        ("assistant", "今日重要公告：\n• 0700.HK 騰訊 — 回購 120 萬股，涉資 4.6 億\n• 9988.HK 阿里巴巴 — 董事會變動公告\n• 1810.HK 小米 — 新產品發佈會通知"),
        ("user", "幫我整理成要點發給老闆"),
        ("assistant", "已整理要點並發送至老闆。\n\n摘要：今日港股高開，科技股領漲。騰訊回購 4.6 億，阿里董事變動。建議關注午後走勢。"),
    ],
    # DeepSeek conversation (deep research)
    [
        ("user", "做一個新能源汽車行業的深度調研"),
        ("assistant", "我將為您進行新能源汽車行業深度調研。讓我先收集最新行業數據。"),
        ("user", "重點關注比亞迪、蔚來、小鵬"),
        ("assistant", "好的。以下是三家公司的初步比較：\n\n| 指標 | 比亞迪(1211.HK) | 蔚來(9866.HK) | 小鵬(9868.HK) |\n|------|----------------|---------------|---------------|\n| 2025 交付量 | 427 萬輛 | 22 萬輛 | 19 萬輛 |\n| 毛利率 | 22.4% | 12.1% | 6.8% |\n| 研發投入 | 532 億 | 134 億 | 68 億 |"),
        ("user", "比亞迪的海外擴張策略如何"),
        ("assistant", "比亞迪海外策略分析：\n\n1. **泰國工廠** — 年產能 15 萬輛，已投產\n2. **匈牙利工廠** — 規劃產能 20 萬輛，2027 投產\n3. **巴西工廠** — 年產能 15 萬輛，在建\n4. **印尼工廠** — 年產能 15 萬輛，規劃中\n\n合計海外規劃產能 65 萬輛，佔總產能約 15%。\n\n主要市場：東南亞(40%)、歐洲(25%)、南美(20%)、其他(15%)"),
        ("user", "生成調研報告"),
        ("assistant", "正在生成 新能源汽車行業深度調研報告.pdf…\n\n已完成章節：\n1. 行業概述與政策環境\n2. 市場規模與成長預測(2026-2030)\n3. 競爭格局分析\n4. 三大標的公司深度分析\n5. 供應鏈分析\n6. 估值比較\n7. 投資建議"),
    ],
    # Claude Code conversation (coding task)
    [
        ("user", "幫我寫一個 Python 腳本，自動從 DI 披露易抓取股權變動數據"),
        ("assistant", "我將為您創建一個 DI 披露易數據抓取腳本。\n\n分析需求：\n- 輸入：港股代碼\n- 輸出：股權變動記錄(日期/股東/變動/持股比例)\n- 技術路徑：requests + BeautifulSoup\n\n讓我開始編寫…"),
        ("user", "加上錯誤處理和速率限制"),
        ("assistant", "已添加：\n- HTTP 429 重試機制(最多3次)\n- 請求間隔 3 秒(避免被封)\n- 網絡異常自動重連\n- JSON 格式輸出\n- 日誌記錄"),
        ("user", "測試一下，用 0700.HK"),
        ("assistant", "正在測試 0700.HK…\n\n✅ 成功連接 DI 披露易\n✅ 獲取股權變動記錄 47 條\n✅ 最新記錄：2026-05-19, Naspers 減持 0.12%, 持股 24.89%\n✅ JSON 輸出已保存"),
    ],
]


def generate_openclaw_sessions(home: Path):
    """Generate mock OpenClaw session JSONL files."""
    sessions_dir = home / ".openclaw/agents/main/sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    session_id = "mock-session-oc-001"
    filepath = sessions_dir / f"{session_id}.jsonl"

    lines = []
    timestamp = datetime(2026, 5, 20, 9, 0, 0, tzinfo=HKT)

    for role, content in CONVERSATIONS[0]:
        timestamp = timestamp + timedelta(seconds=30)
        entry = {
            "type": "message",
            "message": {
                "role": role,
                "content": [{"type": "text", "text": content}],
            },
            "timestamp": timestamp.isoformat(),
            "sessionId": session_id,
        }
        lines.append(json.dumps(entry, ensure_ascii=False))

    filepath.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return filepath


def generate_hermes_sessions(home: Path):
    """Generate mock Hermes session JSONL files."""
    sessions_dir = home / ".hermes/sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    filepath = sessions_dir / "20260520_mock_session.jsonl"

    lines = []
    timestamp = datetime(2026, 5, 20, 8, 0, 0, tzinfo=HKT)

    for role, content in CONVERSATIONS[1]:
        timestamp = timestamp + timedelta(seconds=45)
        entry = {
            "role": role,
            "content": content,
            "timestamp": timestamp.isoformat(),
        }
        lines.append(json.dumps(entry, ensure_ascii=False))

    filepath.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return filepath


def generate_deepseek_sessions(home: Path):
    """Generate mock DeepSeek checkpoint JSON files."""
    sessions_dir = home / ".deepseek/sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    filepath = sessions_dir / "mock-session-ds-001.json"

    messages = []
    timestamp = datetime(2026, 5, 20, 10, 0, 0, tzinfo=HKT)

    for role, content in CONVERSATIONS[2]:
        timestamp = timestamp + timedelta(seconds=60)
        blocks = []
        if role == "assistant":
            blocks.append({"type": "thinking", "thinking": f"Analyzing request: {content[:30]}..."})
            blocks.append({"type": "text", "text": content})
        else:
            blocks.append({"type": "text", "text": content})
        messages.append({
            "role": role,
            "content": blocks,
            "timestamp": timestamp.isoformat(),
        })

    # Add some tool_use / tool_result blocks for realistic testing
    extra = [
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "call_01", "name": "web_search",
                 "input": {"query": "比亞迪 2025 交付量 新能源"}},
            ],
            "timestamp": (timestamp + timedelta(seconds=30)).isoformat(),
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "call_01",
                 "content": "比亞迪 2025 年全年交付量達 427 萬輛，同比增長 41%"},
            ],
            "timestamp": (timestamp + timedelta(seconds=35)).isoformat(),
        },
    ]
    messages.extend(extra)

    data = {
        "schema_version": 1,
        "metadata": {
            "session_id": "mock-session-ds-001",
            "created_at": datetime(2026, 5, 20, 10, 0, 0, tzinfo=HKT).isoformat(),
        },
        "messages": messages,
        "system_prompt": "You are a helpful research assistant.",
        "artifacts": [],
    }

    filepath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return filepath


def generate_claude_sessions(home: Path):
    """Generate mock Claude Code session files.

    Claude Code JSONL (event log, no role/content):
    - Project event log: type-based entries (last-prompt, attachment, etc.)
    - Session metadata: pid, status, cwd, etc.
    """
    # Project event log JSONL
    projects_dir = home / ".claude/projects/-Test-Project"
    projects_dir.mkdir(parents=True, exist_ok=True)

    project_file = projects_dir / "mock-claude-project.jsonl"

    timestamp = int(datetime(2026, 5, 20, 14, 0, 0, tzinfo=HKT).timestamp() * 1000)
    events = []
    for i, (role, content) in enumerate(CONVERSATIONS[3]):
        event = {
            "type": "attachment" if i % 2 == 0 else "last-prompt",
            "leafUuid": f"leaf-{i:04d}",
            "sessionId": "mock-claude-session-001",
            "timestamp": timestamp + i * 60000,
            "userType": "user" if role == "user" else "assistant",
            "cwd": str(projects_dir),
            "version": "2.0.0",
            "entrypoint": "cli",
        }
        events.append(json.dumps(event, ensure_ascii=False))

    # Add metadata events
    events.append(json.dumps({
        "type": "permission-mode",
        "permissionMode": "bypassPermissions",
        "sessionId": "mock-claude-session-001",
    }, ensure_ascii=False))

    project_file.write_text("\n".join(events) + "\n", encoding="utf-8")

    # Session metadata
    sessions_dir = home / ".claude/sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    session_file = sessions_dir / "mock-claude-session.json"
    session_data = {
        "pid": 12345,
        "sessionId": "mock-claude-session-001",
        "cwd": str(projects_dir),
        "startedAt": timestamp,
        "procStart": datetime(2026, 5, 20, 14, 0, 0, tzinfo=HKT).isoformat(),
        "version": "2.0.0",
        "peerProtocol": 1,
        "kind": "claude-code",
        "entrypoint": "cli",
        "status": "completed",
        "updatedAt": timestamp + 300000,
    }
    session_file.write_text(json.dumps(session_data, ensure_ascii=False, indent=2), encoding="utf-8")

    return project_file


def generate_all(home: Path):
    """Generate mock sessions for all 4 platforms."""
    home = Path(home)
    files = {}

    files["openclaw"] = generate_openclaw_sessions(home)
    files["hermes"] = generate_hermes_sessions(home)
    files["deepseek"] = generate_deepseek_sessions(home)
    files["claude"] = generate_claude_sessions(home)

    # Create platform config files for MCP verification
    mcp_config = {
        "servers": {
            "memory-hub": {
                "command": "python3",
                "args": ["-m", "memory_hub.server.mcp_server"],
                "env": {
                    "EMBEDDING_MODEL": "BAAI/bge-m3",
                    "QDRANT_URL": "http://localhost:6333",
                    "DAEMON_HOOK_URL": "http://localhost:3999/hook",
                }
            }
        }
    }

    for platform, config_path in [
        ("openclaw", home / ".openclaw/openclaw.json"),
        ("hermes", home / ".hermes/mcp.json"),
        ("deepseek", home / ".deepseek/mcp.json"),
        ("claude", home / ".claude/mcp.json"),
    ]:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        if platform == "openclaw":
            cfg = {"mcp": mcp_config}
        elif platform == "claude":
            cfg = {"mcpServers": mcp_config["servers"]}
        else:
            cfg = mcp_config
        config_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")

    return files


def count_messages(files: dict) -> dict:
    """Count mock messages per platform."""
    counts = {}
    counts["openclaw"] = len(CONVERSATIONS[0])
    counts["hermes"] = len(CONVERSATIONS[1])
    counts["deepseek"] = len(CONVERSATIONS[2]) + 2  # +2 tool_use/tool_result blocks
    counts["claude"] = 0  # No role/content in Claude event log
    return counts


if __name__ == "__main__":
    import tempfile
    test_home = Path(tempfile.mkdtemp(prefix="mh_mock_"))
    files = generate_all(test_home)
    print(f"Mock data generated at: {test_home}")
    for platform, fp in files.items():
        size = fp.stat().st_size if fp.exists() else 0
        print(f"  {platform}: {fp} ({size} bytes)")
    print(f"\nExpected message counts: {count_messages(files)}")
