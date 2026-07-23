#!/usr/bin/env python3
"""
旁路渠道 — 绕过学历过滤器的岗位发现。
用法1（搜索模式）: python scripts/off_platform.py search → 打印搜索关键词，Agent 用它搜
用法2（导入模式）: echo '[...]' | python scripts/off_platform.py import → 评分+写入 applications.json
ponytail: 不自己爬，HTTP爬取91job等SPA不可靠，让Agent用web_search处理。
"""

import json, sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent.parent
DATA_FILE = ROOT / "data" / "applications.json"

# 职业院校 → 校招信息不受学历硬过滤
SCHOOL_NAMES = [
    "南京机电职业技术学院 就业网 招聘",
    "南京科技职业学院 就业网 招聘",
    "常州机电职业技术学院 就业网 招聘 电气",
    "南京信息职业技术学院 就业网 招聘 自动化",
    "江苏海事职业技术学院 就业网 招聘",
    "南京工业职业技术大学 就业网 招聘 电气",
]

# 绕过BOSS/51job的搜索词 — 这些渠道老板直接发，不看学历
SEARCH_QUERIES = SCHOOL_NAMES + [
    "南京 PLC 调试 实习生 招聘 site:qq.com",
    "南京 电气 自动化 实习生 大专 招聘",
    "常州 机器人 调试 实习 招聘",
    "南京 电工 助理工程师 应届 招聘",
    "苏州 电气 实习 大专 招聘 site:58.com",
    "南京 人才市场 电气 招聘 最新",
    "南京 制造业 技术员 大专 招聘 2026",
    "机器人 调试 实习 大专 site:zhaopin.com",
]

TARGET_KEYWORDS = [
    "电气", "自动化", "PLC", "机器人", "机电", "调试",
    "嵌入式", "单片机", "CAD", "装配", "设备", "维护",
    "电工", "仪器", "仪表", "传感器", "电机", "变频器",
    "技术员", "实习生", "应届", "助理工程师",
]

NEGATIVE_KEYWORDS = [
    "销售", "客服", "Java", "Python", "前端", "算法",
    "架构", "经理", "总监", "保险", "搬运", "普工",
    "操作工", "CNC", "数控", "注塑", "流水线",
]


def score(title, snippet=""):
    text = f"{title} {snippet}".lower()
    s = 0
    for kw in TARGET_KEYWORDS:
        if kw.lower() in text:
            s += 1
    if "南京" in text:
        s += 2
    for kw in NEGATIVE_KEYWORDS:
        if kw.lower() in text:
            s -= 3
    return max(0, min(s, 5))


def parse_search_results(raw_json):
    """解析 web_search 返回的 JSON → 标准化岗位列表。"""
    results = []
    try:
        data = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
        items = data.get("data", {}).get("web", []) if isinstance(data, dict) else data
        if isinstance(items, list):
            for item in items:
                title = item.get("title", "")
                url = item.get("url", "")
                desc = item.get("description", "")
                s = score(title, desc)
                if s >= 1:
                    results.append({
                        "company": title.split(" -")[0].split(" |")[0][:40],
                        "position": title[:80],
                        "platform": "off_platform",
                        "url": url,
                        "jd_summary": desc[:200],
                        "score": s,
                        "status": "discovered",
                        "applied_at": datetime.now().isoformat(),
                        "notes": f"旁路搜索·绕过学历过滤",
                    })
    except Exception:
        pass
    return results


def merge_into_db(entries):
    """追加不重复的到 applications.json。"""
    existing = {"applications": [], "stats": {}}
    if DATA_FILE.exists():
        try:
            existing = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except:
            pass

    apps = existing.get("applications", [])
    existing_keys = {a.get("url", "").strip() for a in apps if a.get("url")}
    new = [e for e in entries if e["url"].strip() not in existing_keys]
    apps.extend(new)

    existing["applications"] = apps
    existing["stats"] = existing.get("stats", {
        "total_applied": 0, "hr_replied": 0,
        "interview_scheduled": 0, "rejected": 0
    })
    existing["stats"]["total_applied"] = len(apps)
    DATA_FILE.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(new), len(apps)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "search":
        print(json.dumps({"queries": SEARCH_QUERIES}, ensure_ascii=False))
    elif len(sys.argv) > 1 and sys.argv[1] == "import":
        raw = sys.stdin.read()
        entries = parse_search_results(raw)
        added, total = merge_into_db(entries)
        print(json.dumps({"added": added, "total": total, "entries": len(entries)}, ensure_ascii=False))
    else:
        print("用法: search | import (pipe JSON from web_search via stdin)")
