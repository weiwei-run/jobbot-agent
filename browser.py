#!/usr/bin/env python3
"""Camofox 浏览器客户端 — 驱动三大平台的搜索与自动投递。

Camofox 是 Firefox 内核的反检测浏览器，通过本地 REST API（端口 9377）操作。
本模块负责：检测/启动 Camofox 服务、创建标签页、导航、执行 JS、点击、验证。
"""
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

CAMOFOX_PORT = 9377
BASE = f"http://localhost:{CAMOFOX_PORT}"
USER_ID = "jobbot"


def js_bool(v) -> bool:
    """Camofox evaluate 返回的 JS 布尔是字符串 'true'/'false'，统一转成 Python bool。"""
    return str(v or "").strip().lower() in ("true", "1")


def _request(method: str, path: str, body: dict | None = None, timeout: int = 45) -> dict:
    url = BASE + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"Camofox HTTP {e.code}: {detail}") from e
    return json.loads(raw) if raw.strip() else {}


def camofox_available() -> bool:
    """检测 Camofox HTTP 服务是否在运行。"""
    try:
        _request("GET", "/tabs", timeout=3)
        return True
    except urllib.error.HTTPError:
        # 服务在运行但该路径报错也算可达
        return True
    except Exception:
        return False


def _node_server_js() -> Path | None:
    """定位 camofox-browser 的 server.js。"""
    candidates = []
    ap = os.environ.get("APPDATA")
    if ap:
        candidates.append(Path(ap) / "npm" / "node_modules" / "@askjo" / "camofox-browser" / "server.js")
    npm_cmd = "npm.cmd" if platform.system() == "Windows" else "npm"
    try:
        npm_root = subprocess.run([npm_cmd, "root", "-g"], capture_output=True,
                                  text=True).stdout.strip()
    except Exception:
        npm_root = ""
    if npm_root:
        candidates.append(Path(npm_root) / "@askjo" / "camofox-browser" / "server.js")
    for c in candidates:
        if c.exists():
            return c
    return None


def _camoufox_install_dir() -> str | None:
    """定位 Camofox 浏览器引擎目录（与 setup.py 一致）。"""
    home = os.environ.get("USERPROFILE", os.environ.get("HOME", ""))
    roots = [
        Path(home) / "AppData" / "Local" / "camoufox" / "camoufox",
        Path(home) / ".cache" / "camoufox" / "camoufox",
        Path(home) / "Library" / "Caches" / "camoufox" / "camoufox",
    ]
    for r in roots:
        if r.is_dir():
            return str(r)
    return None


def ensure_camofox() -> dict:
    """确保 Camofox 服务在运行；未安装则给出安装指引。"""
    if camofox_available():
        return {"ok": True, "message": "Camofox 已运行"}

    server_js = _node_server_js()
    if server_js is None:
        return {"ok": False, "need_install": True,
                "message": "未安装 Camofox。请先运行：npm install -g @askjo/camofox-browser（约150MB）"}
    install_dir = _camoufox_install_dir()
    if install_dir is None:
        return {"ok": False, "need_install": True,
                "message": "Camofox 浏览器引擎缺失，请运行 python scripts/setup.py 修复"}

    env = dict(os.environ)
    env["CAMOUFOX_INSTALL_DIR"] = install_dir
    try:
        if platform.system() == "Windows":
            subprocess.run(["taskkill", "/F", "/IM", "camoufox.exe"],
                           capture_output=True)
        else:
            subprocess.run(["pkill", "-f", "camoufox"], capture_output=True)
    except Exception:
        pass

    try:
        creationflags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
        subprocess.Popen(
            ["node", str(server_js)],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
    except Exception as e:
        return {"ok": False, "message": f"Camofox 启动失败: {e}"}

    # 等待就绪（最多 20 秒）
    for _ in range(40):
        time.sleep(0.5)
        if camofox_available():
            return {"ok": True, "message": "Camofox 已启动"}
    return {"ok": False, "message": "Camofox 启动超时，请手动启动 server.js 后重试"}


def create_tab(url: str, session_key: str = "default") -> str:
    r = _request("POST", "/tabs",
                 {"userId": USER_ID, "sessionKey": session_key, "url": url})
    return r.get("tabId") or r.get("id") or ""


def navigate(tab_id: str, url: str):
    _request("POST", f"/tabs/{tab_id}/navigate", {"userId": USER_ID, "url": url})


def evaluate(tab_id: str, expression: str, timeout: int = 45) -> str:
    r = _request("POST", f"/tabs/{tab_id}/evaluate",
                 {"userId": USER_ID, "expression": expression}, timeout=timeout)
    return r.get("result", "")


def snapshot(tab_id: str) -> dict:
    r = _request("GET", f"/tabs/{tab_id}/snapshot?userId={USER_ID}")
    return r


def close_tab(tab_id: str):
    try:
        _request("DELETE", f"/tabs/{tab_id}")
    except Exception:
        pass


def wait_js(tab_id: str, expression: str, timeout: int = 30) -> str:
    """轮询执行 JS 直到返回真值，返回最后一次结果。"""
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        try:
            last = evaluate(tab_id, expression)
        except Exception:
            last = ""
        if last and last not in ("false", "null", "undefined", "0", "[]"):
            return last
        time.sleep(1.5)
    return last


def check_login(platform: str) -> dict:
    """导航到平台首页，检测登录状态。返回 {ok(已登录), message, url}。"""
    from engine import load_platforms
    pcfg = load_platforms().get(platform)
    if not pcfg:
        return {"ok": False, "message": f"未知平台 {platform}"}
    ensured = ensure_camofox()
    if not ensured["ok"]:
        return ensured
    base = pcfg.get("base_url", "")
    tab = create_tab(base)
    try:
        time.sleep(5)
        url = evaluate(tab, "location.href")
        url = url or ""
        if "login" in url.lower() or "passport" in url.lower():
            return {"ok": False, "url": url, "message": "未登录，请打开登录页完成登录"}
        if platform == "boss_zhipin":
            has_login_btn = evaluate(tab, "!!document.querySelector('.login-btn, [class*=login], [class*=Login]')")
            if js_bool(has_login_btn):
                return {"ok": False, "url": url, "message": "未登录，请打开登录页完成登录"}
        if platform == "wuyou":
            logged_in_mark = evaluate(tab,
                "document.body.innerText.includes('退出') || document.body.innerText.includes('我的简历')")
            if not js_bool(logged_in_mark):
                return {"ok": False, "url": url, "message": "未检测到登录状态（未看到「退出/我的简历」）"}
        if platform == "shixiseng":
            logged_in_mark = evaluate(tab,
                "!!document.querySelector('.header-user, [class*=user] [class*=avatar], [class*=User]')")
            if not js_bool(logged_in_mark):
                return {"ok": False, "url": url, "message": "未检测到登录状态，请先登录"}
        return {"ok": True, "url": url, "message": "已登录"}
    finally:
        close_tab(tab)


def open_login(platform: str) -> dict:
    """在 Camofox 中打开平台登录页，供用户手动登录。"""
    from engine import load_platforms
    pcfg = load_platforms().get(platform)
    if not pcfg:
        return {"ok": False, "message": f"未知平台 {platform}"}
    ensured = ensure_camofox()
    if not ensured["ok"]:
        return ensured
    tab = create_tab(pcfg.get("login_url", pcfg.get("base_url", "")))
    return {"ok": True, "tab": tab,
            "message": "已打开登录页，请手动完成登录后回来点「已登录，继续」"}
