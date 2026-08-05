#!/usr/bin/env python3
"""JobBot 引擎 — 关键词生成 → 三平台搜索 → LLM 评分 → 自动投递 → 记录与看板。

用户只需在 Dashboard 配置 LLM API Key：
- 51job：纯 HTTP API 搜索，被 WAF 拦截自动降级 Chrome headless
- BOSS直聘 / 实习僧：Camofox 浏览器驱动，首次需手动登录
- 自动投递：Camofox 点击 + 成功后验证，失败返回明确原因
- 记录：data/applications.json（唯一数据源）+ 在线表格同步
"""
import json
import re
import threading
import time
import urllib.parse
import uuid
from datetime import datetime
from pathlib import Path

from llm import chat_json
from platforms import LoginRequired, apply_filters, mark_risk

ROOT = Path(__file__).parent
DATA_FILE = ROOT / "data" / "applications.json"
PLATFORMS_FILE = ROOT / "config" / "platforms.yml"

# 会话内登录状态缓存（平台 key → bool）。False/缺失 = 需要重新检测。
_LOGIN_CACHE: dict[str, bool] = {}

# 51job 城市代码
CITY_CODES = {
    "南京": "070200", "北京": "010000", "上海": "020000", "广州": "030200",
    "深圳": "040000", "杭州": "080200", "成都": "090200", "武汉": "180200",
    "苏州": "070500", "西安": "200200", "长沙": "190200", "天津": "050000",
    "重庆": "060000", "郑州": "150200", "合肥": "110200", "无锡": "070400",
    "宁波": "081000", "青岛": "120200", "厦门": "100300", "佛山": "030800",
}

# 学历硬指标等级（数值越大要求越高）
DEGREE_RANK = {"高中": 0, "中专": 0, "大专": 1, "本科": 2, "硕士": 3, "博士": 4}


# ── 轻量 YAML 解析（只支持本项目 platforms.yml 用到的子集）──

def _parse_yml(text: str) -> dict:
    """解析简单 YAML：嵌套 map / 列表 / 标量 / 注释。"""
    root: dict = {}
    stack: list[tuple[int, dict]] = [(-1, root)]

    def current() -> dict:
        return stack[-1][1]

    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        content = line.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        if content.startswith("- "):
            value = _yml_scalar(content[2:].strip())
            lst = current().setdefault("__list__", [])
            if not isinstance(lst, list):
                lst = []
            lst.append(value)
            stack.append((indent, {"__list__": lst}))
            continue
        if ":" in content:
            key, _, val = content.partition(":")
            key = key.strip().strip('"').strip("'")
            val = val.strip()
            if val:
                current()[key] = _yml_scalar(val)
            else:
                nxt: dict = {}
                current()[key] = nxt
                stack.append((indent, nxt))
    return _unfold(root)


def _yml_scalar(s: str):
    if s == "" or s.lower() in ("null", "~"):
        return None
    if s == "[]":
        return []
    if s == "{}":
        return {}
    if s.lower() == "true":
        return True
    if s.lower() == "false":
        return False
    if s.startswith(('"', "'")) and s.endswith(s[0]):
        return s[1:-1]
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if re.fullmatch(r"-?\d+\.\d+", s):
        return float(s)
    return s


