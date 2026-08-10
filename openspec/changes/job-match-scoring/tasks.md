## 1. 画像结构化提取

- [x] 1.1 `engine.py` 新增 `extract_profile_fields(intent, resume_parse)`：LLM 从意向与简历解析文本中提取结构化字段（学历层次、毕业届别、专业、技能、证书、目标城市、岗位方向、薪资期望、招聘类型），输出固定 JSON 并写回 `config/user_profile.json`
- [x] 1.2 新增关键字段缺失检测：`graduate_year` / `expected_salary` / `job_type` / `education` 缺失时返回 `missing_fields` 列表
- [x] 1.3 保存意向流程接入提取与降级：LLM 失败时保留原 intent 文本并标记"评分精度受限"，不阻塞保存
- [x] 1.4 工具级自测：正常提取、缺字段、LLM 失败三种场景断言通过

## 2. 评分核心（结构化加权）

- [x] 2.1 `engine.py` 新增 `SCORE_WEIGHTS_CAMPUS` 权重表（硬技能30 / 项目实习25 / 学历届别专业20 / 证书语言10 / 城市行业意向15）与档位常量（85+/70-84/50-69/<50），社招权重表预留 `None`
- [x] 2.2 新增 JD 结构化提取：从详情页完整 JD 文本提取必备技能、优先技能、学历/专业/证书/经验要求、工作地点与岗位方向（`chat_json` 固定 schema）
- [x] 2.3 技能匹配判断：精确命中记 1.0，语义等价（同义归一，如「可编程控制器」≈「PLC」）记 0.7，无证据记 0
- [x] 2.4 实现分项分与总分计算：硬技能（必备项×2/优先项×1）、项目实习（直接相关1.0/可迁移0.5）、学历届别专业、证书语言、城市行业意向，总分 0~100
- [x] 2.5 证据链生成：每条岗位输出命中证据（简历原句/项目段落）、缺口说明（JD 要求但画像无）、一句话理由
- [x] 2.6 星级兼容换算：20 分一星映射 1~5 星
- [x] 2.7 单元自测：同义匹配、必备技能缺失、档位边界（49/50/69/70/84/85）、证据输出格式

## 3. 两段式搜索管道

- [x] 3.1 `platforms.verify_job` 扩展为 `fetch_detail`：在 offline/degree/location/verified 基础上返回完整 `jd_text` 与 `salary`；51job 走 HTTP 详情页、BOSS/实习僧走浏览器详情页
- [x] 3.2 详情页读取失败仍按"不可核实直接过滤"处理，不展示、不要求人工确认
- [x] 3.3 去重逻辑调整：仅同平台同岗位 ID/URL 去重，跨平台重复岗位保留展示
- [x] 3.4 `run_search` 改为两段式：卡片规则粗筛 + LLM 轻量评分取 Top 30 → 详情页读取（校验+取 JD 一次完成）→ JD 结构化提取 + 加权精排 → 按总分降序输出
- [x] 3.5 结果返回新增 `score`（0-100）、`grade`、`score_breakdown`、`evidence`、`missing_fields` 字段，旧 `reason` 保留兼容
- [x] 3.6 管道级自测：mock 三平台数据跑通粗筛→详情→精排→Top 10，校验失败岗位被过滤

## 4. 看板展示与交互

- [x] 4.1 结果卡片展示 0~100 总分、档位、分项分、命中证据与缺口；1~5 星按换算兼容显示
- [x] 4.2 结果分页：每页固定 10 条，「换一批」翻页查看下一页
- [x] 4.3 移除自动投递按钮，岗位卡片提供详情链接（新标签打开）+「加入记录」手动记录入口
- [x] 4.4 画像补全引导：`missing_fields` 非空时看板展示补全表单，保存后写回 `config/user_profile.json`
- [x] 4.5 评分失败/画像字段缺失时如实标注"评分精度受限"，不冒充正常评分

## 5. 验证与收尾

- [x] 5.1 `python -m py_compile` 全部通过，工具级与管道级自测通过
- [x] 5.2 `openspec validate` 通过
- [ ] 5.3 真实登录态下三平台各搜一轮：确认评分输出、分页、详情链接正常，无回归（旧记录、投递流程不受影响）
- [x] 5.4 按约定在 `run-log.md` 记录本次变更

## 6. 自测反馈修复

- [x] 6.1 修复搜索进度提示不显示：状态元素 `hidden` 类未移除导致 CSS `display:none` 常驻；改为全屏遮罩（步骤/详情/耗时实时展示）+ 阻塞页面所有操作，结束后自动收起
- [x] 6.2 降低「评分失败（LLM 调用异常）」概率：`analyze_job_match` 失败自动重试一次、并发精排 4→2、max_tokens 4000→8000、JD 截断 6000→5000；失败时缺口说明附带真实错误原因
- [x] 6.3 新增重试自测并全量回归：9 项自测通过、`py_compile` 通过、`openspec validate` 通过

## 7. 第二轮反馈（UI 细节）

- [x] 7.1 分页按钮「换一批」改为「下一页」（功能不变）
- [x] 7.2 搜索完成后新增黄色提示行「更换关键词示例：…」展示推荐关键词（与警告同字号同色）
- [x] 7.3 推荐岗位支持按平台筛选（全部平台/BOSS直聘/51job/实习僧），筛选后分页与计数同步

## 8. 移除在线表格同步（定位调整）

- [x] 8.1 删除 `spreadsheet.py`，`engine.py` 移除 `_sync_after_change` 钩子（新增/更新记录不再触发外部推送）
- [x] 8.2 `dashboard.py` 移除设置界面、`loadSettings`/`saveSettings`/`testSettings`、`/api/settings` 与 `/api/settings/test` 接口
- [x] 8.3 「加入记录」默认状态改为 `applied`（先投递、后记录），提示文案同步为「已加入记录（已投递）」
- [x] 8.4 清理文档：`README.md` / `PRODUCT.md` / `start.py` / `TODO.md` / `openspec/config.yaml` 移除在线同步说明
- [x] 8.5 新增 `online-sync` REMOVED delta 并更新 proposal/design；`openspec validate` 通过

## 9. 第三轮反馈（遮罩显示异常）

- [x] 9.1 修复搜索遮罩启动即常驻：`#search-overlay{display:flex}`（ID 优先级）覆盖了 `.hidden{display:none}`，新增 `#search-overlay.hidden{display:none}` 显式覆盖，并排查确认无其他同类冲突

## 10. 第四轮反馈（UI 精简）

- [x] 10.1 移除搜索结果中的关键词标签行（`kw-box`），保留黄色「更换关键词示例：…」文字行
