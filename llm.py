#!/usr/bin/env python3
"""内置 LLM 客户端 — OpenAI 兼容，用户填 api_key 即用。零第三方依赖（urllib）。

config/llm.json:
  {"base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat", "api_key": "sk-..."}
"""
import json
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).parent
LLM_CONFIG = ROOT / "config" / "llm.json"

DEFAULT_CONFIG = {
    "base_url": "https://api.deepseek.com/v1",
    "model": "deepseek-chat",
    "api_key": "",
}


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if LLM_CONFIG.exists():
        try:
            cfg.update(json.loads(LLM_CONFIG.read_text(encoding="utf-8")))
        except Exception:
            pass
    return cfg


def save_config(cfg: dict):
    LLM_CONFIG.parent.mkdir(exist_ok=True)
    LLM_CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def chat(messages: list[dict], temperature: float = 0.3, max_tokens: int = 2000) -> str:
    """OpenAI 兼容 chat completions 调用。返回 content 文本。"""
    cfg = load_config()
    if not cfg.get("api_key"):
        raise RuntimeError("未配置 API Key — 请先在 Dashboard 设置页填写")

    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    body = json.dumps({
        "model": cfg["model"],
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode("utf-8")

    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg['api_key']}",
    })
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")[:300]
        raise RuntimeError(f"LLM 调用失败 HTTP {e.code}: {detail}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"网络错误: {e.reason}")

    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        raise RuntimeError(f"LLM 返回异常: {json.dumps(data, ensure_ascii=False)[:300]}")


def chat_json(messages: list[dict], temperature: float = 0.2) -> dict:
    """LLM 返回 JSON 对象（自动剥 ```json 包裹）。"""
    text = chat(messages, temperature=temperature).strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise RuntimeError(f"LLM 返回非 JSON: {text[:200]}")
    return json.loads(text[start:end + 1])


def test_connection() -> str:
    """测试配置是否可用，返回模型响应。"""
    return chat([{"role": "user", "content": "回复 OK 两个字母即可"}])


if __name__ == "__main__":
    # 自检：python llm.py — 需要 config/llm.json 已配置
    try:
        print("LLM 测试:", test_connection()[:100])
    except Exception as e:
        print(f"❌ {e}")
        raise SystemExit(1)
