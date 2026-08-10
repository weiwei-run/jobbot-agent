#!/usr/bin/env python3
"""三大平台搜索与自动投递。

51job：纯 HTTP API（快）→ 被 WAF 拦截时降级 Chrome headless 解析渲染后 DOM。
BOSS直聘 / 实习僧：Camofox 浏览器驱动（反检测），投递前需用户手动登录一次。

所有投递都必须「验证成功」才返回 ok，登录/风控拦截会给出明确提示。
"""
import json
import re
import threading
import time
import urllib.parse
import urllib.request

import browser


class LoginRequired(RuntimeError):
    """平台需要用户手动登录。抛出时浏览器已停留在登录页，等待用户手动完成。"""


# 每个关键词最多拉取页数 / 滚动次数（"查看更多"）
WUYOU_MAX_PAGES = 3
SCROLL_ROUNDS = 5

# 岗位已下线/失效特征词
OFFLINE_MARKERS = [
    "审核中", "已下线", "职位已关闭", "招聘已结束", "已暂停招聘",
    "职位不存在", "该职位已下线", "该职位已暂停", "职位已失效", "岗位已下线",
    "已下架", "该职位已下架", "职位已下架", "已停止招聘", "停止招聘",
    "暂不招聘", "岗位已关闭", "职位已结束",
]

# 城市名表（与 engine.CITY_CODES 对应，用于地点硬过滤）
CITY_NAMES = [
    "北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "苏州", "西安",
    "长沙", "天津", "重庆", "郑州", "合肥", "无锡", "宁波", "青岛", "厦门",
    "佛山", "南京",
]
# 地点文本中出现这些词时视为「无法定位具体城市」（全国/不限等）
_CITY_INVALID_WORDS = ("全国", "不限", "其他", "异地", "海外", "国外")


def extract_city(text: str) -> str:
    """从文本中提取第一个命中的城市名；无城市或命中「全国/不限」等无效词返回 ''。"""
    if not text:
        return ""
    if any(w in text for w in _CITY_INVALID_WORDS):
        return ""
    for c in CITY_NAMES:
        if c in text:
            return c
    return ""


def extract_location(text: str) -> str:
    """从文本提取「城市·区/县」片段（如 南京·江宁区 / 长沙-望城区），找不到返回 ''。"""
    if not text:
        return ""
    for c in CITY_NAMES:
        m = re.search(re.escape(c) + r"(?:市)?\s*[-·—]?\s*[\u4e00-\u9fa5]{2,6}(?:区|县)", text)
        if m:
            return m.group(0).replace(" ", "")
    return ""


# 学历硬指标等级（数值越大要求越高）
DEGREE_RANK = {"高中": 0, "中专": 0, "大专": 1, "本科": 2, "硕士": 3, "博士": 4}


def jd_required_degree(text: str) -> int:
    """从岗位文本提取最低学历等级，0 = 不限/无明确要求。"""
    if not text:
        return 0
    if re.search(r"学历\s*(不限|无要求)", text):
        return 0
    m = re.search(r"(?:学历|要求)[:：]?\s*(博士|硕士|本科|大专|中专|高中)", text)
    if m:
        return DEGREE_RANK[m.group(1)]
    m = re.search(r"(统招|全日制)?\s*(博士|硕士|本科|大专|中专|高中)[及以]?上?", text)
    if m:
        return DEGREE_RANK[m.group(2)]
    return 0


# 浏览器详情核实并发限制（同时最多开 3 个 Camofox tab）
_BROWSER_VERIFY_SEM = threading.Semaphore(3)


def verify_job(job: dict) -> dict:
    """核实岗位详情：下线状态 + 学历/城市硬指标 + 完整 JD 文本。

    返回 {offline, degree, location, salary, verified, jd_text}。

    - offline: 详情页出现「已下线/审核中」等失效特征
    - degree: 详情页要求的最低学历等级（0 = 不限/未写明）
    - location: 详情页正文片段（供 extract_city 判断城市）
    - salary: 详情页正文提取的薪资（8-13K / 6千-8千 / 100-200/天），取不到为空
    - verified: 详情页是否成功读取；False = 网络/风控/登录墙导致无法核实
    - jd_text: 详情页完整正文（截断至 6000 字符，供 LLM 精排评分）
    """
    url = job.get("url") or ""
    platform = job.get("platform", "")
    if not url:
        # 无链接的岗位无法投递也无法核实，直接视为失效
        return {"offline": True, "degree": 0, "location": "", "salary": "",
                "verified": True, "jd_text": ""}
    if platform == "51job":
        return _verify_wuyou(url)
    if platform in ("BOSS直聘", "实习僧"):
        return _verify_browser(url)
    return {"offline": False, "degree": 0, "location": "", "salary": "",
            "verified": False, "jd_text": ""}


