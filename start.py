#!/usr/bin/env python3
"""JobBot 一键启动 — python start.py → http://localhost:9379

纯 Python 即可启动 Dashboard + 51job 搜索；
BOSS直聘/实习僧搜索与三大平台自动投递需要 Camofox 浏览器（首次运行按提示安装）。
"""
import socket
import subprocess
import sys
import webbrowser
import time
from pathlib import Path

ROOT = Path(__file__).parent
PORT = 9379


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def main():
    print("🤖 JobBot 启动中...\n")

    print("[1/3] 环境检查...")
    ok_py = sys.version_info >= (3, 10)
    print(f"  {'✅' if ok_py else '❌'} Python {sys.version.split()[0]} (需 3.10+)")
    if not ok_py:
        print("  ⚠️ 请安装 Python 3.10+：https://python.org")
        sys.exit(1)

    if port_in_use(PORT):
        print(f"  ⚠️ 端口 {PORT} 已被占用（JobBot 可能已在运行），直接打开看板。")
    else:
        print(f"  ✅ 端口 {PORT} 空闲")

    print("[2/3] 启动 Dashboard...")
    if not port_in_use(PORT):
        dash = subprocess.Popen(
            [sys.executable, str(ROOT / "dashboard.py")],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(1.5)
    else:
        dash = None

    print("[3/3] 打开浏览器...")
    webbrowser.open(f"http://localhost:{PORT}")

    print(f"""
✅ JobBot 已启动！ 👉 http://localhost:{PORT}

   三步开始使用：
   ① 配置 AI：填 LLM API Key（支持 DeepSeek/Kimi/通义等 OpenAI 兼容接口）
   ② 上传简历 / 填写求职意向（城市、岗位、技能）
   ③ 点击「开始搜索」→ AI 生成关键词、三平台搜索精排推荐 → 点岗位链接自行投递，或「加入记录」本地跟进

   - 51job 搜索无需浏览器；BOSS直聘/实习僧搜索需 Camofox（看板内有检测与登录引导）
   - 遇到未登录会自动停在登录页并在看板提示手动登录，登录前不会投递
   - 数据全本地，按 Ctrl+C 停止服务
""")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        if dash:
            dash.terminate()
        try:
            import browser
            browser.stop_camofox()
        except Exception:
            pass
        print("\n👋 JobBot 已停止")


if __name__ == "__main__":
    main()
