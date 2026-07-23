#!/usr/bin/env python3
"""JobBot 环境检测 + 自动安装 — python scripts/setup.py"""

import subprocess, sys, importlib.util, json
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
CONFIG_FILE = ROOT / "config" / "user_profile.json"
CONFIG_TEMPLATE = ROOT / "config" / "user_profile_template.json"

print("JobBot 环境检测\n" + "=" * 50)

ok_count = 0
total = 0

def step(name, fn):
    global ok_count, total; total += 1
    try:
        ok, msg = fn()
    except Exception as e:
        ok, msg = False, str(e)
    print(f"  {'✅' if ok else '❌'} {name}: {msg}")
    if ok: ok_count += 1

# Python
step("Python >= 3.10", lambda: (sys.version_info >= (3, 10), sys.version.split()[0]))

# Playwright pip
pw_spec = importlib.util.find_spec("playwright")
step("pip: playwright", lambda: (pw_spec is not None, "已安装" if pw_spec else "未安装"))

# Auto-install playwright if missing
if pw_spec is None:
    print("  → 正在安装 playwright (约30秒)...")
    r = subprocess.run([sys.executable, "-m", "pip", "install", "playwright"])
    ok = r.returncode == 0
    print(f"    {'✅' if ok else '❌'} playwright {'安装完成' if ok else '安装失败'}")
else:
    print("    ✅ playwright 已安装")

# Playwright Firefox browser
def check_firefox():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.firefox.launch().close()
            return True, "Firefox 已安装"
    except Exception as e:
        msg = str(e)
        if "doesn't exist" in msg:
            return False, "Firefox 未安装 — 正在自动安装..."
        return False, msg[:80]

step("Playwright Firefox", check_firefox)

# Auto-install Firefox
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        try: p.firefox.launch().close()
        except:
            print("  → 正在下载 Firefox 浏览器 (~116MB, CDN国内直连, 约3-10分钟, 请耐心等待)...")
            r = subprocess.run([sys.executable, "-m", "playwright", "install", "firefox"])
            ok = r.returncode == 0
            print(f"    {'✅' if ok else '❌'} Firefox {'安装完成' if ok else '安装失败，可手动运行: playwright install firefox'}")
except ImportError:
    pass

# Config
step("配置文件", lambda: (
    CONFIG_FILE.exists() or CONFIG_TEMPLATE.exists(),
    "就绪" if CONFIG_FILE.exists() else "模板就绪 (需重命名为 user_profile.json)"
))

# Data dir
step("数据目录", lambda: (True, str(DATA_DIR)))

print(f"\n{'=' * 50}")
print(f"结果: {ok_count}/{total} 项通过")

if ok_count == total:
    print("\n✅ 环境就绪！python dashboard.py 启动看板。")
else:
    print("\n⚠️ 部分项未通过，但 Dashboard 仍可启动。")
    print("  BOSS直聘需要手动登录一次后 Cookie 自动复用。")

sys.exit(0 if ok_count == total else 1)
