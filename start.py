#!/usr/bin/env python3
"""JobBot 一键启动 — python start.py
检测环境 → 启动 Dashboard → 打开浏览器"""

import subprocess, sys, webbrowser, time
from pathlib import Path

ROOT = Path(__file__).parent

def run(cmd, **kw):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, **kw)

print("🤖 JobBot Agent 启动中...\n")

# 1. Environment check
print("[1/3] 环境检测...")
setup = run(f'"{sys.executable}" "{ROOT}/scripts/setup.py"')
if setup.returncode != 0:
    print("⚠️ 部分依赖缺失，Dashboard 仍可启动。BOSS直聘需手动登录。")
    print(f"   详情: python scripts/setup.py\n")

# 2. Start dashboard in background
print("[2/3] 启动 Dashboard...")
dash = subprocess.Popen(
    [sys.executable, str(ROOT / "dashboard.py")],
    stdout=subprocess.PIPE, stderr=subprocess.PIPE
)
time.sleep(1.5)

# 3. Open browser
print("[3/3] 打开浏览器...")
webbrowser.open("http://localhost:9379")

print(f"""
✅ JobBot Dashboard 已启动！
   👉 http://localhost:9379

   - 填写意向描述 → 保存配置
   - 在 Agent 中说「帮我找工作」开始投递
   - 投递记录自动显示在此页面

   按 Ctrl+C 停止服务
""")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    dash.terminate()
    print("\n👋 JobBot 已停止")
