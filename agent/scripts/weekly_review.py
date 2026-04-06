#!/usr/bin/env python3
"""
Weekly Review — Claude Opus analyzes accumulated data and generates insights.

Runs independently of the daily Nemotron agent. Produces a markdown report
with fresh insights, pattern discoveries, agent quality audit, and knowledge
base hygiene checks.

Usage:
  cd /home/yuyu/home-iot/agent
  uv run python scripts/weekly_review.py           # generate report
  uv run python scripts/weekly_review.py --dry-run  # print data package, no API call

Schedule with cron:
  0 23 * * 0  cd /home/yuyu/home-iot/agent && uv run python scripts/weekly_review.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, date, timedelta
from pathlib import Path

import httpx
import yaml

# Add agent src
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from home_iot.config import settings
from home_iot.ha import HAClient
from home_iot.tools import Tools


ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = "claude-sonnet-4-20250514"  # cost-effective for weekly review; switch to opus for deeper analysis
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
KNOWLEDGE_PATH = Path(__file__).resolve().parent.parent / "config" / "home_knowledge.yaml"
LAYOUT_PATH = Path(__file__).resolve().parent.parent / "config" / "home_layout.yaml"
QUESTIONS_PATH = Path(__file__).resolve().parent.parent / "config" / "open_questions.yaml"


REVIEW_SYSTEM_PROMPT = """\
You are an external auditor reviewing a smart home AI system. You are Claude (Anthropic),
performing a periodic review of a system normally operated by a local LLM (Nemotron Cascade 2).

Your role:
1. Provide FRESH insights the daily agent might have missed (different model = different perspective)
2. Audit the quality of accumulated knowledge and past decisions
3. Discover interesting statistics and non-obvious patterns
4. Check data quality and knowledge base hygiene
5. Make specific, actionable recommendations

You will receive a data package containing:
- Current knowledge base (entity dictionary, observations, preferences, patterns, lessons)
- Home layout and context
- Weekly data summaries (sleep, activity, environment, health metrics)
- Recent agent decisions and automation executions (if available)

## Output format

Write a markdown report in Korean with these sections:

### 📊 이번 주 핵심 수치
Top 5 most interesting statistics from this week's data.

### 🔍 새로운 인사이트
Patterns or correlations the daily agent hasn't noted. Be specific with numbers.

### 📈 추세 변화
What changed compared to previous periods? Getting better/worse?

### 🤖 에이전트 감사
Review the knowledge base: any stale observations? Wrong confidence levels?
Any learned patterns that need updating? Contradictions?

### 🧹 Knowledge Base 정리 제안
Specific entries to update, remove, or add. Reference by ID (O001, L001, etc.)

### 💡 권고사항
Concrete next actions: automation tweaks, new data to collect, experiments to try.

### 🎯 다음 주 관찰 포인트
What to watch for in the coming week based on current trends.