# 精排评分复用同一详情读取（校验 + 完整 JD 一次完成）
fetch_detail = verify_job


def _verify_wuyou(url: str) -> dict:
    """51job：HTTP 请求服务端渲染的详情页。网络异常/WAF 拦截视为无法核实。"""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        with urllib.request.urlopen(req, timeout=10) as r:
            html = r.read(300000).decode("utf-8", errors="ignore")
    except Exception:
        return {"offline": False, "degree": 0, "location": "", "salary": "",
                "verified": False, "jd_text": ""}
    if any(m in html for m in OFFLINE_MARKERS):
        return {"offline": True, "degree": 0, "location": "", "salary": "",
                "verified": True, "jd_text": ""}
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return {"offline": False, "degree": jd_required_degree(text),
            "location": text[:800], "salary": _extract_detail_salary(text),
            "verified": True, "jd_text": text[:6000]}


def _verify_browser(url: str) -> dict:
    """BOSS直聘/实习僧：Camofox 打开详情页取正文核实（并发 tab ≤ 3）。"""
    with _BROWSER_VERIFY_SEM:
        try:
            r = browser.open_page_text(url, timeout=15, markers=OFFLINE_MARKERS)
        except Exception:
            return {"offline": False, "degree": 0, "location": "", "salary": "",
                    "verified": False, "jd_text": ""}
    if not r.get("ok"):
        return {"offline": False, "degree": 0, "location": "", "salary": "",
                "verified": False, "jd_text": ""}
    text = r.get("text") or ""
    if any(m in text for m in OFFLINE_MARKERS):
        return {"offline": True, "degree": 0, "location": "", "salary": "",
                "verified": True, "jd_text": ""}
    return {"offline": False, "degree": jd_required_degree(text),
            "location": text[:800], "salary": _extract_detail_salary(text),
            "verified": True, "jd_text": text[:6000]}


_DETAIL_SALARY_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*[-~—至]\s*(\d+(?:\.\d+)?)\s*(万元|千|万|K|k)?\s*(/月|/天|/周)?")
_DETAIL_SALARY_RE2 = re.compile(
    r"(\d+(?:\.\d+)?)\s*(千|万)\s*[-~—至]\s*(\d+(?:\.\d+)?)\s*(千|万)\s*(/月|/天|/周)?")


def _fmt_salary_num(s: str) -> str:
    """薪资数字去无意义尾零（8.0 → 8）。"""
    try:
        f = float(s)
        return str(int(f)) if f == int(f) else s
    except ValueError:
        return s


def _extract_detail_salary(text: str) -> str:
    """从岗位详情正文提取薪资（如 8-13K / 6千-8千 / 100-200/天）。

    取正文前 400 字内的首个区间匹配（详情页首段通常是「标题 + 薪资」）。
    """
    if not text:
        return ""
    head = (text or "")[:400]
    m = _DETAIL_SALARY_RE2.search(head)
    if m:
        period = m.group(5) or ""
        return (f"{_fmt_salary_num(m.group(1))}{m.group(2)}-"
                f"{_fmt_salary_num(m.group(3))}{m.group(4)}{period}")
    m = _DETAIL_SALARY_RE.search(head)
    if m:
        unit = (m.group(3) or "").upper() if (m.group(3) or "").lower() == "k" else (m.group(3) or "")
        period = m.group(4) or ""
        return f"{_fmt_salary_num(m.group(1))}-{_fmt_salary_num(m.group(2))}{unit}{period}"
    return ""


# ── 通用解析工具 ──────────────────────────────────────────

