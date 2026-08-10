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

from concurrent.futures import ThreadPoolExecutor

from llm import chat_json
from platforms import (DEGREE_RANK, LoginRequired, apply_filters, extract_city,
                       extract_location, fetch_detail, jd_required_degree, mark_risk,
                       verify_job)

ROOT = Path(__file__).parent
DATA_FILE = ROOT / "data" / "applications.json"
PLATFORMS_FILE = ROOT / "config" / "platforms.yml"
USER_PROFILE_FILE = ROOT / "config" / "user_profile.json"

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

# ── 匹配评分（校招/实习版）──

# 维度权重：硬技能 30 / 项目实习 25 / 学历届别专业 20 / 证书语言 10 / 城市行业意向 15
SCORE_WEIGHTS_CAMPUS = {
    "hard_skills": 30,
    "project_intern": 25,
    "edu_major": 20,
    "cert_lang": 10,
    "city_industry": 15,
}
SCORE_WEIGHTS_SOCIAL = None  # 社招权重表预留，本次不实现

# 档位阈值（降序）：≥85 高度匹配 / ≥70 推荐投递 / ≥50 备选 / 其余观望
GRADE_BANDS = ((85, "高度匹配"), (70, "推荐投递"), (50, "备选"), (0, "观望"))

# 画像关键评分字段（缺失时在看板引导补全）
PROFILE_KEY_FIELDS = {
    "education": "最高学历",
    "graduate_year": "毕业届别",
    "expected_salary": "薪资期望",
    "job_type": "招聘类型（实习/校招/社招）",
}

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