def _unfold(node):
    if isinstance(node, dict):
        if set(node.keys()) == {"__list__"}:
            return node["__list__"]
        return {k: _unfold(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_unfold(v) for v in node]
    return node


def load_platforms() -> dict:
    if not PLATFORMS_FILE.exists():
        return {}
    try:
        return _parse_yml(PLATFORMS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def enabled_platforms() -> dict:
    return {k: v for k, v in load_platforms().items()
            if isinstance(v, dict) and v.get("enabled", False)}


def get_login_states() -> dict:
    return dict(_LOGIN_CACHE)


def mark_login(platform_key: str, ok: bool):
    """更新平台登录状态缓存。"""
    _LOGIN_CACHE[platform_key] = bool(ok)


def _p(progress: dict | None, step: str, detail: str = ""):
    if progress is not None:
        progress["step"] = step
        progress["detail"] = detail


def _user_profile(intent: str) -> dict:
    """从意向描述提取用户硬指标（学历/工作年限）。"""
    p: dict = {}
    m = re.search(r"学历[:：]\s*(大专|本科|硕士|博士|中专|高中|研究生)", intent)
    if m:
        p["education"] = "硕士" if m.group(1) == "研究生" else m.group(1)
    m = re.search(r"(\d+)\s*年(?:以上)?(?:工作|实操|相关)?经验", intent)
    if m:
        p["work_years"] = int(m.group(1))
    if re.search(r"应届|在校生|无经验", intent):
        p.setdefault("work_years", 0)
    return p


def _jd_required_degree(jd: str) -> int:
    """JD 要求的最低学历等级，0 = 不限/无明确要求。"""
    if re.search(r"学历\s*(不限|无要求)", jd):
        return 0
    m = re.search(r"(?:学历|要求)[:：]?\s*(博士|硕士|本科|大专|中专|高中)", jd)
    if m:
        return DEGREE_RANK[m.group(1)]
    m = re.search(r"(统招|全日制)?\s*(博士|硕士|本科|大专|中专|高中)[及以]?上?", jd)
    if m:
        return DEGREE_RANK[m.group(2)]
    return 0


def _jd_required_years(jd: str) -> int:
    """JD 要求的最低工作年限，0 = 不限。"""
    if re.search(r"经验\s*(不限|无要求)", jd):
        return 0
    m = re.search(r"(\d+)\s*年(?:及|以)?上", jd)
    if m:
        return int(m.group(1))
    m = re.search(r"工作\s*(\d+)\s*年", jd)
    if m:
        return int(m.group(1))
    return 0


def _hard_filter(job: dict, profile: dict, city: str) -> bool:
    """硬指标过滤：学历/年限/地域不满足直接剔除（不看 LLM 评分）。"""
    jd = job.get("jd_summary") or ""
    edu = profile.get("education")
    if edu and edu in DEGREE_RANK:
        if _jd_required_degree(jd) > DEGREE_RANK[edu]:
            return False
    if "work_years" in profile:
        need = _jd_required_years(jd)
        if need and profile["work_years"] < need:
            return False
    loc = job.get("location") or ""
    if loc and city and city not in loc:
        for c in CITY_CODES:
            if c in loc:
                return False
    return True


# ── 数据存储 ────────────────────────────────────────────

def _empty_db() -> dict:
    return {"applications": [], "stats": {"total_applied": 0, "hr_replied": 0,
                                          "interview_scheduled": 0, "rejected": 0}}


def load_db() -> dict:
    if DATA_FILE.exists():
        try:
            db = json.loads(DATA_FILE.read_text(encoding="utf-8", errors="ignore"))
            if isinstance(db, dict) and isinstance(db.get("applications"), list):
                return db
        except Exception:
            pass
    return _empty_db()


def save_db(db: dict):
    DATA_FILE.parent.mkdir(exist_ok=True)
    DATA_FILE.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")


def recompute_stats(db: dict):
    apps = db.get("applications", [])
    db["stats"] = {
        "total_applied": len(apps),
        "hr_replied": sum(1 for a in apps if a.get("status") in ("hr_replied", "interviewing",
                                                                 "interview_scheduled", "offered")),
        "interview_scheduled": sum(1 for a in apps if a.get("status") in ("interview_scheduled",
                                                                           "interviewing", "offered")),
        "rejected": sum(1 for a in apps if a.get("status") == "rejected"),
    }


def find_record(url_or_id: str) -> dict | None:
    for a in load_db().get("applications", []):
        if a.get("url") == url_or_id or a.get("id") == url_or_id:
            return a
    return None


# ── 关键词生成 ──────────────────────────────────────────

def generate_keywords(intent: str) -> list[str]:
    if not intent or len(intent.strip()) < 4:
        raise ValueError("请先填写求职意向（城市、岗位、技能等）")
    prompt = (
        "你是求职搜索关键词生成器。根据用户的求职意向，生成 5~8 个中文岗位搜索关键词。\n"
        "要求：\n"
        "1. 覆盖意向的核心岗位方向，如「PLC调试」「电气工程师助理」「Python后端开发」\n"
        "2. 包含技能词变体（如 PLC→PLC编程、PLC调试）\n"
        "3. 排除销售、客服、普工等无关方向\n"
        "4. 只返回 JSON：{\"keywords\": [\"关键词1\", \"关键词2\", ...]}\n"
        f"求职意向：{intent}"
    )
    result = chat_json([{"role": "user", "content": prompt}], temperature=0.2)
    kws = [k for k in result.get("keywords", []) if isinstance(k, str) and k.strip()]
    if not kws:
        raise RuntimeError("关键词生成为空")
    return kws[:8]


# ── 三平台搜索 ──────────────────────────────────────────

def _norm_job(job: dict, platform_key: str, pcfg: dict) -> dict | None:
    """标准化岗位字段 + 过滤 + 信任检测。返回 None 表示被过滤。"""
    if not job.get("position") and not job.get("company"):
        return None
    name_map = {"boss_zhipin": "BOSS直聘", "wuyou": "51job", "shixiseng": "实习僧"}
    n = {
        "platform": job.get("platform") or name_map.get(platform_key, platform_key),
        "platform_uid": str(job.get("platform_uid") or job.get("jobId") or ""),
        "company": job.get("company") or "",
        "position": (job.get("position") or job.get("jobName") or "").strip(),
        "salary": job.get("salary") or job.get("provideSalaryString") or "",
        "location": job.get("location") or job.get("jobAreaString") or "",
        "degree": job.get("degree") or job.get("degreeString") or "",
        "work_year": job.get("work_year") or job.get("workYearString") or "",
        "url": job.get("url") or job.get("jobHref") or "",
        "jd_summary": (job.get("jd_summary") or job.get("jobDescribe") or "")[:1500],
        "hr_name": job.get("hr_name") or "",
        "risk": "normal",
        "risk_hits": [],
    }
    if not n["position"]:
        return None
    if not apply_filters(n, pcfg):
        return None
    mark_risk(n, pcfg)
    return n


def _search_one_platform(platform_key: str, keyword: str, city: str, pcfg: dict,
                         page_size: int = 20) -> list[dict]:
    from platforms import search_boss, search_shixiseng, search_wuyou
    raw: list[dict] = []
    if platform_key == "wuyou":
        city_code = pcfg.get("city_code") or CITY_CODES.get(city, "070200")
        raw = search_wuyou(keyword, city_code, page_size)
    elif platform_key == "boss_zhipin":
        city_code = pcfg.get("city_code") or "101190100"
        raw = search_boss(keyword, city_code)
    elif platform_key == "shixiseng":
        raw = search_shixiseng(keyword, pcfg.get("location") or city)
    else:
        return []
    jobs = []
    for r in raw:
        n = _norm_job(r, platform_key, pcfg)
        if n:
            jobs.append(n)
    return jobs


def run_search(intent: str, city: str = "南京", page_size: int = 20,
               progress: dict | None = None) -> dict:
    """一键流程：关键词 → 各启用平台搜索 → 去重 → LLM 评分。"""
    intent = re.sub(r"【简历解析】", "", intent or "").strip()
    platforms = enabled_platforms()
    if not platforms:
        raise RuntimeError("未启用任何平台，请检查 config/platforms.yml")

    # 登录门禁：按 Dashboard 登录状态决定搜索范围——有几个平台登录就搜几个；
    # 一个都没登录则不拉起浏览器，直接提示用户先点上方登录按钮。
    _p(progress, "检查登录状态", "按已登录平台开始搜索")
    login_states = get_login_states()
    logged_in_keys = [k for k in platforms if login_states.get(k)]
    if not logged_in_keys:
        warnings = ["还没有平台登录。请先点击上方的【BOSS登录】【51job登录】【实习僧登录】"
                    "完成至少一个平台登录，再点击【开始搜索】。"]
        return {"keywords": [], "jobs": [], "warnings": warnings,
                "login_required": list(platforms.keys()),
                "filtered": 0, "offline": 0}
    active_platforms = {k: v for k, v in platforms.items() if login_states.get(k)}
    skipped = [k for k in platforms if not login_states.get(k)]
    warnings: list[str] = []
    login_required: list[str] = []
    if skipped:
        names = "、".join(platforms[k].get("name", k) for k in skipped)
        warnings.append(f"以下平台未登录，本次跳过（可先点上方登录按钮登录）：{names}")
        login_required = list(skipped)

    _p(progress, "生成搜索关键词")
    keywords = generate_keywords(intent)
    profile = _user_profile(intent)
    all_jobs: list[dict] = []
    seen: set = set()
    for pkey, pcfg in active_platforms.items():
        name = pcfg.get("name", pkey)
        count = 0
        fails = 0
        for idx, kw in enumerate(keywords):
            if fails >= 2:
                warnings.append(f"{name}：连续失败，跳过剩余关键词（疑似被风控/未登录）")
                break
            _p(progress, f"搜索 {name}", f"关键词 {idx + 1}/{len(keywords)}")
            try:
                jobs = _search_one_platform(pkey, kw, city, pcfg, page_size)
                fails = 0
                for j in jobs:
                    key = (j.get("platform", ""), j.get("platform_uid") or j.get("url", ""))
                    key2 = (j.get("company", ""), j.get("position", ""))
                    if key in seen or (j.get("url") and key2 in seen):
                        continue
                    seen.add(key)
                    seen.add(key2)
                    all_jobs.append(j)
                count += len(jobs)
            except LoginRequired as e:
                mark_login(pkey, False)
                login_required.append(pkey)
                warnings.append(f"{name}：{e}")
                break
            except Exception as e:
                fails += 1
                msg = str(e)[:200]
                warnings.append(f"{name}：{kw} 搜索失败：{msg}")
            time.sleep(0.3)
        if count:
            warnings.append(f"{name}：共找到 {count} 个岗位")
        elif pkey not in login_required:
            warnings.append(f"{name}：未找到岗位（可能需要登录/更换关键词）")

    # 硬指标过滤（评分前剔除，节省 LLM 调用）
    _p(progress, "硬指标过滤", "学历/年限/地域不满足的岗位直接剔除")
    before = len(all_jobs)
    all_jobs = [j for j in all_jobs if _hard_filter(j, profile, city)]
    hard_removed = before - len(all_jobs)

    # 候选过多时先限量（避免一次性 LLM 评分爆量）
    if len(all_jobs) > 100:
        all_jobs = all_jobs[:100]
    _p(progress, "AI 评分", f"共 {len(all_jobs)} 个候选岗位")
    total_candidates = len(all_jobs)
    all_jobs = score_jobs(all_jobs, intent)
    all_jobs.sort(key=lambda j: j.get("score", 0), reverse=True)
    filtered = sum(1 for j in all_jobs if j.get("score", 0) < 3)
    filtered += hard_removed
    all_jobs = [j for j in all_jobs if j.get("score", 0) >= 3]

    # 已下线/审核中岗位过滤（只校验评分达标的岗位，节省请求）
    offline = 0
    if all_jobs:
        _p(progress, "校验岗位有效性", "正在过滤已下线/审核中的岗位")
        from concurrent.futures import ThreadPoolExecutor
        from platforms import job_offline

        def _keep(j: dict):
            if j.get("platform") == "51job" and j.get("url") and job_offline(j["url"]):
                return None
            return j

        with ThreadPoolExecutor(max_workers=8) as ex:
            kept = list(ex.map(_keep, all_jobs))
        offline = sum(1 for j in all_jobs if j not in kept)
        all_jobs = [j for j in kept if j]

    _p(progress, "完成", f"共找到 {len(all_jobs)} 个匹配岗位")
    return {"keywords": keywords, "jobs": all_jobs, "warnings": warnings,
            "login_required": login_required,
            "filtered": filtered, "offline": offline}


def score_jobs(jobs: list[dict], intent: str) -> list[dict]:
    """LLM 批量评分 1~5 星。"""
    if not jobs:
        return jobs
    brief = [
        {"i": i, "公司": j["company"], "岗位": j["position"], "薪资": j["salary"],
         "地点": j["location"], "学历": j["degree"], "经验": j["work_year"],
         "JD": j["jd_summary"][:200]}
        for i, j in enumerate(jobs)
    ]
    prompt = (
        "你是求职匹配评分专家。根据求职者意向，对每个岗位评 1~5 星：\n"
        "5星=专业高度匹配+学历符合+城市符合；4星=相关可投；3星=沾边可试；2星=勉强；1星=不投\n"
        "硬性要求必须一票否决：学历不达标、经验年限不够、工作地点不在目标城市、必需技能缺失 → 一律打 1 星，"
        "即使其他方面再好也不行，并在 reason 里说明是哪个硬指标不满足。\n"
        "只返回 JSON：{\"scores\": [{\"i\": 0, \"score\": 4, \"reason\": \"一句话理由\"}, ...]}\n"
        f"求职意向：{intent}\n岗位列表：{json.dumps(brief, ensure_ascii=False)}"
    )
    try:
        result = chat_json([{"role": "user", "content": prompt}], temperature=0.1)
        score_map = {s.get("i"): s for s in result.get("scores", []) if isinstance(s, dict)}
        for i, j in enumerate(jobs):
            s = score_map.get(i, {})
            j["score"] = max(1, min(5, int(s.get("score", 3) or 3)))
            j["reason"] = s.get("reason", "")
    except Exception:
        # 评分失败不阻塞：全部按 3 星展示
        for j in jobs:
            j.setdefault("score", 3)
            j.setdefault("reason", "")
    return jobs


# ── 记录与投递 ──────────────────────────────────────────

def add_application(job: dict, status: str = "discovered") -> dict:
    """把岗位加入投递记录。返回新增记录；重复返回 ValueError。"""
    db = load_db()
    apps = db.get("applications", [])
    url = job.get("url", "")
    uid = str(job.get("platform_uid") or "")
    for a in apps:
        if url and a.get("url") == url:
            raise ValueError("该岗位已在记录中")
        if uid and a.get("platform_uid") == uid and a.get("platform") == job.get("platform"):
            raise ValueError("该岗位已在记录中")
    now = datetime.now().isoformat(timespec="seconds")
    rec = {
        "id": uuid.uuid4().hex[:12],
        "company": job.get("company", ""),
        "position": job.get("position", ""),
        "platform": job.get("platform", "手动"),
        "platform_uid": uid,
        "salary": job.get("salary", ""),
        "location": job.get("location", ""),
        "degree": job.get("degree", ""),
        "work_year": job.get("work_year", ""),
        "score": int(job.get("score", 0) or 0),
        "reason": job.get("reason", ""),
        "url": url,
        "jd_summary": job.get("jd_summary", ""),
        "hr_name": job.get("hr_name", ""),
        "contact_person": job.get("contact_person"),
        "contact_phone": job.get("contact_phone"),
        "status": status,
        "applied_at": now,
        "last_update": now,
        "messages": job.get("messages", []),
        "notes": job.get("notes", ""),
    }
    apps.insert(0, rec)
    db["applications"] = apps
    recompute_stats(db)
    save_db(db)
    _sync_after_change()
    return rec


def apply_job(job: dict) -> dict:
    """自动投递：调用平台投递逻辑，成功后记录状态 applied。"""
    from platforms import apply
    result = apply(job)
    platform_key = {"51job": "wuyou", "BOSS直聘": "boss_zhipin", "实习僧": "shixiseng"}.get(
        job.get("platform", ""))
    if result.get("ok"):
        if platform_key:
            mark_login(platform_key, True)
    elif result.get("need_login") and platform_key:
        mark_login(platform_key, False)
    if result.get("ok"):
        try:
            rec = add_application(job, status="applied")
            result["record"] = rec
        except ValueError:
            # 已存在记录 → 更新为 applied
            db = load_db()
            for a in db.get("applications", []):
                if a.get("url") == job.get("url"):
                    a["status"] = "applied"
                    a["last_update"] = datetime.now().isoformat(timespec="seconds")
                    break
            recompute_stats(db)
            save_db(db)
            _sync_after_change()
            result["record"] = find_record(job.get("url", ""))
    return result


def update_status(url_or_id: str, status: str) -> dict:
    db = load_db()
    for a in db.get("applications", []):
        if a.get("url") == url_or_id or a.get("id") == url_or_id:
            a["status"] = status
            a["last_update"] = datetime.now().isoformat(timespec="seconds")
            recompute_stats(db)
            save_db(db)
            _sync_after_change()
            return {"ok": True, "record": a}
    return {"ok": False, "error": "未找到该记录"}


def _sync_after_change():
    import spreadsheet
    settings = spreadsheet.load_settings()
    if not settings["spreadsheet"].get("enabled"):
        return
    db = load_db()
    spreadsheet.sync_async(db.get("applications", []))


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    intent = sys.argv[1] if len(sys.argv) > 1 else "大专，电气自动化，2027毕业，南京，PLC调试实习"
    try:
        r = run_search(intent)
        print(f"关键词: {r['keywords']}")
        print(f"岗位数: {len(r['jobs'])}")
        for w in r["warnings"]:
            print("  ⚠", w)
        for j in r["jobs"][:8]:
            print(f"  ⭐{j['score']} [{j['platform']}] {j['position']} @ {j['company']} {j['salary']}")
    except Exception as e:
        print(f"❌ {e}")
        raise SystemExit(1)