def parse_salary(text: str) -> tuple[int, int]:
    """把 '3-4.5千' / '1-1.5万' / '面议' 解析成 (min, max) 元。解析失败返回 (0,0)。"""
    if not text:
        return 0, 0
    t = text.replace(" ", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*[-~—至]\s*(\d+(?:\.\d+)?)\s*(千|万)?", t)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        unit = 10000 if m.group(3) == "万" else 1000 if m.group(3) == "千" else 1
        return int(lo * unit), int(hi * unit)
    m = re.search(r"(\d+(?:\.\d+)?)\s*(千|万)?", t)
    if m:
        v = float(m.group(1))
        unit = 10000 if m.group(2) == "万" else 1000 if m.group(2) == "千" else 1
        return int(v * unit), int(v * unit)
    return 0, 0


def _parse_extract(raw) -> list:
    """Camofox evaluate 结果可能是结构化数组，也可能是 JSON 字符串，统一转成 list。"""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
            return data if isinstance(data, list) else []
        except Exception:
            return []
    return []


def apply_filters(job: dict, pcfg: dict) -> bool:
    """按平台配置的标题黑名单 / 薪资 / 学历过滤。返回 True = 保留。"""
    title = (job.get("position") or "").lower()
    tf = pcfg.get("title_filter") or {}
    for w in tf.get("negative", []):
        if w and w.lower() in title:
            return False

    sf = pcfg.get("salary_filter") or {}
    lo_min = int(sf.get("min") or 0)
    hi_max = int(sf.get("max") or 0)
    if lo_min or hi_max:
        sal_min, sal_max = parse_salary(job.get("salary"))
        if sal_min and sal_max:
            if lo_min and sal_max < lo_min:
                return False
            if hi_max and sal_min > hi_max:
                return False

    allow = pcfg.get("education_allow") or []
    if allow:
        degree = job.get("degree") or ""
        if degree:
            ok = any(a in degree for a in allow) or "不限" in degree
            if not ok:
                return False
    return True


def mark_risk(job: dict, pcfg: dict):
    """信任检测：命中可疑词打标，不自动过滤。"""
    tf = pcfg.get("trust_filter") or {}
    if not tf.get("enabled", True):
        job["risk"] = "normal"
        job["risk_hits"] = []
        return
    text = f"{job.get('position')} {job.get('jd_summary')} {job.get('company')}"
    susp = tf.get("suspicious_keywords", [])
    high = tf.get("high_risk_keywords", [])
    hits = [w for w in susp if w in text]
    hits += [w for w in high if w in text]
    ceiling = int(tf.get("salary_ceiling") or 0)
    if ceiling:
        sal_min, sal_max = parse_salary(job.get("salary"))
        if sal_max and sal_max > ceiling and ("不限" in (job.get("degree") or "") or not job.get("degree")):
            hits.append("薪资虚高")
    job["risk"] = "suspicious" if hits else "normal"
    job["risk_hits"] = hits


# ── 51job 搜索 ──────────────────────────────────────────

WUYOU_API = "https://we.51job.com/api/job/search-pc"


def _wuyou_params(keyword: str, city_code: str, page_size: int = 20) -> dict:
    return {
        "api_key": "51job",
        "timestamp": str(int(time.time() * 1000)),
        "keyword": keyword,
        "searchType": "2",
        "jobArea": city_code,
        "pageNum": "1",
        "pageSize": str(page_size),
        "source": "1",
        "scene": "7",
        "sortType": "0",
        "workYear": "02",  # 在校生/应届生
    }


def search_wuyou(keyword: str, city_code: str, page_size: int = 20) -> list[dict]:
    """HTTP 快路径（多页拉取）→ 被 WAF 拦截时降级 Chrome headless 滚动解析。"""
    try:
        return _wuyou_http(keyword, city_code, page_size, WUYOU_MAX_PAGES)
    except Exception:
        return _wuyou_chrome(keyword, city_code, page_size)


def _wuyou_http(keyword: str, city_code: str, page_size: int, max_pages: int) -> list[dict]:
    jobs: list[dict] = []
    seen: set[str] = set()
    for page in range(1, max_pages + 1):
        params = _wuyou_params(keyword, city_code, page_size)
        params["pageNum"] = str(page)
        url = WUYOU_API + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
        })
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read().decode("utf-8", errors="replace")
        if not body.lstrip().startswith("{"):
            raise RuntimeError("WAF blocked")
        items = _parse_wuyou_items(json.loads(body))
        if not items:
            break
        for j in items:
            if j["url"] and j["url"] not in seen:
                seen.add(j["url"])
                jobs.append(j)
        if len(items) < page_size:
            break  # 最后一页
    return jobs


