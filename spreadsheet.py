#!/usr/bin/env python3
"""在线表格同步 — 投递记录自动推送到在线表格。

支持两种方式（config/settings.json 中配置）：
1. webhook：POST JSON 到任意 webhook 地址（可对接 Zapier / Make / 自建服务等）
2. feishu：飞书多维表格（Bitable）API，需要 app_id/app_secret/多维表格 app_token/数据表 table_id

飞书申请方式：https://open.feishu.cn 创建企业自建应用 → 开通「多维表格」权限 →
在目标多维表格中复制 app_token 和 table_id。
"""
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
SETTINGS_FILE = ROOT / "config" / "settings.json"

DEFAULT_SETTINGS = {
    "spreadsheet": {
        "enabled": False,
        "type": "webhook",          # webhook | feishu | none
        "webhook_url": "",
        "feishu": {
            "app_id": "",
            "app_secret": "",
            "app_token": "",
            "table_id": "",
        },
    }
}


def load_settings() -> dict:
    cfg = json.loads(json.dumps(DEFAULT_SETTINGS))
    if SETTINGS_FILE.exists():
        try:
            stored = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            cfg["spreadsheet"].update(stored.get("spreadsheet", {}))
            if stored.get("spreadsheet", {}).get("feishu"):
                cfg["spreadsheet"]["feishu"].update(stored["spreadsheet"]["feishu"])
        except Exception:
            pass
    return cfg


def save_settings(settings: dict) -> None:
    SETTINGS_FILE.parent.mkdir(exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2),
                             encoding="utf-8")


def _public(settings: dict) -> dict:
    """返回给前端的配置（隐藏密钥）。"""
    s = settings["spreadsheet"]
    return {
        "enabled": bool(s.get("enabled")),
        "type": s.get("type", "webhook"),
        "webhook_url": s.get("webhook_url", ""),
        "feishu": {
            "app_id": s["feishu"].get("app_id", ""),
            "app_token": s["feishu"].get("app_token", ""),
            "table_id": s["feishu"].get("table_id", ""),
            "has_secret": bool(s["feishu"].get("app_secret")),
        },
    }


def row_of(rec: dict) -> dict:
    """把一条投递记录转成表格行（同一 schema 供 webhook / 飞书使用）。"""
    return {
        "company": rec.get("company", ""),
        "position": rec.get("position", ""),
        "platform": rec.get("platform", ""),
        "salary": rec.get("salary", ""),
        "location": rec.get("location", ""),
        "score": rec.get("score", ""),
        "status": rec.get("status", ""),
        "applied_at": rec.get("applied_at", ""),
        "url": rec.get("url", ""),
        "contact": rec.get("hr_name") or rec.get("contact_person") or "",
        "notes": rec.get("notes", ""),
    }


def _post_json(url: str, payload: dict, timeout: int = 30) -> tuple[int, str]:
    req = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8", errors="replace")[:500]


def _feishu_token(app_id: str, app_secret: str) -> str:
    body = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode("utf-8")
    req = urllib.request.Request(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        data=body, headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode("utf-8"))
    if data.get("code") != 0:
        raise RuntimeError(f"飞书鉴权失败: {data.get('msg')}")
    return data["tenant_access_token"]


def _feishu_sync(records: list[dict], feishu: dict) -> tuple[int, str]:
    if not (feishu.get("app_id") and feishu.get("app_secret")):
        raise RuntimeError("飞书未配置 app_id / app_secret")
    if not (feishu.get("app_token") and feishu.get("table_id")):
        raise RuntimeError("飞书未配置多维表格 app_token / table_id")
    token = _feishu_token(feishu["app_id"], feishu["app_secret"])
    fields = [{"fields": row_of(r)} for r in records]
    body = json.dumps({"records": fields}).encode("utf-8")
    url = (f"https://open.feishu.cn/open-apis/bitable/v1/apps/{feishu['app_token']}"
           f"/tables/{feishu['table_id']}/records/batch_create")
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {token}",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode("utf-8"))
    if data.get("code") != 0:
        raise RuntimeError(f"飞书写入失败: {data.get('msg')}")
    return len(fields), "ok"


def sync_records(records: list[dict]) -> dict:
    """同步全部记录到在线表格。返回 {ok, message, pushed}。"""
    settings = load_settings()
    s = settings["spreadsheet"]
    if not s.get("enabled"):
        return {"ok": True, "message": "在线表格同步未开启", "pushed": 0}
    stype = s.get("type", "webhook")
    try:
        if stype == "webhook":
            if not s.get("webhook_url"):
                raise RuntimeError("webhook 地址未配置")
            rows = [row_of(r) for r in records]
            status, body = _post_json(s["webhook_url"],
                                      {"records": rows, "count": len(rows)})
            if status >= 400:
                raise RuntimeError(f"webhook 返回 HTTP {status}: {body}")
            return {"ok": True, "message": f"已推送 {len(rows)} 条到 webhook", "pushed": len(rows)}
        if stype == "feishu":
            pushed, _ = _feishu_sync(records, s.get("feishu", {}))
            return {"ok": True, "message": f"已写入飞书多维表格 {pushed} 条", "pushed": pushed}
        return {"ok": True, "message": "未知同步类型", "pushed": 0}
    except Exception as e:
        return {"ok": False, "message": str(e), "pushed": 0}


def sync_async(records: list[dict]):
    """后台线程同步，不阻塞投递流程。"""
    def _run():
        try:
            sync_records(records)
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()


def test_sync() -> dict:
    """测试配置：推送一条测试记录。"""
    test_rec = {
        "company": "JobBot 测试",
        "position": "连接测试",
        "platform": "测试",
        "salary": "",
        "location": "",
        "score": "",
        "status": "test",
        "applied_at": "",
        "url": "",
        "contact": "",
        "notes": "这是一条 JobBot 同步测试记录",
    }
    settings = load_settings()
    s = settings["spreadsheet"]
    try:
        if s.get("type") == "webhook":
            status, body = _post_json(s["webhook_url"],
                                      {"records": [test_rec], "count": 1, "test": True})
            if status >= 400:
                raise RuntimeError(f"webhook 返回 HTTP {status}: {body}")
            return {"ok": True, "message": "webhook 测试成功"}
        if s.get("type") == "feishu":
            pushed, _ = _feishu_sync([test_rec], s.get("feishu", {}))
            return {"ok": True, "message": f"飞书测试成功，写入 {pushed} 条"}
        return {"ok": False, "message": "请先选择同步方式"}
    except Exception as e:
        return {"ok": False, "message": str(e)}


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(_public(load_settings()), ensure_ascii=False, indent=2))
