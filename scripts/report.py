#!/usr/bin/env python3
"""生成离线 Dashboard HTML，嵌入当前 applications.json 数据。"""

import json
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent.parent
DATA_FILE = ROOT / "data" / "applications.json"
OUTPUT = ROOT / "data" / "dashboard.html"

if not DATA_FILE.exists():
    print("❌ data/applications.json 不存在，先运行一次投递。")
    exit(1)

data = json.loads(DATA_FILE.read_text(encoding="utf-8", errors="ignore"))
apps = data.get("applications", [])
stats = data.get("stats", {})

# Count by platform
platforms = {}
for a in apps:
    p = a.get("platform", "unknown")
    platforms[p] = platforms.get(p, 0) + 1

# Count by status
status_counts = {}
for a in apps:
    s = a.get("status", "applied")
    status_counts[s] = status_counts.get(s, 0) + 1

badge_map = {
    "applied": ("badge-applied", "#d29922"),
    "hr_replied": ("badge-replied", "#58a6ff"),
    "interview_scheduled": ("badge-interview", "#3fb950"),
    "interviewing": ("badge-interview", "#3fb950"),
    "rejected": ("badge-rejected", "#f85149"),
}

rows = ""
for a in sorted(apps, key=lambda x: x.get("applied_at", ""), reverse=True):
    s = a.get("status", "applied")
    badge_class, _ = badge_map.get(s, ("badge-applied", "#d29922"))
    score = "⭐" * a.get("score", 0) or "—"
    url = a.get("url", "")
    pos = f'<a href="{url}" target="_blank">{a.get("position","—")}</a>' if url else a.get("position", "—")
    rows += f"""<tr><td>{a.get('company','—')}</td><td>{pos}</td><td>{a.get('platform','—')}</td>
      <td>{score}</td><td><span class="badge {badge_class}">{s}</span></td>
      <td>{(a.get('applied_at','')[:10])}</td></tr>"""

html = f"""<!DOCTYPE html>
<html lang="zh">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>JobBot 投递看板</title>
<style>
:root{{--bg:#0d1117;--fg:#e6edf3;--accent:#58a6ff;--good:#3fb950;--warn:#d29922;--err:#f85149;--card:#161b22;--border:#30363d}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font:14px/1.6 system-ui,sans-serif;background:var(--bg);color:var(--fg);padding:20px;max-width:1000px;margin:0 auto}}
h1{{font-size:22px;margin-bottom:4px}}.sub{{color:#8b949e;margin-bottom:20px;font-size:13px}}
.grid4{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:24px}}
.stat-card{{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:14px;text-align:center}}
.stat-card .num{{font-size:28px;font-weight:700}}.stat-card .lbl{{font-size:12px;color:#8b949e;margin-top:2px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{text-align:left;padding:8px 10px;color:#8b949e;border-bottom:1px solid var(--border)}}
td{{padding:8px 10px;border-bottom:1px solid var(--border)}}
tr:hover td{{background:rgba(88,166,255,.05)}}
a{{color:var(--accent);text-decoration:none}}a:hover{{text-decoration:underline}}
.badge{{padding:2px 8px;border-radius:10px;font-size:11px;white-space:nowrap}}
.badge-applied{{background:#2a1f0a;color:var(--warn)}}.badge-replied{{background:#0a1f2a;color:var(--accent)}}
.badge-interview{{background:#0a2a1a;color:var(--good)}}.badge-rejected{{background:#2a0a0a;color:var(--err)}}
</style></head><body>
<h1>📊 JobBot 投递看板</h1>
<p class=sub>最后更新：{datetime.now().strftime('%Y-%m-%d %H:%M')} | 总投递：{len(apps)}</p>
<div class=grid4>
<div class=stat-card><div class=num style=color:var(--accent)>{stats.get('total_applied',0)}</div><div class=lbl>总投递</div></div>
<div class=stat-card><div class=num style=color:var(--good)>{stats.get('hr_replied',0)}</div><div class=lbl>HR回复</div></div>
<div class=stat-card><div class=num style=color:var(--warn)>{stats.get('interview_scheduled',0)}</div><div class=lbl>约面试</div></div>
<div class=stat-card><div class=num style=color:var(--err)>{stats.get('rejected',0)}</div><div class=lbl>已拒绝</div></div>
</div>
<table><thead><tr><th>公司</th><th>岗位</th><th>平台</th><th>匹配</th><th>状态</th><th>时间</th></tr></thead>
<tbody>{rows}</tbody></table>
<p style=text-align:center;color:#8b949e;margin-top:24px;font-size:12px>python dashboard.py 启动实时看板</p>
</body></html>"""

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(html, encoding="utf-8", errors="ignore")
print(f"✅ 看板已生成: {OUTPUT}")
print(f"   投递: {len(apps)} | 回复: {stats.get('hr_replied',0)} | 面试: {stats.get('interview_scheduled',0)}")
