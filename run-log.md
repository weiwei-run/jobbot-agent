# JobBot 运行日志

> 每次 OpenCode 运行 JobBot 后记录。

---

## 2026-08-09 #0 — filter-undeliverable-jobs 收尾：真实登录态实测通过 + 归档；顺带修复 BOSS 薪资乱码

- **动作**: 完成 5.2/5.3——真实登录态下三平台各搜一轮（BOSS直聘 256 / 51job 14 / 实习僧 109 个岗位），
  最终展示 7 个岗位全部 `verified=True`、`offline=0`、地点均在南京（3 个未通过详情核实的候选被如实过滤）；
  投递记录流程（add_application / update_status / 重复 URL 转更新 / stats）工具级回归通过；
  `openspec validate --all` 7/7 通过；delta spec 已合并进 `openspec/specs/job-search/`，
  变更手动归档至 `openspec/changes/archive/2026-08-09-filter-undeliverable-jobs/`
- **附带修复（轻量，行为 bug）**: 真实搜索发现 BOSS 卡片薪资显示乱码（如 `-K`）——
  根因是 BOSS 用图标字体（kanzhun-mix）把薪资数字编码进私有区（U+E031+n = 数字 n），
  实习僧脚本有清理而 BOSS 没有。修复：`_BOSS_EXTRACT_JS` 增加私有区数字解码 +
  装饰字符剔除；`verify_job` 新增 `salary` 字段，从详情页明文提取薪资（8-13K / 6千-8千 / 100-200/天）
  并在展示前覆盖卡片值。实测卡片 5-10K/6-10K/8-13K 与详情页明文逐一吻合
- **验证**: `python -m py_compile` 通过；详情薪资提取 8 组单测全过；
  真实 BOSS 搜索 47 张卡片薪资全部干净且含数字

---

## 2026-08-08 #1 — 修复：重传简历后意向描述未刷新（前端解析块状态 bug，与格式无关）

- **现象**: 先传一份简历、再传另一份 PDF 简历后，【意向描述】仍保留旧内容，目标城市也未变
- **根因**: `splitIntent` 依赖 `_resumeParse` 在文本框末尾做后缀匹配来剥离旧解析块；一旦匹配失败（手动编辑过意向、或页面/配置状态不同步），整段文本被当成手动意向且 `resume_parse` 被清空，之后重传只把新解析块**追加**到旧内容后面，看起来"没更新"。与 PDF/docx 格式无关（实测两种格式解析均正常）
- **修复**: `uploadResume` 重传时先剥掉末尾旧解析块，若剩余部分仍以 `姓名:/学历:` 等结构化标签开头则整体丢弃，再拼新解析块
- **验证**: 模拟坏状态/正常状态/全新上传三种场景，旧内容均被干净替换；`python -m py_compile` 通过

## 2026-08-08 #0 — BOSS/实习僧 搜索解析修复（Camofox evaluate 契约变化）

- **现象**: BOSS直聘搜索报「未解析到岗位（可能被风控拦截或页面结构变化）」，但浏览器手动浏览、登录均正常
- **根因**: 三个平台抽取 JS 是裸箭头函数 `() => {...}`，Camofox evaluate 对其只返回 `{ok:true}` 无 `result`；且新版 Camofox 对数组返回结构化 JSON（Python list），应用代码 `json.loads()` 只认字符串
- **修复**: 三个抽取 JS 改为 IIFE 自调用；新增 `platforms._parse_extract()` 兼容 list/字符串；BOSS 公司选择器适配新版 `span.boss-name`（旧 `[class*=company]` 误匹配 company-location）；实习僧改用结构化选择器（`.city` / `.intern-detail__company .title`），标题清理字体图标私有区字符
- **验证**: BOSS 搜「新媒体运营」返回 17 条（公司/地点/链接正确）；实习僧返回 11 条

## 2026-08-06 #0 — 建立 OpenSpec 基线 + 变更约定

- **动作**: 通读代码生成 6 能力域基线规格（user-config / platform-automation / job-search / apply-and-tracking / local-dashboard / online-sync），归档为 `openspec/changes/archive/2026-08-06-initial-project-baseline/`
- **约定**: 是否改变用户可见行为/数据格式/外部接口 → 是走完整 OpenSpec 流程，否则轻量处理（skip_specs 或 run-log）；已写入根目录 `AGENTS.md`，重启 Codex 自动加载
- **注意**: 本机 `openspec archive` 报 EPERM（Node 目录改名问题），采用手动合并+Move-Item 归档

## 2026-07-20 #1 — 配置向导测试

- **Agent**: OpenCode v1.18.3
- **模型**: big-pickle (free)
- **输入**: "我在南京找电气自动化实习，大专，2027毕业，PLC+CAD"
- **输出**: 
  - ✅ 读取 AGENTS.md 成功，自称为 JobBot
  - ✅ 读取 config/user_profile_template.json + platforms.yml
  - ✅ 生成 user_profile.json（字段完整）
  - ✅ 生成搜索关键词（9个，分 P0-P3 优先级）
  - ✅ 询问用户确认并是否开始搜索