def _parse_wuyou_items(data: dict) -> list[dict]:
    items = (data.get("resultbody") or {}).get("job", {}).get("items", []) or []
    jobs = []
    for it in items:
        if it.get("isApply"):  # 已投递过，跳过
            continue
        jd = (it.get("jobDescribe") or "")[:1500]
        jobs.append({
            "platform": "51job",
            "platform_uid": str(it.get("jobId", "")),
            "company": it.get("fullCompanyName", ""),
            "position": it.get("jobName", ""),
            "salary": it.get("provideSalaryString", ""),
            "location": it.get("jobAreaString", ""),
            "degree": it.get("degreeString", ""),
            "work_year": it.get("workYearString", ""),
            "url": it.get("jobHref", ""),
            "jd_summary": jd,
            "hr_name": it.get("hrName", ""),
            "risk": "normal",
            "risk_hits": [],
        })
    return jobs


_WUYOU_EXTRACT_JS = r"""
(() => {
  const out = [];
  // 只取岗位详情页：jobs.51job.com/…/{数字}.html；排除公司页 /all/co*
  const links = Array.from(document.querySelectorAll('a[href*="jobs.51job.com"]')).filter(a => {
    const h = a.href || '';
    return /\/\d+\.html$/.test(h) && h.indexOf('/all/co') < 0;
  });
  for (const a of links) {
    const href = a.href || '';
    if (out.some(j => j.url === href)) continue;
    let el = a;
    for (let i = 0; i < 7; i++) { el = el.parentElement; if (!el) break; }
    const text = (el && el.innerText || '').replace(/\s+/g, ' ').trim();
    let title = (a.innerText || '').trim().replace(/\s+/g, ' ').slice(0, 80);
    if (!text || !title) continue;
    const sm = text.match(/(\d+(?:\.\d+)?\s*[-~至—]\s*\d+(?:\.\d+)?\s*[千万元])|(\d+(?:\.\d+)?\s*[千万元])/);
    const salary = sm ? sm[0].replace(/\s+/g, '') : '';
    const locM = text.match(/([\u4e00-\u9fa5]{2,8}·[\u4e00-\u9fa5]{2,8})/);
    const location = locM ? locM[1] : '';
    const cm = text.match(/([\u4e00-\u9fa5A-Za-z0-9（）()]+?(?:有限公司|股份|集团|科技|服务|咨询|工作室|中心|工厂|厂|事务所))/);
    const company = cm ? cm[1] : '';
    // 标题为空时从卡片文本取第一段（如 "电气工程师（南京）"）
    if (!title && text) title = text.split('|')[0].trim().slice(0, 80);
    if (company || location || salary) {
      out.push({position: title, salary, company, location, url: href, jd_summary: text.slice(0, 300)});
    }
  }
  return out;
})()
"""


