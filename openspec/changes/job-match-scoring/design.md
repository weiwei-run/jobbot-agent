## Context

现状：`engine.py` 的 `score_jobs` 让 LLM 基于卡片 `jd_summary[:200]` 打 1~5 星，输出不稳定且无证据；`verify_job` 只对 Top 10 读详情页做有效性校验，不取全文；`config/user_profile.json` 实际只保存 `intent` 文本，模板中的结构化字段未填充；看板提供自动投递按钮。动机与范围见 proposal.md。

## Goals / Non-Goals

**Goals:**
- 建立"LLM 结构化提取 + 规则加权计算"的评分管道，输出 0~100 总分、档位、分项分与证据链，结果可复现、可单测。
- 两段式搜索管道：卡片粗筛 ≤30 → 详情页读取（校验 + 取完整 JD 一次完成）→ 精排 → Top 10 分页展示。
- 画像结构化：保存意向时由 LLM 提取画像字段，缺失关键字段（届别、薪资期望）时引导补全。
- 看板改为展示评分详情 + 岗位链接 + 每页 10 条翻页；移除自动投递入口。

**Non-Goals:**
- 社招权重表本次不实现，只预留结构。
- 不引入第三方依赖（维持纯 stdlib + Camofox/Node 现状）。
- 不做权重自动校准闭环（v1 只记录用户投递反馈，不自动调参）。
- 不实现跨平台去重（按决策保留重复岗位）。

## Decisions

### 1. 评分架构：LLM 提取、规则算分

LLM 只做两件事：从详情 JD 提取结构化要求（必备技能、优先技能、学历/专业/证书/经验、岗位方向），从简历/画像提取技能与项目证据并做同义归一；分数由 Python 规则按权重表计算。

理由：规则计算可复现、可单测、可校准，且不随 prompt 波动；LLM 的语义判断能力用在同义归一（"可编程控制器"≈"PLC"）这种规则做不好的地方。

备选：直接让 LLM 输出分项分（prompt 给定权重）。缺点是不可复现、难单测，故放弃。

### 2. 两段式管道，详情读取只做一次

`run_search` 改为：

```
搜索 → 规则粗筛 → LLM 轻量评分（卡片）→ 取 Top 30
  → 详情页读取（fetch_detail：校验下线/学历/地点 + 返回完整 JD 文本）
  → LLM 提取 JD 结构化要求（批量）→ 规则加权精排 → 总分排序
  → 返回 ≤30 条完整排序结果 → 前端分页每页 10 条
```

`platforms.verify_job` 扩展为 `fetch_detail`：在原有校验字段（offline/degree/location/verified）基础上返回 `jd_text` 与 `salary`；读取失败仍按"不可核实直接过滤"处理。精排与校验共用同一次详情页读取，避免二次开页（省时间、降风控风险）。

### 3. 画像结构化与补全引导

保存意向/上传简历时，LLM 从 `intent + resume_parse` 提取模板字段（education、graduate_year、major、skills、certificates、expected_cities、expected_jobs、expected_salary、job_type 等），写回 `config/user_profile.json`；检测关键字段缺失（graduate_year、expected_salary、job_type、education）时返回 `missing_fields` 列表，看板展示补全引导。

提取失败时保留原 intent 文本并在结果中标注"评分精度受限"，不阻塞。

### 4. 权重表结构（校招/实习版）

权重常量放 `engine.py`，结构为可扩展 dict：

```python
SCORE_WEIGHTS_CAMPUS = {
  "hard_skills": 30,       # 必备项×2、优先项×1；直接证据1.0 / 语义等价0.7 / 无0
  "project_intern": 25,    # 直接相关1.0 / 可迁移0.5
  "edu_major": 20,         # 学历层次达标 + 专业对口/相关/不限/无关
  "cert_lang": 10,         # JD 要求证书是否持有
  "city_industry": 15,     # 目标城市 + 岗位方向一致
}
SCORE_WEIGHTS_SOCIAL = None  # 预留
```

档位：≥85 高度匹配 / 70-84 推荐投递 / 50-69 备选 / <50 观望。星级换算按 20 分一星（≤5 星兼容显示）。

### 5. 自动投递入口移除

看板移除"🚀 投递"按钮，岗位卡片提供详情链接（新标签打开）+「加入记录」手动记录入口。`engine.apply_job` 与 `platforms` 投递代码保留不删（apply-and-tracking 规格仍定义自动投递成功验证契约，后续作加分项恢复），仅 UI 不再暴露。

### 6. 数据兼容

`data/applications.json` 的 `score` 字段语义变为 0-100；旧记录中 ≤5 的值按星级兼容显示（不迁移改写，避免破坏历史数据）。新增评分详情字段（`score_breakdown`、`evidence`）仅随搜索结果返回，默认不写入投递记录（投递时可选快照）。

### 7. 在线表格同步移除

按产品定位调整，整体删除在线同步：`spreadsheet.py` 删除、`engine` 记录写入后不再触发外部推送、`dashboard` 移除设置界面与 `/api/settings` 接口、`online-sync` 能力域从规格中 REMOVED。投递记录与状态流转保留在本地看板（含 CSV 导出），「加入记录」默认状态改为 `applied` 以对齐"先投递、后记录"的新流程。`config/settings.json` 遗留文件不主动删除（已不入库），对功能无影响。

## Risks / Trade-offs

- 每轮 30 条详情页读取耗时与风控风险上升（预计单轮搜索从 1~2 分钟增至 3~8 分钟）→ 沿用现有浏览器并发 tab ≤3 与失败重试；读取失败直接过滤，不拖慢流程；30 为可调上限。
- LLM 结构化提取偶尔不符合 JSON schema → 固定 `chat_json` schema + 失败重试一次；提取失败岗位降级为卡片文本兜底评分并标注。
- 权重表为经验值、未经校准 → v1 只展示不承诺；后续用用户"投/不投"反馈做离线校准。
- 跨平台重复岗位保留导致同一岗位多条 → 符合用户决策；看板以平台标签区分，避免误判为刷屏。

## Migration Plan

1. 后端先行：`engine` 新增评分模块与画像提取，`run_search` 新管道；API 返回新结构（总分/档位/分项/证据），旧字段（score 1-5、reason）保留兼容。
2. 前端随后：结果卡片展示新评分详情与分页；移除投递按钮、增加链接与补全引导。
3. 旧投递记录不受影响；`user_profile.json` 在下次保存意向时自动补全结构化字段。
4. 回滚：若新评分质量明显变差，切回旧 `score_jobs`（保留旧函数），前端按 score 兼容显示。

## Open Questions

- 30 条详情读取的实际耗时阈值与每轮上限的最终值，待真实登录态实测后调整（不改规格，只调配置）。
- 星级换算的具体映射（20 分一星）待 UI 联调时确认展示细节。
