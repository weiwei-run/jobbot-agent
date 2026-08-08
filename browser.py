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
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

CAMOFOX_PORT = 9377
BASE = f"http://localhost:{CAMOFOX_PORT}"
USER_ID = "jobbot"

# 启动互斥：避免并发调用 ensure_camofox 拉起多个服务/浏览器进程
_CAMOFOX_START_LOCK = threading.Lock()
# JobBot 自己启动的 Camofox server 进程（用于退出时只停自己启动的）
_CAMOFOX_PROC = None
# 各平台已打开的登录页标签（供登录检测复用，避免新建重复页面）
_LOGIN_TABS: dict[str, str] = {}

_BOSS_LOGIN_STATE_JS = r"""
(() => {
  const text = document.body.innerText;
  if (text.includes('验证码登录') || text.includes('APP扫码登录')) return 'logged_out';
  // 可见的「登录/注册」按钮（排除 is-login 这类状态类容器）
  const btns = Array.from(document.querySelectorAll('a,button,[class*=btn],[class*=Btn]')).filter(e =>
    e.offsetParent !== null && e.offsetWidth > 0 && e.offsetHeight > 0 &&
    /^\s*(登录|注册|立即登录|登录\/注册)\s*$/.test((e.innerText || '').trim())
  );
  if (btns.length > 0) return 'logged_out';
  const userMark = !!document.querySelector(
      '.header-user, [class*=avatar], [class*=Avatar], [class*=user-info], [class*=userInfo], .user-name, .username')
    || text.includes('退出登录') || text.includes('账号设置');
  if (userMark) return 'logged_in';
  return 'unknown';
})()
"""

_SXS_LOGIN_STATE_JS = r"""
(() => {
  const wall = Array.from(document.querySelectorAll('.outer-auth, [class*=auth], [class*=Auth]'))
    .some(e => e.offsetParent !== null && e.offsetWidth > 0 && e.offsetHeight > 0);
  if (wall) return 'logged_out';
  const userEl = Array.from(document.querySelectorAll(
      '[class*=header] [class*=avatar], [class*=Avatar], [class*=user], [class*=User]'))
    .find(e => e.offsetParent !== null && e.offsetWidth > 0 && e.offsetHeight > 0);
  if (userEl) return 'logged_in';
  return 'unknown';
})()
"""

_WUYOU_LOGIN_STATE_JS = r"""
(() => {
  const text = document.body.innerText;
  const url = location.href;
  if (url.includes('/login') || url.includes('passport') || url.includes('sso.')) return 'logged_out';
  // 登录态标志：可见的用户名/头像、「编辑简历」「在线简历」等
  const userInfo = Array.from(document.querySelectorAll(
      '.user-info, [class*=user-info], [class*=UserInfo], .username, [class*=member_userinfo]'))
    .find(e => e.offsetParent !== null && e.offsetWidth > 0 && (e.innerText || '').trim().length > 0);
  if (userInfo || text.includes('编辑简历') || text.includes('在线简历')) return 'logged_in';
  // 未登录：登录页/验证码/登录框
  const wall = text.includes('验证码登录')
    || !!document.querySelector('.login-box, [class*=login-form], [class*=loginForm], [class*=QRcode], [class*=qr-code]');
  if (wall) return 'logged_out';
  return 'unknown';
})()
"""


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


def _port_pid(port: int) -> int | None:
    """查找监听指定端口的进程 PID（跨平台尽力而为）。"""
    try:
        if platform.system() == "Windows":
            out = subprocess.run(["netstat", "-ano"], capture_output=True,
                                 text=True).stdout
            for line in out.splitlines():
                parts = line.split()
                if (len(parts) >= 5 and parts[0] == "TCP"
                        and parts[1].endswith(f":{port}")
                        and "LISTENING" in line.upper()):
                    return int(parts[-1])
        else:
            out = subprocess.run(["lsof", "-ti", f"tcp:{port}"],
                                 capture_output=True, text=True).stdout.strip()
            if out:
                return int(out.splitlines()[0])
    except Exception:
        return None
    return None


def _kill_port_owner(port: int):
    """强制结束占用端口的进程（仅用于启动前清理残留服务）。"""
    pid = _port_pid(port)
    if not pid:
        return
    try:
        if platform.system() == "Windows":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           capture_output=True)
        else:
            os.kill(pid, 9)
    except Exception:
        pass