- **时长**: ~15秒
- **文件产物**: config/user_profile.json (796B)

---

## 2026-07-20 #0 — 环境搭建

- OpenCode 安装：npm install -g opencode-ai（需 npm 镜像）
- Postinstall：手动运行 postinstall.mjs
- AGENTS.md：复制到 ~/.config/opencode/AGENTS.md
- LongCat key：curl 验证通过，但 OpenCode 原生集成报 "incorrect api key"
- Workaround：opencode/hy3-free 或 opencode/big-pickle 免费模型可用

---

## 2026-08-08 #2 — 图片自动识别（OCR）桥接

- **背景**：Codex 当前配置为 DeepSeek（deepseek-v4-flash，无视觉能力），用户发截图时模型无法直接看图
- **动作**：新增 `scripts/ocr_image.ps1`（Windows 内置 OCR，zh-Hans-CN 优先）；AGENTS.md 增加「图片自动识别（OCR）约定」，消息带图片/截图路径时自动 OCR 再回复
- **验证**：真实中文截图（BOSS直聘页面）OCR 读取正常；`view_image` 在当前模型下不可用，OCR 为唯一读图通道

---

## 2026-08-08 #3 — BOSS直聘拦截检测 + Camofox 重启

- **现象**：Camofox 服务在跑但引擎卡死，创建标签页连续超时（HTTP 500, tab create timed out）
- **处理**：结束占用 9377 端口的 node 进程 → 冷启动 server.js + camoufox 引擎（登录 cookie 存于 profile，登录态保留）
- **检测结果**：BOSS直聘未拦截。搜索页 `zhipin.com/web/geek/jobs?query=PLC&city=101190100` 与详情页 `/job_detail/7a3e18ec8997214c0nFy09i9EFpT.html` 均正常加载，无安全验证/验证码/登录墙/IP 黑名单标记，账号（肖豪威）已登录
- **注意**：引擎冷启动后首次创建标签页较慢（本次约 90s/重试 3 次成功），遇到 `tab create timed out` 时重试即可

---

## 2026-08-10 #0 — 匹配评分机制重构（job-match-scoring 变更，实现阶段）

- **背景**：产品定位确认为"AI 完成 300→10 精细初筛"，旧评分（LLM 对卡片 200 字打 1~5 星）不可解释、不稳定、无法校准
- **方案**：调研 ATS/北森/job-copilot 的"字段化+权重+证据链"共识后确定——LLM 只做结构化提取与语义判断，分数由规则按校招权重表（硬技能30/项目实习25/学历届别专业20/证书语言10/城市行业意向15）计算 0~100 + 档位 + 分项 + 证据链
- **实现**：
  - `engine.py`：画像结构化提取（`extract_profile_fields`/`enrich_profile`，缺关键字段引导补全）；`analyze_job_match` + `compute_match_scores` 精排；`run_search` 改两段式（卡片粗筛 Top30 → 详情页校验+取完整 JD 一次完成 → 精排 → Top10 分页）
  - `platforms.py`：`verify_job` 扩展为 `fetch_detail`（新增 `jd_text` 完整 JD 返回）
  - `dashboard.py`：结果卡片展示总分/档位/分项/证据，每页 10 条「换一批」翻页，移除自动投递按钮改为「打开详情投递」链接 + 加入记录，新增画像补全引导 UI 与 `/api/profile`
  - `llm.py`：`chat_json` 支持 max_tokens；分析/提取 prompt 加"只返回 JSON 不要解释"（修复推理模型 reasoning 占满 token 导致 content 为空）
  - 新增 `scripts/selftest_scoring.py`（8 项自测全过：提取/缺失字段/降级/档位边界/同义匹配/证据链/管道级过滤）
- **验证**：`py_compile` 通过、`openspec validate` 7 项全过；真实画像提取正常（学历/专业/8 项技能/2 证书）；51job 真实搜索首次跑通（11 条），后续被临时限流返回 0，三平台实测待 Dashboard 验证
- **注意**：深色模式推理模型（deepseek-v4-flash）对复杂 JSON prompt 可能把输出预算全耗在 reasoning 上，需显式"不要解释"并调大 max_tokens；51job 高频搜索会触发临时限流

### 补充（同日自测反馈修复）

- 搜索进度提示此前从未显示：状态元素带 `hidden` 类但 JS 只改 `hidden` 属性，CSS `display:none` 常驻 → 改为全屏遮罩（步骤/详情/耗时）+ 阻塞页面操作
- 「评分失败（LLM 调用异常）」根因：推理模型在长 JD 上 reasoning 占满 token 预算导致 content 为空/截断，4 路并发加剧网关异常 → 失败重试一次 + 并发 4→2 + max_tokens 8000 + JD 截断 5000