def _wuyou_chrome(keyword: str, city_code: str, page_size: int) -> list[dict]:
    """Chrome headless：加载搜索页（过 WAF JS 挑战），等列表渲染后解析 DOM。"""
    from playwright.sync_api import sync_playwright
    land_url = (f"https://we.51job.com/pc/search?jobArea={city_code}"
                f"&keyword={urllib.parse.quote(keyword)}&searchType=2&sortType=0")
    with sync_playwright() as p:
        browser_inst = p.chromium.launch(headless=True)
        page = browser_inst.new_page()
        try:
            page.goto(land_url, timeout=45000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            # 滚动加载更多，滚动两轮无新结果即结束
            cards: list[dict] = []
            seen: set[str] = set()
            no_new = 0
            for _ in range(SCROLL_ROUNDS + 3):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(2000)
                batch = page.evaluate(_WUYOU_EXTRACT_JS) or []
                new = [c for c in batch if c.get("url") and c["url"] not in seen]
                for c in new:
                    seen.add(c["url"])
                    cards.append(c)
                if not new:
                    no_new += 1
                    if no_new >= 2:
                        break
                else:
                    no_new = 0
            return cards
        finally:
            browser_inst.close()


# ── BOSS直聘 搜索 ───────────────────────────────────────

def _platform_login_url(key: str) -> str:
    from engine import load_platforms
    pcfg = load_platforms().get(key) or {}
    return pcfg.get("login_url") or pcfg.get("base_url") or ""


_BOSS_EXTRACT_JS = r"""
(() => {
  const out = [];
  // BOSS 薪资数字用图标字体（kanzhun-mix）编码在私有区：\uE031+n = 数字 n；
  // 其余私有区字符是装饰图标，直接剔除
  const decode = s => (s || '').replace(/[\uE031-\uE03A]/g, ch =>
      String.fromCharCode(ch.codePointAt(0) - 0xE031 + 48))
    .replace(/[\uE000-\uF8FF]/g, '').trim();
  const clean = s => (s || '').replace(/[\uE000-\uF8FF]/g, '').replace(/\s+/g, ' ').trim();
  const pick = (el, sels) => {
    for (const s of sels) { const e = el.querySelector(s); if (e && e.innerText) return e.innerText.trim(); }
    return '';
  };
  const cards = Array.from(document.querySelectorAll('.job-card-wrapper, .job-card, [class*=job-card], [class*=jobcard], a[href*="job_detail"]'));
  for (const c of cards) {
    const a = c.tagName === 'A' ? c : c.querySelector('a[href*="job_detail"], a[href*="job"]');
    const href = (a && a.href) || '';
    if (out.some(j => j.url === href)) continue;
    const title = clean(pick(c, ['.job-name', '.job-title', '[class*=job-name]', '[class*=job-title]']) || (a ? a.innerText : ''));
    const salary = decode(pick(c, ['.salary', '[class*=salary]']));
    // 新版卡片公司名在 span.boss-name；[class*=company] 会误匹配 company-location，不能用
    const company = clean(pick(c, ['.boss-name', '.company-name', '.company-info', '[class*=boss-name]', '[class*=company-name]', '.name']));
    const area = clean(pick(c, ['.job-area', '.job-location', '[class*=area]', '[class*=location]']));
    const info = clean(pick(c, ['.job-banner', '.job-card-footer', '.info-desc', '[class*=desc]', '[class*=tag]']));
    if (title || company) out.push({position: title, salary, company, location: area, url: href, jd_summary: info});
  }
  return out;
})()
"""


def search_boss(keyword: str, city_code: str) -> list[dict]:
    ensured = browser.ensure_camofox()
    if not ensured["ok"]:
        raise RuntimeError(ensured["message"])
    url = (f"https://www.zhipin.com/web/geek/job?query={urllib.parse.quote(keyword)}"
           f"&city={city_code}")
    tab = browser.create_tab(url)
    keep_tab = False
    try:
        time.sleep(6)
        cur = browser.evaluate(tab, "location.href")
        if "login" in (cur or "").lower():
            keep_tab = True
            browser.navigate(tab, _platform_login_url("boss_zhipin"))
            raise LoginRequired("BOSS直聘需要登录：浏览器已停在登录页，请手动完成登录后回来点「已登录，继续」")
        # BOSS 未登录会直接显示登录墙（URL 不变）
        wall = browser.js_bool(browser.evaluate(tab,
            "document.body.innerText.indexOf('验证码登录') >= 0 || document.body.innerText.indexOf('APP扫码登录') >= 0"))
        if wall:
            keep_tab = True
            browser.navigate(tab, _platform_login_url("boss_zhipin"))
            raise LoginRequired("BOSS直聘需要登录：浏览器已停在登录页，请手动完成登录后回来点「已登录，继续」")
        cards: list[dict] = []
        seen: set[str] = set()
        no_new = 0
        for _ in range(SCROLL_ROUNDS):
            raw = browser.evaluate(tab, _BOSS_EXTRACT_JS)
            batch = _parse_extract(raw)
            new = [c for c in batch if c.get("url") and c["url"] not in seen]
            for c in new:
                seen.add(c["url"])
                cards.append(c)
            if not new:
                no_new += 1
                if no_new >= 2:
                    break
            else:
                no_new = 0
            browser.evaluate(tab, "window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2)
        if not cards:
            raise RuntimeError("BOSS直聘未解析到岗位（可能被风控拦截或页面结构变化）")
        for c in cards:
            c["platform"] = "BOSS直聘"
        return cards
    finally:
        if not keep_tab:
            browser.close_tab(tab)


# ── 实习僧 搜索 ─────────────────────────────────────────

_SXS_EXTRACT_JS = r"""
(() => {
  const out = [];
  const links = Array.from(document.querySelectorAll('a[href*="intern"], a[href*="/job/"]'))
    .filter(a => !a.closest('.other-content, [class*=other-content]'));  // 排除「推荐职位」
  const clean = s => (s || '').replace(/[\uE000-\uF8FF]/g, '').replace(/\s+/g, ' ').trim();
  for (const a of links) {
    const href = a.href || '';
    if (!/shixiseng\.com\/(intern|job)/.test(href)) continue;
    if (out.some(j => j.url === href)) continue;
    const title = clean(a.innerText).slice(0, 80);
    if (!title) continue;
    const card = a.closest('.intern-item, .intern-wrap') || a.parentElement || a;
    const dayEl = card.querySelector('.day');
    const salary = dayEl ? clean(dayEl.innerText) : '';
    const companyEl = card.querySelector('.intern-detail__company .title')
      || card.querySelector('.company-title, [class*=company] .title');
    const company = companyEl ? clean(companyEl.innerText || companyEl.getAttribute('title')) : '';
    const locEl = card.querySelector('.city');
    const location = locEl ? clean(locEl.innerText) : '';
    const jd = clean(card.innerText).slice(0, 300);
    if (company || location || salary) {
      out.push({position: title, salary, company, location, url: href, jd_summary: jd});
    }
  }
  return out;
})()
"""


def search_shixiseng(keyword: str, city: str) -> list[dict]:
    ensured = browser.ensure_camofox()
    if not ensured["ok"]:
        raise RuntimeError(ensured["message"])
    url = (f"https://www.shixiseng.com/interns?keyword={urllib.parse.quote(keyword)}"
           f"&city={urllib.parse.quote(city)}&type=intern")
    tab = browser.create_tab(url)
    keep_tab = False
    try:
        time.sleep(8)
        cur = browser.evaluate(tab, "location.href")
        if "login" in (cur or "").lower() or "passport" in (cur or "").lower():
            keep_tab = True
            browser.navigate(tab, _platform_login_url("shixiseng"))
            raise LoginRequired("实习僧需要登录：浏览器已停在登录页，请手动完成登录后回来点「已登录，继续」")
        cards: list[dict] = []
        seen: set[str] = set()
        no_new = 0
        for _ in range(SCROLL_ROUNDS):
            raw = browser.evaluate(tab, _SXS_EXTRACT_JS)
            batch = _parse_extract(raw)
            new = [c for c in batch if c.get("url") and c["url"] not in seen]
            for c in new:
                seen.add(c["url"])
                cards.append(c)
            if not new:
                no_new += 1
                if no_new >= 2:
                    break
            else:
                no_new = 0
            browser.evaluate(tab, "window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2)
        if not cards:
            empty = browser.evaluate(tab,
                "document.body.innerText.indexOf('暂无') >= 0 || document.body.innerText.indexOf('没有找到') >= 0")
            if browser.js_bool(empty):
                raise RuntimeError("实习僧当前搜索无结果，请尝试换关键词或城市")
            raise RuntimeError("实习僧未解析到岗位（可能被风控拦截或页面结构变化）")
        for c in cards:
            c["platform"] = "实习僧"
        return cards
    finally:
        if not keep_tab:
            browser.close_tab(tab)


# ── 自动投递（Camofox）──────────────────────────────────

def _click_js(selector_expr: str) -> str:
    """生成递归事件派发 JS（BOSS React 委托按钮必需）。"""
    return ("""
      (function clickAll(s){document.querySelectorAll(s).forEach(function(e){
        const r = e.getBoundingClientRect();
        const x = r.x + r.width/2, y = r.y + r.height/2;
        e.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,clientX:x,clientY:y}));
        e.dispatchEvent(new MouseEvent('mouseup',{bubbles:true,clientX:x,clientY:y}));
        e.dispatchEvent(new MouseEvent('click',{bubbles:true,clientX:x,clientY:y}));
        clickAll(e);
      })})(""" + selector_expr + "); 'clicked'")


def _find_visible_button_js(texts: list[str]) -> str:
    """找到可见的、文本精确匹配的按钮并点击。"""
    quoted = json.dumps(texts)
    return ("""
      (() => {
        const texts = """ + quoted + """;
        const els = document.querySelectorAll('button, a, span, div, li');
        for (const e of els) {
          const t = (e.innerText || e.textContent || '').trim();
          if (texts.includes(t) && e.offsetParent !== null && e.offsetWidth > 0 && e.offsetHeight > 0) {
            e.dispatchEvent(new MouseEvent('mousedown',{bubbles:true}));
            e.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));
            e.click();
            return 'clicked:' + t;
          }
        }
        return 'notfound';
      })()
    """)


def apply_boss(job: dict) -> dict:
    """BOSS直聘：点击「立即沟通」，验证 已发送/继续沟通/送达。"""
    ensured = browser.ensure_camofox()
    if not ensured["ok"]:
        return {"ok": False, "message": ensured["message"], "need_camofox": True}
    url = job.get("url") or ""
    if not url:
        return {"ok": False, "message": "缺少岗位链接"}
    tab = browser.create_tab(url)
    keep_tab = False
    try:
        time.sleep(6)
        cur = browser.evaluate(tab, "location.href")
        if "login" in (cur or "").lower():
            keep_tab = True
            browser.navigate(tab, _platform_login_url("boss_zhipin"))
            return {"ok": False, "need_login": True,
                    "message": "BOSS直聘未登录：浏览器已停在登录页，请手动登录后回来重新点「投递」"}
        wall = browser.js_bool(browser.evaluate(tab,
            "document.body.innerText.indexOf('验证码登录') >= 0 || document.body.innerText.indexOf('APP扫码登录') >= 0"))
        if wall:
            keep_tab = True
            browser.navigate(tab, _platform_login_url("boss_zhipin"))
            return {"ok": False, "need_login": True,
                    "message": "BOSS直聘未登录：浏览器已停在登录页，请手动登录后回来重新点「投递」"}
        body_text = browser.evaluate(tab, "document.body.innerText")
        if any(m in (body_text or "") for m in OFFLINE_MARKERS):
            return {"ok": False, "message": "该岗位已下线或审核中，请换一个岗位投递", "offline": True}
        # 点「立即沟通」
        sel = "'.btn-startchat-wrap, [class*=btn-startchat], [class*=chat-btn], [class*=沟通]'"
        browser.evaluate(tab, _click_js(sel))
        time.sleep(3)
        state = browser.wait_js(tab,
            "(document.body.innerText.includes('已发送') ? 'sent' : (document.body.innerText.includes('继续沟通') ? 'continue' : (document.body.innerText.includes('送达') ? 'delivered' : 'none')))",
            timeout=12)
        if state == "sent" or state == "delivered":
            return {"ok": True, "message": "已发送沟通消息（验证：已发送）", "verified": state}
        if state == "continue":
            browser.evaluate(tab, _click_js(sel))
            time.sleep(3)
            state2 = browser.wait_js(tab,
                "(document.body.innerText.includes('已发送') ? 'sent' : (document.body.innerText.includes('送达') ? 'delivered' : 'none'))",
                timeout=10)
            if state2 in ("sent", "delivered"):
                return {"ok": True, "message": "已发送沟通消息（验证：已发送）", "verified": state2}
            return {"ok": False, "message": "点击后未检测到「已发送」状态，可能被风控拦截"}
        return {"ok": False, "message": "未检测到投递成功状态，请人工确认"}
    finally:
        if not keep_tab:
            browser.close_tab(tab)


def apply_wuyou(job: dict) -> dict:
    """51job：打开岗位详情 → 点「投递」→ 验证「投递成功」。"""
    ensured = browser.ensure_camofox()
    if not ensured["ok"]:
        return {"ok": False, "message": ensured["message"], "need_camofox": True}
    url = job.get("url") or ""
    if not url:
        return {"ok": False, "message": "缺少岗位链接"}
    tab = browser.create_tab(url)
    keep_tab = False
    try:
        time.sleep(6)
        cur = browser.evaluate(tab, "location.href")
        if "login" in (cur or "").lower():
            keep_tab = True
            browser.navigate(tab, _platform_login_url("wuyou"))
            return {"ok": False, "need_login": True,
                    "message": "51job 未登录：浏览器已停在登录页，请手动登录后回来重新点「投递」"}
        body_text = browser.evaluate(tab, "document.body.innerText")
        if any(m in (body_text or "") for m in OFFLINE_MARKERS):
            return {"ok": False, "message": "该岗位已下线或审核中，请换一个岗位投递", "offline": True}
        # 部分岗位是「去聊聊」而非「投递」
        btn_state = browser.evaluate(tab, _find_visible_button_js(["投递", "立即投递", "投递简历"]))
        if "notfound" in str(btn_state):
            chat = browser.evaluate(tab, "(document.body.innerText.includes('去聊聊') ? 'chat' : 'none')")
            if "chat" in str(chat):
                return {"ok": False, "message": "该岗位只有「去聊聊」入口，需人工处理", "skip": True}
            return {"ok": False, "message": "未找到「投递」按钮，请人工确认"}
        time.sleep(3)
        ok_state = browser.wait_js(tab,
            "(document.body.innerText.includes('投递成功') ? 'success' : (document.body.innerText.includes('已投递') ? 'applied' : 'none'))",
            timeout=12)
        if ok_state in ("success", "applied"):
            return {"ok": True, "message": "投递成功（验证：投递成功）", "verified": ok_state}
        # 常见「微信扫码」弹窗也意味着投递成功，关闭后继续
        if ok_state == "none":
            browser.evaluate(tab, _click_js("'.ant-modal-close, [class*=close], .modal-close, .icon-close'"))
            ok2 = browser.wait_js(tab,
                "(document.body.innerText.includes('投递成功') ? 'success' : (document.body.innerText.includes('已投递') ? 'applied' : 'none'))",
                timeout=6)
            if ok2 in ("success", "applied"):
                return {"ok": True, "message": "投递成功（验证：投递成功）", "verified": ok2}
        return {"ok": False, "message": "点击投递后未验证到成功状态，请人工确认"}
    finally:
        if not keep_tab:
            browser.close_tab(tab)


def apply_shixiseng(job: dict) -> dict:
    """实习僧：点「投个简历」→ 选附件简历 → 确认投递。"""
    ensured = browser.ensure_camofox()
    if not ensured["ok"]:
        return {"ok": False, "message": ensured["message"], "need_camofox": True}
    url = job.get("url") or ""
    if not url:
        return {"ok": False, "message": "缺少岗位链接"}
    tab = browser.create_tab(url)
    keep_tab = False
    try:
        time.sleep(6)
        cur = browser.evaluate(tab, "location.href")
        if "login" in (cur or "").lower() or "passport" in (cur or "").lower():
            keep_tab = True
            browser.navigate(tab, _platform_login_url("shixiseng"))
            return {"ok": False, "need_login": True,
                    "message": "实习僧未登录：浏览器已停在登录页，请手动登录后回来重新点「投递」"}
        body_text = browser.evaluate(tab, "document.body.innerText")
        if any(m in (body_text or "") for m in OFFLINE_MARKERS):
            return {"ok": False, "message": "该岗位已下线或审核中，请换一个岗位投递", "offline": True}
        r1 = browser.evaluate(tab, _find_visible_button_js(["投个简历", "投递", "立即投递"]))
        if "notfound" in str(r1):
            return {"ok": False, "message": "未找到「投个简历」按钮，请人工确认"}
        time.sleep(3)
        # 弹窗内选择附件简历并确认
        browser.evaluate(tab, _click_js("'.common-deliver__item, [class*=resume-item], [class*=deliver] [class*=item]'"))
        browser.evaluate(tab, _click_js("'.common-deliver__footer, [class*=deliver] [class*=footer], [class*=confirm]'"))
        time.sleep(3)
        ok_state = browser.wait_js(tab,
            "(document.body.innerText.includes('投递成功') ? 'success' : (document.body.innerText.includes('已投递') ? 'applied' : 'none'))",
            timeout=10)
        if ok_state in ("success", "applied"):
            return {"ok": True, "message": "投递成功（验证：投递成功）", "verified": ok_state}
        return {"ok": False, "message": "实习僧投递后未验证到成功状态，请人工确认"}
    finally:
        if not keep_tab:
            browser.close_tab(tab)


def apply(job: dict) -> dict:
    platform = job.get("platform", "")
    if platform == "51job":
        return apply_wuyou(job)
    if platform == "BOSS直聘":
        return apply_boss(job)
    if platform == "实习僧":
        return apply_shixiseng(job)
    return {"ok": False, "message": f"平台 {platform} 暂不支持自动投递"}
