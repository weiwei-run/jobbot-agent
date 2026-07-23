#!/usr/bin/env python3
"""JobBot 环境检测 + 自动安装 — python scripts/setup.py
检测 Node.js / npm / Camofox，缺失自动安装。"""

import subprocess, sys, os
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

# Node.js
def check_node():
    try:
        r = subprocess.run(["node", "--version"], capture_output=True, text=True)
        v = r.stdout.strip().lstrip("v")
        major = int(v.split(".")[0])
        return major >= 16, v
    except FileNotFoundError:
        return False, "未安装 — 请从 https://nodejs.org 下载 LTS 版"

step("Node.js >= 16", check_node)

# npm
def check_npm():
    for cmd in ["npm", "npm.cmd"]:
        try:
            r = subprocess.run([cmd, "--version"], capture_output=True, text=True)
            if r.returncode == 0:
                return True, r.stdout.strip()
        except FileNotFoundError:
            continue
    return False, "未安装 (需 Node.js, 安装后重启终端)"

step("npm", check_npm)

# Camofox browser
def check_camoufox():
    try:
        r = subprocess.run(["npm", "list", "-g", "@askjo/camofox-browser", "--depth=0"],
                          capture_output=True, text=True)
        if "@askjo/camofox-browser" in r.stdout:
            return True, "已安装"
    except:
        pass

    # Auto-install
    print("  → 正在安装 Camofox 浏览器 (~150MB, npm registry, 约2-5分钟, 请耐心等待)...")
    r = subprocess.run(["npm", "install", "-g", "@askjo/camofox-browser"])
    ok = r.returncode == 0
    return ok, "安装完成" if ok else "安装失败，手动运行: npm install -g @askjo/camofox-browser"

step("Camofox 浏览器", check_camoufox)

# Camofox install dir
def check_camoufox_dir():
    home = os.environ.get("USERPROFILE", os.environ.get("HOME", ""))
    path = os.path.join(home, "AppData", "Local", "camoufox", "camoufox")
    if os.path.isdir(path):
        return True, path
    # try macOS/Linux
    for alt in [os.path.join(home, ".cache", "camoufox", "camoufox"),
                os.path.join(home, "Library", "Caches", "camoufox", "camoufox")]:
        if os.path.isdir(alt):
            return True, alt
    return False, f"未找到 (expected: {path})"

step("Camofox 浏览器引擎", check_camoufox_dir)

# Config
step("配置文件", lambda: (
    CONFIG_FILE.exists() or CONFIG_TEMPLATE.exists(),
    "就绪" if CONFIG_FILE.exists() else "模板就绪 (重命名为 user_profile.json)"
))

# Data dir
step("数据目录", lambda: (True, str(DATA_DIR)))

print(f"\n{'=' * 50}")
print(f"结果: {ok_count}/{total} 项通过")

if ok_count == total:
    print("\n✅ 环境就绪！python start.py 启动。")
else:
    print("\n⚠️ 部分项未通过，但 Dashboard 仍可启动。")
    print("  各平台首次使用需手动登录一次，Cookie 自动复用。")

sys.exit(0 if ok_count == total else 1)