Be concise, specific, data-driven. Korean throughout. No fluff.
"""


async def _gather_data_package() -> str:
    """Build the data summary for Claude to review."""
    ha = HAClient()
    tools = Tools(ha)

    sections = []

    # 1. Knowledge base
    knowledge = {}
    for path in (KNOWLEDGE_PATH, LAYOUT_PATH, QUESTIONS_PATH):
        if path.exists():
            with open(path) as f:
                knowledge[path.stem] = yaml.safe_load(f) or {}

    sections.append("## Current Knowledge Base\n```yaml\n" +
                     yaml.safe_dump(knowledge.get("home_knowledge", {}),
                                    allow_unicode=True, sort_keys=False, default_flow_style=False)[:4000] +
                     "\n```")

    # 2. Sleep stats
    for days in (7, 30):
        try:
            stats = await tools.get_sleep_stats(days)
            sections.append(f"## Sleep Stats ({days}d)\n```json\n{json.dumps(stats, indent=2)}\n```")
        except Exception as e:
            sections.append(f"## Sleep Stats ({days}d)\nError: {e}")

    # 3. Activity summary
    try:
        activity = await tools.get_activity_summary(7, 15)
        sections.append(f"## Activity Summary (7d)\n```json\n{json.dumps(activity, indent=2, ensure_ascii=False)}\n```")
    except Exception as e:
        sections.append(f"## Activity Summary\nError: {e}")

    # 4. Environment (recent averages via InfluxDB)
    env_queries = {
        "temperature": ('from(bucket:"home-iot") |> range(start:-7d) |> filter(fn:(r)=>r._measurement=="°C" and r._field=="value") '
                        '|> group(columns:["entity_id"]) |> mean() |> keep(columns:["entity_id","_value"])'),
        "humidity": ('from(bucket:"home-iot") |> range(start:-7d) |> filter(fn:(r)=>r._measurement=="%" and r.entity_id=~/_humidity/ and r._field=="value") '
                     '|> group(columns:["entity_id"]) |> mean() |> keep(columns:["entity_id","_value"])'),
    }
    for name, flux in env_queries.items():
        try:
            rows = await tools._run_flux(flux)
            sections.append(f"## Environment 7d avg: {name}\n" +
                            "\n".join(f"- {r.get('entity_id')}: {r.get('value'):.1f}" for r in rows if r.get('value')))
        except Exception as e:
            sections.append(f"## Environment {name}\nError: {e}")

    # 5. Samsung Health weekly aggregates
    health_queries = {
        "heart_rate": 'from(bucket:"home-iot") |> range(start:-7d) |> filter(fn:(r)=>r._measurement=="samsung_hr" and r._field=="bpm") |> mean()',
        "stress": 'from(bucket:"home-iot") |> range(start:-7d) |> filter(fn:(r)=>r._measurement=="samsung_stress" and r._field=="score") |> mean()',
        "steps_daily": 'from(bucket:"home-iot") |> range(start:-7d) |> filter(fn:(r)=>r._measurement=="samsung_steps" and r._field=="count") |> aggregateWindow(every:1d,fn:sum,createEmpty:false) |> mean()',
        "spo2": 'from(bucket:"home-iot") |> range(start:-7d) |> filter(fn:(r)=>r._measurement=="samsung_spo2" and r._field=="spo2") |> mean()',
    }
    health_results = {}
    for name, flux in health_queries.items():
        try:
            rows = await tools._run_flux(flux)
            if rows:
                health_results[name] = rows[0].get("value")
        except:
            pass
    if health_results:
        sections.append(f"## Samsung Health 7d averages\n```json\n{json.dumps(health_results, indent=2)}\n```")

    # 6. Open questions
    if knowledge.get("open_questions", {}).get("questions"):
        open_qs = [q for q in knowledge["open_questions"]["questions"] if q.get("status") == "open"]
        if open_qs:
            sections.append(f"## Open Questions ({len(open_qs)})\n" +
                            "\n".join(f"- {q['id']}: {q['question']}" for q in open_qs))

    await ha.aclose()
    return "\n\n".join(sections)


async def _call_claude(data_package: str) -> str:
    """Call Claude API with the data package."""
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": ANTHROPIC_MODEL,
                "max_tokens": 4096,
                "system": REVIEW_SYSTEM_PROMPT,
                "messages": [
                    {"role": "user", "content": f"다음은 이번 주 데이터 패키지입니다. 주간 리뷰를 작성해주세요.\n\n{data_package}"},
                ],
            },
        )
        if resp.status_code != 200:
            print(f"API error {resp.status_code}: {resp.text[:500]}")
            resp.raise_for_status()
        data = resp.json()
        return data["content"][0]["text"]


def _save_report(report: str) -> Path:
    """Save report to reports/ directory."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today()
    week_num = today.isocalendar()[1]
    filename = f"weekly-{today.year}-W{week_num:02d}.md"
    path = REPORTS_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# Weekly Review — {today.year} W{week_num}\n")
        f.write(f"_Generated: {datetime.now().isoformat()}_\n")
        f.write(f"_Model: {ANTHROPIC_MODEL}_\n\n")
        f.write(report)
    return path


async def main():
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

    dry_run = "--dry-run" in sys.argv

    print("📦 Gathering data package...")
    data_package = await _gather_data_package()

    if dry_run:
        print("\n=== DATA PACKAGE (dry run) ===")
        print(data_package)
        print(f"\n=== Package size: {len(data_package)} chars ===")
        return

    print(f"📦 Data package: {len(data_package)} chars")
    print(f"🤖 Calling Claude ({ANTHROPIC_MODEL})...")
    report = await _call_claude(data_package)

    path = _save_report(report)
    print(f"✅ Report saved: {path}")
    print(f"   Size: {len(report)} chars")
    print(f"\n{'='*60}")
    print(report)


if __name__ == "__main__":
    asyncio.run(main())