def load_user_profile() -> dict:
    """读取 config/user_profile.json（求职意向 + 简历解析结果）；缺失/损坏返回空 dict。"""
    if not USER_PROFILE_FILE.exists():
        return {}
    try:
        data = json.loads(USER_PROFILE_FILE.read_text(encoding="utf-8", errors="ignore"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _user_profile(intent: str, resume_parse: str = "") -> dict:
    """提取用户硬指标（最高学历）：优先简历解析结果，意向文本仅兜底。"""
    p: dict = {}
    for text in (resume_parse, intent):
        m = re.search(r"学历[:：]\s*(博士|硕士|本科|大专|中专|高中|研究生)", text or "")
        if m:
            p["education"] = "硕士" if m.group(1) == "研究生" else m.group(1)
            break
    return p


def save_profile(profile: dict):
    """写回 config/user_profile.json。"""
    USER_PROFILE_FILE.parent.mkdir(exist_ok=True)
    USER_PROFILE_FILE.write_text(json.dumps(profile, ensure_ascii=False, indent=2),
                                 encoding="utf-8")


def profile_missing_fields(profile: dict) -> list[str]:
    """返回缺失的关键画像字段（key 列表）。"""
    missing: list[str] = []
    for key in PROFILE_KEY_FIELDS:
        val = profile.get(key)
        if val in (None, "", [], [None, None]):
            missing.append(key)
    return missing


def extract_profile_fields(intent: str, resume_parse: str = "") -> dict:
    """LLM 从意向与简历解析文本中提取结构化画像字段。

    返回字段 dict：education / graduate_year / major / skills / certificates /
    expected_cities / expected_jobs / expected_salary / job_type。
    """
    text = "意向：" + (intent or "")
    if resume_parse:
        text += "\n简历解析：" + resume_parse
    prompt = (
        "你是求职画像提取器。从用户的求职意向与简历解析文本中提取结构化画像字段。\n"
        "不要输出任何解释或思考过程，只返回 JSON：\n"
        "{\n"
        '  "education": "最高学历，取值 博士/硕士/本科/大专/中专/高中 之一，无法判断为 null",\n'
        '  "graduate_year": "毕业届别（整数年份），无法判断为 null",\n'
        '  "major": "专业名称，无法判断为 null",\n'
        '  "skills": ["技能列表，每项为具体技能词，如 PLC编程调试"],\n'
        '  "certificates": ["证书列表，如 低压电工证"],\n'
        '  "expected_cities": ["目标城市列表"],\n'
        '  "expected_jobs": ["目标岗位列表，如 电气工程师助理"],\n'
        '  "expected_salary": [最低, 最高] 或 null,\n'
        '  "job_type": "实习/校招/社招 之一，无法判断为 null"\n'
        "}\n"
        "要求：只从给定文本提取，不猜测；文本没有的字段填 null 或空数组。\n"
        f"文本：{text}"
    )
    result = chat_json([{"role": "user", "content": prompt}], temperature=0.1)
    out: dict = {}
    for k in ("education", "graduate_year", "major", "skills", "certificates",
              "expected_cities", "expected_jobs", "expected_salary", "job_type"):
        v = result.get(k)
        if k in ("skills", "certificates", "expected_cities", "expected_jobs"):
            out[k] = [str(x).strip() for x in v if str(x).strip()] if isinstance(v, list) else []
        elif k == "graduate_year":
            if isinstance(v, int):
                out[k] = v
            elif isinstance(v, str) and v.strip().isdigit():
                out[k] = int(v)
            else:
                out[k] = None
        elif k == "expected_salary":
            if isinstance(v, list) and len(v) == 2:
                out[k] = [v[0], v[1]]
            else:
                out[k] = None
        else:
            out[k] = v if isinstance(v, str) and v.strip() else None
    return out


def enrich_profile(intent: str, resume_parse: str = "", city: str = "南京") -> dict:
    """保存意向/发起搜索前调用：按需结构化提取并写回 user_profile.json。

    相同文本提取成功则缓存（_extract_src），不重复调用；LLM 失败时保留原文本并标记
    _extract_failed，允许下次重试，不阻塞流程。手动补全的字段不会被后续提取清空。
    返回 {"profile", "missing_fields", "extract_failed", "changed"}。
    """
    profile = load_user_profile()
    raw = (intent or "") + "\x00" + (resume_parse or "")
    changed = False
    if profile.get("_extract_src") == raw and not profile.get("_extract_failed"):
        changed = False
    else:
        changed = True
        profile["_extract_src"] = raw
        try:
            fields = extract_profile_fields(intent, resume_parse)
            for k, v in fields.items():
                if v not in (None, "", [], [None, None]):
                    profile[k] = v
            profile["_extract_failed"] = False
        except Exception:
            profile["_extract_failed"] = True
        profile["intent"] = intent or profile.get("intent", "")
        profile["resume_parse"] = resume_parse or profile.get("resume_parse", "")
        profile["city"] = city or profile.get("city", "南京")
        save_profile(profile)
    return {"profile": profile,
            "missing_fields": profile_missing_fields(profile),
            "extract_failed": bool(profile.get("_extract_failed")),
            "changed": changed}


def _hard_filter(job: dict, profile: dict, city: str) -> bool:
    """硬指标过滤（学历/地点）：卡片数据能确定的直接剔除，不能确定的打标记待详情核实。

    返回 True = 保留；并在 job 上打 location_ok / degree_ok 标记。
    """
    jd = job.get("jd_summary") or ""
    degree_field = job.get("degree") or ""
    edu = profile.get("education")
    if edu and edu in DEGREE_RANK:
        # 51job 学历字段来自搜索 API（可信）；BOSS/实习僧卡片学历标签不可信，交给详情页核实
        if job.get("platform") == "51job":
            need = max(jd_required_degree(jd), jd_required_degree(degree_field))
            if need > DEGREE_RANK[edu]:
                return False
            job["degree_ok"] = need > 0
        else:
            job["degree_ok"] = False
    else:
        # 画像缺学历 → 不启用学历硬过滤（调用方会在警告中提示）
        job["degree_ok"] = True
    loc = job.get("location") or ""
    ccity = extract_city(loc)
    if ccity:
        if ccity != city:
            return False
        job["location_ok"] = True
    else:
        # 卡片地点只有区名/无城市 → 待详情页核实
        job["location_ok"] = False
    return True


def _passes_verified_hard(job: dict, v: dict, profile: dict, city: str) -> bool:
    """详情页核实结果 vs 硬指标（学历/地点）。返回 True = 保留。"""
    edu = profile.get("education")
    if edu and edu in DEGREE_RANK and v.get("degree"):
        if v["degree"] > DEGREE_RANK[edu]:
            return False
    vcity = extract_city(v.get("location") or "")
    if vcity:
        return vcity == city
    # 详情页没解析出城市：卡片有城市则用卡片判断，否则视为无法确认 → 不展示
    ccity = extract_city(job.get("location") or "")
    if ccity:
        return ccity == city
    return False


def _verify_many(jobs: list[dict], progress: dict | None, step: str) -> list[dict]:
    """并发读取岗位详情（校验 + 完整 JD，浏览器并发受 platforms 信号量限制 ≤3）。

    返回与 jobs 对齐的结果列表，每条含 offline/degree/location/salary/verified/jd_text。
    """
    def _run(j: dict) -> dict:
        try:
            return fetch_detail(j)
        except Exception:
            return {"offline": False, "degree": 0, "location": "", "salary": "",
                    "verified": False, "jd_text": ""}

    out: list[dict] = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for idx, v in enumerate(ex.map(_run, jobs), 1):
            out.append(v)
            _p(progress, step, f"正在核实岗位（{idx}/{len(jobs)}）")
    return out


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

    # ── 画像：LLM 结构化提取（失败降级为文本解析，不阻塞）──
    _p(progress, "提取求职画像", "结构化画像字段")
    profile_data = load_user_profile()
    enriched = enrich_profile(intent, profile_data.get("resume_parse") or "", city)
    profile = enriched["profile"]
    if enriched["extract_failed"]:
        warnings.append("画像结构化提取失败（LLM 不可用），评分精度可能受限")
    elif enriched["missing_fields"]:
        labels = "、".join(PROFILE_KEY_FIELDS[k] for k in enriched["missing_fields"])
        warnings.append(f"画像缺少关键字段：{labels}，建议在配置区补全以提高匹配精度")
    if not profile.get("education"):
        warnings.append("未从简历解析/意向中识别到最高学历，学历硬过滤未生效，请完善意向描述")
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
                    # 同一平台内按 公司+岗位 去重；跨平台重复岗位保留展示
                    key2 = (j.get("platform", ""), j.get("company", ""), j.get("position", ""))
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

    # ── 阶段 A1：评分前确定性硬指标过滤（学历/地点，卡片数据）──
    _p(progress, "硬指标过滤", "学历/地点不满足的岗位直接剔除")
    before = len(all_jobs)
    kept_a = [j for j in all_jobs if _hard_filter(j, profile, city)]
    filtered = before - len(kept_a)
    all_jobs = kept_a

    # 候选过多时先限量（避免一次性 LLM 评分爆量）
    if len(all_jobs) > 100:
        all_jobs = all_jobs[:100]

    # ── 阶段 A2：卡片粗筛（LLM 1~5 星）→ 取 Top 30 进详情页 ──
    _p(progress, "AI 粗筛", f"共 {len(all_jobs)} 个候选岗位")
    all_jobs = score_jobs(all_jobs, intent)
    all_jobs.sort(key=lambda j: j.get("score", 0), reverse=True)
    if len(all_jobs) > 30:
        filtered += len(all_jobs) - 30
        all_jobs = all_jobs[:30]

    # ── 阶段 A3：详情页读取（校验下线/学历/地点 + 完整 JD，一次完成）──
    # 列表卡片数据不可信（BOSS 列表地点/学历可能与详情不符），一律以详情页为准；
    # 核实通过且硬指标满足才进入精排，杜绝「卡片南京、详情长沙」与「已下线」泄漏
    offline = 0
    if all_jobs:
        _p(progress, "校验岗位有效性", f"正在核实岗位（0/{len(all_jobs)}）")
        verified_jobs: list[dict] = []
        for j, v in zip(all_jobs, _verify_many(all_jobs, progress, "校验岗位有效性")):
            if v["offline"]:
                offline += 1
                continue
            if not v["verified"]:
                filtered += 1
                continue
            if not _passes_verified_hard(j, v, profile, city):
                filtered += 1
                continue
            if v.get("location"):
                j["location"] = (extract_location(v["location"])
                                 or extract_city(v["location"])
                                 or j.get("location", ""))
            # 详情页明文薪资更可靠（BOSS 卡片薪资是图标字体私有区编码），有则覆盖
            if v.get("salary"):
                j["salary"] = v["salary"]
            j["jd_text"] = v.get("jd_text") or ""
            j["verified"] = True
            verified_jobs.append(j)
        all_jobs = verified_jobs

    # ── 阶段 A4：详情精排（完整 JD 结构化加权评分 0~100）──
    if all_jobs:
        _p(progress, "AI 精排", f"正在精排 {len(all_jobs)} 个岗位")
        all_jobs = precise_score_jobs(all_jobs, profile, city, progress)
        all_jobs.sort(key=lambda j: j.get("score", 0), reverse=True)
        # 观望档（<50）不展示，避免把不推荐投递的岗位当候选推给用户
        before_final = len(all_jobs)
        all_jobs = [j for j in all_jobs if j.get("score", 0) >= 50]
        filtered += before_final - len(all_jobs)

    if not all_jobs:
        warnings.append("没有找到合适的岗位：本次候选已全部被过滤（不匹配、已下线或无法核实）。"
                        "建议调整关键词、完善意向描述或稍后再试。")

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
        "学历、工作地点等硬指标已由规则在评分前过滤，此处不再一票否决；"
        "经验年限不作为否决项；卡片 JD 可能不完整，技能缺失不代表详情页一定没有，不要因此单独打 1 星。\n"
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


# ── 匹配评分（0~100 结构化加权）────────────────────────

def _grade(score: int) -> str:
    for threshold, name in GRADE_BANDS:
        if score >= threshold:
            return name
    return "观望"


def _star(score: int) -> int:
    """0~100 分 → 1~5 星（20 分一星）。"""
    return max(1, min(5, score // 20 + 1))


def analyze_job_match(jd_text: str, profile: dict) -> dict:
    """LLM 分析岗位：提取 JD 结构化要求 + 与画像的匹配判断。

    返回供规则算分的 JSON：must_skills / preferred_skills / required_education /
    required_certificates / work_location / job_direction / skill_matches /
    experience_relevance / experience_evidence / major_relevance / direction_relevance。
    """
    brief_profile = {
        "education": profile.get("education"),
        "graduate_year": profile.get("graduate_year"),
        "major": profile.get("major"),
        "skills": profile.get("skills") or [],
        "certificates": profile.get("certificates") or [],
        "expected_cities": profile.get("expected_cities") or [],
        "expected_jobs": profile.get("expected_jobs") or [],
        "job_type": profile.get("job_type"),
    }
    prompt = (
        "你是人岗匹配分析器。根据岗位 JD 与求职者画像，输出结构化匹配分析。\n"
        "不要输出任何解释或思考过程，只返回 JSON：{\n"
        '  "must_skills": ["JD 明确要求的必备技能，如 PLC编程"],\n'
        '  "preferred_skills": ["JD 的优先/加分技能"],\n'
        '  "required_education": "JD 要求的最低学历（博士/硕士/本科/大专/中专/高中/不限），未提及为 null",\n'
        '  "required_certificates": ["JD 要求必须持有的证书"],\n'
        '  "work_location": "JD 工作地点（城市名），未提及为 null",\n'
        '  "job_direction": "岗位方向一句话，如 电气自动化/PLC调试",\n'
        '  "skill_matches": [{"skill": "JD技能", "resume_skill": "画像中对应技能或 null", '
        '"match": "exact|semantic|none", "confidence": 1.0 或 0.7 或 0, "evidence": "画像技能原文或空"}],\n'
        '  "experience_relevance": 1.0 直接相关 或 0.5 可迁移相关 或 0 不相关,\n'
        '  "experience_evidence": "画像经历/项目原文证据或空",\n'
        '  "major_relevance": 1.0 专业对口 或 0.7 相关专业 或 0.5 无明确要求 或 0 专业不符,\n'
        '  "direction_relevance": 1.0 方向一致 或 0.7 方向接近 或 0.5 方向泛化 或 0 方向不符\n'
        "}\n"
        "规则：semantic 表示同义等价（如 可编程控制器 ≈ PLC）；confidence 只允许 1.0/0.7/0；"
        "evidence 必须来自画像原文；不猜测 JD 没有的要求。\n"
        f"画像：{json.dumps(brief_profile, ensure_ascii=False)}\n"
        f"JD 文本：{(jd_text or '')[:6000]}"
    )
    return chat_json([{"role": "user", "content": prompt}], temperature=0.1,
                     max_tokens=4000)


def compute_match_scores(analysis: dict, profile: dict, city: str) -> dict:
    """按校招权重表把 LLM 分析换算为 0~100 分。

    返回 {score, grade, score_breakdown, evidence, gaps, reason}。
    """
    breakdown: dict[str, float] = {}
    hits: list[dict] = []
    gaps: list[str] = []

    # 硬技能 30：必备项权重 2、优先项权重 1；命中按 confidence 计
    must_set = {s for s in (analysis.get("must_skills") or []) if s}
    pref_set = {s for s in (analysis.get("preferred_skills") or []) if s}
    total_w, got = 0, 0.0
    for m in analysis.get("skill_matches") or []:
        skill = m.get("skill") or ""
        w = 2 if skill in must_set else 1
        conf = m.get("confidence")
        conf = float(conf) if isinstance(conf, (int, float)) else 0.0
        conf = min(1.0, max(0.0, conf))
        total_w += w
        got += w * conf
        if conf > 0:
            hits.append({"type": "技能", "item": skill,
                         "confidence": conf, "evidence": m.get("evidence") or ""})
    for s in must_set:
        if not any((m.get("skill") or "") == s for m in analysis.get("skill_matches") or []):
            total_w += 2
            gaps.append(f"JD 必备技能「{s}」画像中无证据")
    breakdown["hard_skills"] = round(got / (total_w or 1) * 30, 1)

    # 项目/实习经历 25
    exp = analysis.get("experience_relevance")
    exp = float(exp) if isinstance(exp, (int, float)) else 0.0
    exp = min(1.0, max(0.0, exp))
    breakdown["project_intern"] = round(exp * 25, 1)
    if exp > 0 and analysis.get("experience_evidence"):
        hits.append({"type": "经历", "item": "经历相关度",
                     "confidence": exp, "evidence": analysis["experience_evidence"]})
    elif exp == 0:
        gaps.append("简历经历与岗位方向相关性弱")

    # 学历/届别/专业 20：学历 12 + 专业相关 8
    req_edu = analysis.get("required_education")
    profile_edu = profile.get("education")
    if not req_edu or req_edu in ("不限", "无要求"):
        edu_score = 1.0
    elif profile_edu in DEGREE_RANK and req_edu in DEGREE_RANK:
        edu_score = 1.0 if DEGREE_RANK[profile_edu] >= DEGREE_RANK[req_edu] else 0.0
    else:
        edu_score = 0.5  # 信息不足取中性
    major_rel = analysis.get("major_relevance")
    major_rel = float(major_rel) if isinstance(major_rel, (int, float)) else 0.5
    major_rel = min(1.0, max(0.0, major_rel))
    breakdown["edu_major"] = round(edu_score * 12 + major_rel * 8, 1)
    if edu_score == 0:
        gaps.append(f"学历低于 JD 要求（{req_edu}）")
    if major_rel == 0:
        gaps.append("专业与岗位方向不符")

    # 证书/语言 10
    req_certs = [c for c in (analysis.get("required_certificates") or []) if c]
    cert_text = " ".join(str(c) for c in (profile.get("certificates") or []))
    if not req_certs:
        cert_score = 1.0
    else:
        hit_n = sum(1 for c in req_certs if c in cert_text)
        cert_score = hit_n / len(req_certs)
        for c in req_certs:
            if c in cert_text:
                hits.append({"type": "证书", "item": c, "confidence": 1.0, "evidence": c})
            else:
                gaps.append(f"JD 要求证书「{c}」画像中无")
    breakdown["cert_lang"] = round(cert_score * 10, 1)

    # 城市/行业意向 15：城市 10 + 方向 5
    loc = analysis.get("work_location") or ""
    if loc and city:
        city_ok = 1.0 if extract_city(loc) == city else 0.0
    elif loc:
        city_ok = 0.5
    else:
        city_ok = 0.5
    dir_rel = analysis.get("direction_relevance")
    dir_rel = float(dir_rel) if isinstance(dir_rel, (int, float)) else 0.5
    dir_rel = min(1.0, max(0.0, dir_rel))
    breakdown["city_industry"] = round(city_ok * 10 + dir_rel * 5, 1)
    if city_ok == 0:
        gaps.append(f"JD 工作地点 {loc} 不在目标城市 {city}")
    if dir_rel == 0:
        gaps.append("岗位方向与目标岗位不一致")

    score = int(round(sum(breakdown.values())))
    grade = _grade(score)
    hit_skills = sum(1 for h in hits if h["type"] == "技能")
    reason = (f"硬技能命中 {hit_skills} 项，经历{'相关' if exp >= 0.5 else '一般' if exp > 0 else '偏弱'}，"
              f"总分 {score}（{grade}）")
    return {"score": score, "grade": grade, "score_breakdown": breakdown,
            "evidence": hits, "gaps": gaps, "reason": reason}


def precise_score_jobs(jobs: list[dict], profile: dict, city: str,
                       progress: dict | None = None) -> list[dict]:
    """详情精排：读完整 JD 后结构化加权评分 0~100，并生成证据链。"""
    def _score_one(j: dict):
        jd_text = j.get("jd_text") or j.get("jd_summary") or ""
        try:
            analysis = analyze_job_match(jd_text, profile)
            res = compute_match_scores(analysis, profile, city)
            j.update(res)
            j["score_failed"] = False
        except Exception:
            j["score"] = 60
            j["grade"] = "备选"
            j["score_breakdown"] = {}
            j["evidence"] = []
            j["gaps"] = ["评分失败（LLM 调用异常），按备选档位展示"]
            j["reason"] = "评分失败，按备选档位展示（信息可能不完整）"
            j["score_failed"] = True
        j["star"] = _star(j.get("score", 0))
        j["missing_fields"] = profile_missing_fields(profile)
        j.pop("jd_text", None)

    if not jobs:
        return jobs
    with ThreadPoolExecutor(max_workers=4) as ex:
        for idx, _ in enumerate(ex.map(_score_one, jobs), 1):
            _p(progress, "AI 精排", f"正在精排（{idx}/{len(jobs)}）")
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