def ensure_camofox() -> dict:
    """确保 Camofox 服务在运行；未安装则给出安装指引。"""
    global _CAMOFOX_PROC
    if camofox_available():
        return {"ok": True, "message": "Camofox 已运行"}

    with _CAMOFOX_START_LOCK:
        # 等待期间可能已被其他调用启动
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
        # 清理残留服务（占着端口但不可用的 node 进程）与残留浏览器进程
        _kill_port_owner(CAMOFOX_PORT)
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
            proc = subprocess.Popen(
                ["node", str(server_js)],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
            _CAMOFOX_PROC = proc
        except Exception as e:
            return {"ok": False, "message": f"Camofox 启动失败: {e}"}

        # 等待就绪（最多 20 秒）
        for _ in range(40):
            time.sleep(0.5)
            if camofox_available():
                return {"ok": True, "message": "Camofox 已启动"}
        return {"ok": False, "message": "Camofox 启动超时，请手动启动 server.js 后重试"}


def stop_camofox() -> dict:
    """停掉 JobBot 自己启动的 Camofox 服务；外部运行的实例不动。"""
    global _CAMOFOX_PROC
    proc = _CAMOFOX_PROC
    if proc is None:
        return {"ok": True, "message": "Camofox 非 JobBot 启动，无需停止"}
    _CAMOFOX_PROC = None
    # 优先优雅停止（未配置 admin key 时可能 403，忽略）
    try:
        _request("POST", "/stop", {}, timeout=5)
        time.sleep(1)
    except Exception:
        pass
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    # 清理残留浏览器进程
    try:
        if platform.system() == "Windows":
            subprocess.run(["taskkill", "/F", "/IM", "camoufox.exe"],
                           capture_output=True)
        else:
            subprocess.run(["pkill", "-f", "camoufox"], capture_output=True)
    except Exception:
        pass
    return {"ok": True, "message": "已停止 JobBot 启动的 Camofox"}


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
        _request("DELETE", f"/tabs/{tab_id}?userId={USER_ID}")
    except Exception:
        pass


def open_page_text(url: str, timeout: int = 15, markers: list[str] | None = None) -> dict:
    """打开页面并等待正文加载，返回 {ok, text, login, message}。用于岗位详情核实。

    markers: 命中任一标记即认为页面就绪并立即返回（用于快速识别「已下线/审核中」等状态页）。
    """
    ensured = ensure_camofox()
    if not ensured["ok"]:
        return {"ok": False, "text": "", "login": False,
                "message": ensured.get("message", "Camofox 不可用")}
    tab = create_tab(url)
    if not tab:
        return {"ok": False, "text": "", "login": False, "message": "创建标签页失败"}
    try:
        deadline = time.time() + timeout
        last_text = ""
        prev_text = ""
        stable = 0
        while time.time() < deadline:
            try:
                cur = evaluate(tab, "location.href") or ""
            except Exception:
                cur = ""
            if "login" in cur.lower() or "passport" in cur.lower():
                return {"ok": False, "text": "", "login": True,
                        "message": "详情页跳转登录页"}
            try:
                text = evaluate(tab, "document.body.innerText") or ""
            except Exception:
                text = ""
            if text:
                last_text = text
                if "验证码登录" in text or "APP扫码登录" in text:
                    return {"ok": False, "text": "", "login": True,
                            "message": "详情页出现登录墙"}
                if markers and any(m in text for m in markers):
                    return {"ok": True, "text": text, "login": False, "message": ""}
                if len(text) > 200:
                    # SPA 内容可能后渲染：连续两轮文本相同才认为加载完成
                    if text == prev_text:
                        stable += 1
                        if stable >= 2:
                            return {"ok": True, "text": text, "login": False, "message": ""}
                    else:
                        stable = 0
                    prev_text = text
            time.sleep(1)
        if last_text:
            return {"ok": True, "text": last_text, "login": False, "message": ""}
        return {"ok": False, "text": "", "login": False, "message": "等待页面内容超时"}
    except Exception as e:
        return {"ok": False, "text": "", "login": False, "message": str(e)[:200]}
    finally:
        close_tab(tab)


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
    tab = _LOGIN_TABS.get(platform)
    created = False
    if not tab:
        tab = create_tab(base)
        created = True
    try:
        time.sleep(5 if created else 1.5)
        url = evaluate(tab, "location.href")
        url = url or ""
        if "login" in url.lower() or "passport" in url.lower():
            return {"ok": False, "url": url, "message": "未登录，请打开登录页完成登录"}
        if platform == "boss_zhipin":
            state = (evaluate(tab, _BOSS_LOGIN_STATE_JS) or "").strip()
            if state == "logged_out":
                return {"ok": False, "url": url, "message": "未登录，请打开登录页完成登录"}
            if state == "logged_in":
                return {"ok": True, "url": url, "message": "已登录"}
            # unknown：无登录墙也无登录按钮，按已登录继续（后续搜索/投递会再次校验）
            return {"ok": True, "url": url, "message": "未检测到登录拦截，按已登录处理"}
        if platform == "wuyou":
            state = (evaluate(tab, _WUYOU_LOGIN_STATE_JS) or "").strip()
            if state == "logged_out":
                return {"ok": False, "url": url, "message": "未登录，请打开登录页完成登录"}
            if state == "logged_in":
                return {"ok": True, "url": url, "message": "已登录"}
            return {"ok": True, "url": url, "message": "未检测到登录拦截，按已登录处理"}
        if platform == "shixiseng":
            state = (evaluate(tab, _SXS_LOGIN_STATE_JS) or "").strip()
            if state == "logged_out":
                return {"ok": False, "url": url, "message": "未登录，请打开登录页完成登录"}
            if state == "logged_in":
                return {"ok": True, "url": url, "message": "已登录"}
            return {"ok": True, "url": url, "message": "未检测到登录拦截，按已登录处理"}
        return {"ok": True, "url": url, "message": "已登录"}
    finally:
        if created:
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
    # 若该平台已有登录页标签，先关掉再开新的，避免重复页面
    old = _LOGIN_TABS.get(platform)
    if old:
        close_tab(old)
    tab = create_tab(pcfg.get("login_url", pcfg.get("base_url", "")))
    _LOGIN_TABS[platform] = tab
    return {"ok": True, "tab": tab,
            "message": "已打开登录页，登录完成后将自动检测并提示"}
