#!/usr/bin/env python3
"""JobBot HTML 看板生成器 — 从 applications.json 生成可视化投递状态看板"""

import json
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent.parent
DATA_FILE = ROOT / "data" / "applications.json"
OUTPUT = ROOT / "data" / "dashboard.html"

def load_data():
    if DATA_FILE.exists():
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"applications": {}, "stats": {}}

def generate(data):
    apps = data.get("applications", {})
    empty = not apps
    if empty:
        content = "<p style='text-align:center;color:#888;margin:80px 0 0 0;font-size:16px'>暂无投递记录。<br>说「帮我搜岗位」开始第一轮搜索吧。</p>"

    # Stats
    stats = {"APPLIED": 0, "HR_REPLIED": 0, "IN_CONVERSATION": 0, "INTERVIEW_SCHEDULED": 0,
             "REJECTED": 0, "NO_RESPONSE": 0, "DISCOVERED": 0, "MATCHED": 0}
    for app in apps.values():
        s = app.get("status", "DISCOVERED")
        if s in stats:
            stats[s] += 1

    # Platform stats
    platforms = {}
    for app in apps.values():
        p = app.get("platform", "unknown")
        platforms[p] = platforms.get(p, 0) + 1

    rows = ""
    for uid, app in sorted(apps.items(), key=lambda x: x[1].get("applied_at", ""), reverse=True):
        status_label = app.get("status", "DISCOVERED")
        status_color = {
            "INTERVIEW_SCHEDULED": "#22c55e", "HR_REPLIED": "#3b82f6",
            "IN_CONVERSATION": "#8b5cf6", "APPLIED": "#f59e0b",
            "REJECTED": "#ef4444", "NO_RESPONSE": "#6b7280",
            "DISCOVERED": "#9ca3af", "MATCHED": "#6366f1"
        }.get(status_label, "#9ca3af")

        score = app.get("match_score", "—")
        url = app.get("url", "#")
        rows += f"""
        <tr>
            <td>{app.get('company','—')}</td>
            <td>{'<a href="'+url+'" target="_blank">'+app.get('job','—')+'</a>' if url != '#' else app.get('job','—')}</td>
            <td>{app.get('location','—')}</td>
            <td>{app.get('salary','—')}</td>
            <td>{score}</td>
            <td><span style="background:{status_color};color:white;padding:2px 8px;border-radius:10px;font-size:12px;">{status_label}</span></td>
            <td>{app.get('applied_at','—')[:10] if app.get('applied_at') else '—'}</td>
        </tr>"""

    empty_body = ""
    if empty:
        empty_body = content
    
    table_section = "" if empty else f"""<table><thead><tr>
<th>公司</th><th>岗位</th><th>地点</th><th>薪资</th><th>匹配度</th><th>状态</th><th>投递时间</th>
</tr></thead><tbody>{rows}</tbody></table>"""

    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>JobBot 投递看板</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f5f5f5;color:#333;padding:20px}}
.container{{max-width:1200px;margin:0 auto}}
h1{{font-size:24px;margin-bottom:4px}}
.updated{{color:#888;font-size:13px;margin-bottom:20px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:24px}}
.card{{background:white;border-radius:10px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,.1);text-align:center}}
.card .num{{font-size:32px;font-weight:bold}}
.card .label{{color:#888;font-size:13px;margin-top:4px}}
.platform-tags{{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}}
.tag{{background:white;padding:4px 12px;border-radius:12px;font-size:13px;box-shadow:0 1px 2px rgba(0,0,0,.08)}}
table{{width:100%;background:white;border-radius:10px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.1);border-collapse:collapse}}
th{{background:#f8f9fa;padding:12px 14px;text-align:left;font-size:13px;color:#555;border-bottom:2px solid #eee}}
td{{padding:10px 14px;font-size:14px;border-bottom:1px solid #f0f0f0}}
tr:hover td{{background:#f8f9ff}}
a{{color:#2563eb;text-decoration:none}}
a:hover{{text-decoration:underline}}
.empty{{text-align:center;color:#888;margin-top:80px;font-size:16px}}
</style></head><body>
<div class="container">
<h1>📊 JobBot 投递看板</h1>
<p class="updated">最后更新：{datetime.now().strftime('%Y-%m-%d %H:%M')} | 总投递：{len(apps)}</p>
<div class="cards">
<div class="card"><div class="num" style="color:#22c55e">{stats['INTERVIEW_SCHEDULED']}</div><div class="label">🎉 已约面试</div></div>
<div class="card"><div class="num" style="color:#3b82f6">{stats['HR_REPLIED'] + stats['IN_CONVERSATION']}</div><div class="label">💬 HR 回复中</div></div>
<div class="card"><div class="num" style="color:#f59e0b">{stats['APPLIED']}</div><div class="label">📨 已投递待回复</div></div>
<div class="card"><div class="num" style="color:#ef4444">{stats['REJECTED']}</div><div class="label">❌ 被拒</div></div>
</div>
<div class="platform-tags">
{''.join(f'<span class="tag">📌 {p}: {n} 个</span>' for p, n in sorted(platforms.items()))}
</div>
{empty_body}
{table_section}
</div></body></html>"""
    return html

if __name__ == "__main__":
    data = load_data()
    html = generate(data)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ 看板已生成: {OUTPUT}")
    print(f"   总投递: {len(data.get('applications', {}))} 个")
