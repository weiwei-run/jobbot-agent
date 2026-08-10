#!/usr/bin/env python3
"""job-match-scoring 变更自测：画像提取 / 评分核心 / 两段式管道（全部 mock，不碰真实配置与数据）。"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import engine  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


PROFILE_FIELDS = {
    "education": "大专", "graduate_year": 2027, "major": "电气自动化",
    "skills": ["PLC编程调试", "CAD"], "certificates": ["低压电工证"],
    "expected_cities": ["南京"], "expected_jobs": ["电气工程师助理"],
    "expected_salary": [3000, 6000], "job_type": "实习",
}

GOOD_ANALYSIS = {
    "must_skills": ["PLC编程"], "preferred_skills": ["CAD"],
    "required_education": "大专", "required_certificates": ["低压电工证"],
    "work_location": "南京", "job_direction": "电气自动化/PLC调试",
    "skill_matches": [
        {"skill": "PLC编程", "resume_skill": "PLC编程调试", "match": "exact",
         "confidence": 1.0, "evidence": "技能:PLC编程调试"},
        {"skill": "CAD", "resume_skill": "CAD", "match": "exact",
         "confidence": 1.0, "evidence": "技能:CAD"},
    ],
    "experience_relevance": 1.0, "experience_evidence": "经历:ABB机器人实操与PLC编程调试",
    "major_relevance": 1.0, "direction_relevance": 1.0,
}


def mock_chat_json(messages, temperature=0.2):
    prompt = messages[-1]["content"] if messages else ""
    if "求职画像提取器" in prompt:
        return dict(PROFILE_FIELDS)
    if "人岗匹配分析器" in prompt:
        return json.loads(json.dumps(GOOD_ANALYSIS))
    if "求职搜索关键词生成器" in prompt:
        return {"keywords": ["PLC调试"]}
    if "求职匹配评分专家" in prompt:
        return {"scores": []}
    raise AssertionError(f"未预期的 prompt: {prompt[:80]}")


def test_profile_extraction():
    engine.chat_json = mock_chat_json
    fields = engine.extract_profile_fields("大专，电气自动化，2027毕业，南京，PLC调试实习",
                                          "技能:PLC编程调试")
    assert fields["education"] == "大专"
    assert fields["graduate_year"] == 2027
    assert "PLC编程调试" in fields["skills"]
    assert fields["job_type"] == "实习"
    print("✓ 1.4a 正常提取结构化画像字段")


def test_missing_fields():
    missing = engine.profile_missing_fields({"education": "大专"})
    assert "graduate_year" in missing and "expected_salary" in missing
    assert "education" not in missing
    print("✓ 1.4b 缺失字段检测")


def test_extract_failure_fallback():
    calls = {"n": 0}

    def fail_chat(messages, temperature=0.2):
        calls["n"] += 1
        raise RuntimeError("LLM 不可用")

    engine.chat_json = fail_chat
    store = {}
    engine.save_profile = lambda p: None  # profile 与 store 同一对象，原地修改即持久化
    engine.load_user_profile = lambda: store
    r = engine.enrich_profile("意向文本", "", "南京")
    assert r["extract_failed"] is True
    assert r["missing_fields"]
    # 失败后相同文本允许重试（LLM 恢复后可补提取）
    engine.enrich_profile("意向文本", "", "南京")
    assert calls["n"] == 2
    print("✓ 1.4c LLM 失败降级（不阻塞），失败后允许重试")


def test_grade_star_boundaries():
    assert engine._grade(49) == "观望"
    assert engine._grade(50) == "备选"
    assert engine._grade(69) == "备选"
    assert engine._grade(70) == "推荐投递"
    assert engine._grade(84) == "推荐投递"
    assert engine._grade(85) == "高度匹配"
    assert engine._star(0) == 1 and engine._star(19) == 1
    assert engine._star(20) == 2 and engine._star(40) == 3
    assert engine._star(60) == 4 and engine._star(100) == 5
    print("✓ 2.7a 档位与星级边界")


def test_semantic_match():
    a = json.loads(json.dumps(GOOD_ANALYSIS))
    a["skill_matches"][0]["match"] = "semantic"
    a["skill_matches"][0]["confidence"] = 0.7
    res = engine.compute_match_scores(a, PROFILE_FIELDS, "南京")
    # 必备 PLC编程 2×0.7 + 优先 CAD 1×1.0 = 2.4/3 → 0.8×30 = 24
    assert res["score_breakdown"]["hard_skills"] == 24.0
    print("  (语义匹配置信度 0.7 生效)")
    print("✓ 2.7b 技能同义匹配计入部分分")


def test_missing_required_skill():
    a = {"must_skills": ["PLC编程"], "preferred_skills": [], "required_education": "大专",
         "required_certificates": [], "work_location": "南京", "job_direction": "电气自动化",
         "skill_matches": [], "experience_relevance": 0.0, "experience_evidence": "",
         "major_relevance": 0.5, "direction_relevance": 0.5}
    res = engine.compute_match_scores(a, PROFILE_FIELDS, "南京")
    assert res["score_breakdown"]["hard_skills"] == 0.0
    assert any("必备技能" in g for g in res["gaps"])
    assert res["score"] < 50
    print("✓ 2.7c 必备技能缺失 → 低分 + 缺口说明")


def test_evidence_format():
    res = engine.compute_match_scores(GOOD_ANALYSIS, PROFILE_FIELDS, "南京")
    assert res["score"] == 100 and res["grade"] == "高度匹配"
    assert res["score_breakdown"]["hard_skills"] == 30.0
    assert res["evidence"] and all("item" in e and "confidence" in e for e in res["evidence"])
    assert res["reason"]
    print("✓ 2.7d 证据链输出 + 满分场景总分 100")


def test_analyze_retry():
    calls = {"n": 0}

    def flaky(jd, profile):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("LLM 返回非 JSON: （瞬时异常）")
        return json.loads(json.dumps(GOOD_ANALYSIS))

    engine.analyze_job_match = flaky
    jobs = [{"jd_text": "JD 全文", "jd_summary": "卡片", "score": 5}]
    engine.precise_score_jobs(jobs, PROFILE_FIELDS, "南京")
    assert calls["n"] == 2                      # 失败后自动重试一次
    assert jobs[0]["score"] == 100 and jobs[0]["score_failed"] is False
    print("✓ 评分失败自动重试一次后成功")


def _mk_job(platform, uid, company, position, url):
    return {"platform": platform, "platform_uid": uid, "company": company,
            "position": position, "salary": "100-200/天", "location": "南京-江宁区",
            "degree": "大专", "work_year": "应届", "url": url,
            "jd_summary": "PLC调试", "hr_name": "", "risk": "normal", "risk_hits": []}


def test_pipeline():
    engine.chat_json = mock_chat_json
    engine.enabled_platforms = lambda: {
        "boss_zhipin": {"name": "BOSS直聘", "enabled": True},
        "wuyou": {"name": "51job", "enabled": True},
    }
    engine.get_login_states = lambda: {"boss_zhipin": True, "wuyou": True}
    engine.load_user_profile = lambda: {}
    engine.save_profile = lambda p: None
    engine.score_jobs = lambda jobs, intent: [j.update(score=5, reason="粗筛") or j for j in jobs]
    engine.analyze_job_match = lambda jd, profile: json.loads(json.dumps(GOOD_ANALYSIS))

    jobs_boss = [
        _mk_job("BOSS直聘", "b1", "公司A", "电气实习生", "https://x/b1"),
        _mk_job("BOSS直聘", "b2", "公司B", "PLC调试员", "https://x/b2"),       # 跨平台重复（与 wuyou w2）
        _mk_job("BOSS直聘", "b3", "公司C", "电气助理", "https://x/b3"),        # 已下线
        _mk_job("BOSS直聘", "b4", "公司D", "自动化实习生", "https://x/b4"),   # 无法核实
        _mk_job("BOSS直聘", "b5", "公司E", "电气工程师", "https://x/b5"),     # 学历不达标（本科）
    ]
    jobs_wuyou = [
        _mk_job("51job", "w1", "公司F", "电气自动化实习生", "https://x/w1"),
        _mk_job("51job", "w2", "公司B", "PLC调试员", "https://x/w2"),         # 跨平台重复（与 boss b2）
        _mk_job("51job", "w3", "公司G", "电气实习生", "https://x/w3"),        # 已下线
        _mk_job("51job", "w4", "公司H", "电气实习生", "https://x/w4"),        # 地点不符（长沙）
        _mk_job("51job", "w5", "公司I", "电气实习生", "https://x/w5"),
    ]

    def fake_search(pkey, kw, city, pcfg, page_size=20):
        return jobs_boss if pkey == "boss_zhipin" else jobs_wuyou

    engine._search_one_platform = fake_search

    def fake_fetch(job):
        url = job.get("url", "")
        if url in ("https://x/b3", "https://x/w3"):
            return {"offline": True, "degree": 0, "location": "", "salary": "",
                    "verified": True, "jd_text": ""}
        if url == "https://x/b4":
            return {"offline": False, "degree": 0, "location": "", "salary": "",
                    "verified": False, "jd_text": ""}
        if url == "https://x/b5":
            return {"offline": False, "degree": 3, "location": "南京", "salary": "",
                    "verified": True, "jd_text": "要求本科"}
        if url == "https://x/w4":
            return {"offline": False, "degree": 1, "location": "长沙", "salary": "",
                    "verified": True, "jd_text": "长沙"}
        return {"offline": False, "degree": 1, "location": "南京-江宁区", "salary": "150/天",
                "verified": True, "jd_text": "PLC 调试岗位 JD 全文"}

    engine.fetch_detail = fake_fetch
    r = engine.run_search("大专，电气自动化，2027毕业，南京，PLC调试实习", city="南京")
    assert r["offline"] == 2
    jobs = r["jobs"]
    urls = {j["url"] for j in jobs}
    assert "https://x/b3" not in urls and "https://x/w3" not in urls   # 已下线过滤
    assert "https://x/b4" not in urls                                  # 无法核实过滤
    assert "https://x/b5" not in urls                                  # 学历不达标过滤
    assert "https://x/w4" not in urls                                  # 异地过滤
    assert "https://x/b2" in urls and "https://x/w2" in urls           # 跨平台重复保留
    assert len(jobs) == 5
    for j in jobs:
        assert 0 <= j["score"] <= 100 and j["grade"] and j["score_breakdown"] and j["evidence"]
    scores = [j["score"] for j in jobs]
    assert scores == sorted(scores, reverse=True)
    print("✓ 3.6 管道级自测：粗筛→详情→精排→Top10 排序，下线/无法核实/异地/学历不达标均被过滤")


def main():
    tests = [test_profile_extraction, test_missing_fields, test_extract_failure_fallback,
             test_grade_star_boundaries, test_semantic_match, test_missing_required_skill,
             test_evidence_format, test_analyze_retry, test_pipeline]
    for t in tests:
        t()
    print(f"\n全部 {len(tests)} 项自测通过")


if __name__ == "__main__":
    main()
