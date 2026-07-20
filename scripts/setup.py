#!/usr/bin/env python3
"""JobBot 环境检测脚本 — 检查依赖是否就绪"""

import sys
import subprocess
import importlib.util
import json
from pathlib import Path

CHECKS = []

def check(name, fn):
    try:
        ok, msg = fn()
    except Exception as e:
        ok, msg = False, str(e)
    CHECKS.append({"name": name, "ok": ok, "message": msg})
    status = "✅" if ok else "❌"
    print(f"  {status} {name}: {msg}")
    return ok

print("JobBot 环境检测\n" + "=" * 50)

# Python version
check("Python >= 3.10", lambda: (
    sys.version_info >= (3, 10),
    f"Python {sys.version}"
))

# pip packages
for pkg, import_name, desc in [
    ("playwright", "playwright", "Playwright 浏览器自动化"),
    ("httpx", "httpx", "HTTP 客户端"),
    ("jinja2", "jinja2", "HTML 模板引擎"),
]:
    spec = importlib.util.find_spec(import_name)
    check(f"pip: {pkg}", lambda s=spec, d=desc: (
        s is not None,
        d + (" (已安装)" if s else " (未安装 — pip install " + pkg + ")")
    ))

# Playwright browsers
def check_pw_browsers():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browsers = [b["name"] for b in p.chromium.browsers if "name" in b]
            if not browsers:
                return False, "未找到 Chromium 浏览器 (运行: playwright install chromium)"
            return True, f"已安装: {', '.join(browsers)}"
    except Exception as e:
        return False, str(e)

check("Playwright 浏览器", check_pw_browsers)

# Config files
ROOT = Path(__file__).parent.parent
for f, desc in [
    ("config/user_profile.json", "用户简历"),
    ("config/platforms.yml", "平台配置"),
]:
    path = ROOT / f
    if str(path).startswith("config/") and Path("config/user_profile_template.json").exists():
        check(desc, lambda p=ROOT/"config/user_profile_template.json": (
            p.exists(),
            "模板已就绪 (需重命名为 user_profile.json 并填写)"
        ))
        continue

# Summary
ok_count = sum(1 for c in CHECKS if c["ok"])
total = len(CHECKS)
print(f"\n{'=' * 50}")
print(f"结果: {ok_count}/{total} 项通过")

if ok_count < total:
    print("\n请先修复 ❌ 项再使用 JobBot:")
    for c in CHECKS:
        if not c["ok"]:
            print(f"  • {c['name']}: {c['message']}")
else:
    print("\n✅ 环境就绪！在 Hermes 中加载 SKILL.md 后说 '帮我找工作' 即可开始。")

sys.exit(0 if ok_count == total else 1)
