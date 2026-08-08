## 1. 画像与城市提取工具

- [x] 1.1 `engine.py` 新增 `load_user_profile()`：读取 `config/user_profile.json`，返回 `resume_parse` 文本与 `city` 字段
- [x] 1.2 改造 `_user_profile(intent, resume_parse)`：最高学历优先从 `resume_parse` 提取（正则 `学历[:：]\s*(博士|硕士|本科|大专|中专|高中|研究生)`，研究生归一为硕士），意向文本仅兜底；两者皆缺时返回缺失标记供警告使用
- [x] 1.3 `platforms.py` 新增 `extract_city(text)`：遍历 `CITY_CODES` 返回文本中出现的第一个城市名，排除「全国」「不限」等无效词

## 2. 详情页核实（verify_job）

- [x] 2.1 将 `platforms.job_offline` 改造为 `verify_job(job)`：返回 `{offline, degree, location, verified}`；51job 走 HTTP 详情页，网络异常/WAF 拦截返回 `verified=False`（调用方按 D5 直接过滤）
- [x] 2.2 `browser.py` 新增「打开详情页并取正文」封装：创建 tab → 取 `document.body.innerText` → 关闭 tab，带超时与登录墙检测；并发 tab 数限制 ≤ 3
- [x] 2.3 `platforms.py` 实现 BOSS直聘/实习僧的 `verify_job`：Camofox 打开详情页，匹配 `OFFLINE_MARKERS`，用 `_jd_required_degree` 与 `extract_city` 提取学历/城市

## 3. 硬指标过滤修正

- [x] 3.1 `_hard_filter` 地点判断改用 `extract_city`：卡片城市 ≠ 目标城市即剔除；卡片只有区名/无城市时标记「待详情核实」
- [x] 3.2 修正实习僧 `_SXS_EXTRACT_JS` 的 location 正则，保留「城市-区/县」完整片段（如「长沙-望城区」不再被截成「望城区」）
- [x] 3.3 评分前对全部候选调用 `verify_job` 统一核实（下线/学历/地点），不再仅限卡片数据不足的岗位
- [x] 3.4 从 `_user_profile` 与 `_hard_filter` 中移除工作年限硬校验；`score_jobs` 评分 prompt 移除「经验年限不够→1星」否决，经验仅作参考因素

## 4. 搜索管道集成

- [x] 4.1 `run_search` 改为：评分取 3 星以上前 10 名，仅对这 ≤10 个候选统一详情核实（下线/学历/地点一次拿全），核实通过才展示
- [x] 4.2 不可核实或核实不通过的岗位直接过滤，不展示、不要求人工确认；最终为空时如实提示「未找到合适的岗位」（可附 `filtered`/`offline` 计数，不列具体岗位）
- [x] 4.3 `filtered`/`offline` 统计如实反映三平台剔除数量，进度反馈「校验岗位有效性」附 `(已校验/总数)`

## 5. 验证与收尾

- [x] 5.1 工具级自测：`extract_city`（含「长沙-望城区」「望城区」）、学历提取（「学历:本科」「统招本科」）、`verify_job` 三态（在线/下线/无法核实）
- [ ] 5.2 真实登录态下三平台各搜一轮，确认结果不再出现「审核中/已下线」岗位与异地/学历不达标岗位；全部被过滤时如实显示 0 结果提示
- [ ] 5.3 `openspec validate` 通过，投递流程回归不受影响
