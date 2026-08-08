## Context

当前项目是一个无第三方运行时依赖的 Python 3.10+ 单体（dashboard 单文件、纯 stdlib），通过本地 Camofox（Node）驱动浏览器自动化。现有行为散落在 `engine.py`、`platforms.py`、`browser.py`、`llm.py`、`dashboard.py`、`spreadsheet.py`、`pdftext.py` 与根目录 `SKILL.md` 运行手册中。详见 `proposal.md - Why`：本次变更不新增任何功能，只把"现状应该做什么"固化为可评审、可追踪的规格基线。

## Goals / Non-Goals

**Goals:**
- 以行为契约（而非实现细节）准确记录 6 个能力域的当前行为，覆盖搜索、评分、投递、追踪、看板、同步与配置
- 建立后续所有变更的对照基准：之后任何改动都以其为起点生成 delta
- 补全 `openspec/config.yaml` 项目上下文，让后续 AI 生成的产物贴合项目

**Non-Goals:**
- 不改任何项目代码、不引入新依赖、不修复已知问题
- 不把 TODO 中未实现的规划（回复工作流、手动投递识别、更多平台扩展）写入基线
- 不做架构重构或模块拆分

## Decisions

**按模块边界划分 6 个能力域，而非单一巨型 spec。**
`user-config`（配置/画像/简历解析）、`platform-automation`（浏览器与登录门禁）、`job-search`（搜索匹配管线）、`apply-and-tracking`（投递与记录）、`local-dashboard`（看板与 API）、`online-sync`（表格同步）。
理由：模块边界清晰、便于后续按域出 delta；备选方案是合并为 1~2 个大 spec，粒度太粗会导致后续任何小改动都要重写整份规格，故弃用。

**以 ADDED delta 作为基线载体，经 apply 合并进主规格。**
主规格当前为空，用标准变更流程（new change → delta specs → apply）生成基线，保证 `openspec/` 的校验与归档机制从一开始就生效；不手工直接写 `openspec/specs/`。

**规格只写可观察行为，不写选择器/类名/实现细节。**
平台页面结构易变（BOSS/实习僧改版、51job WAF），把"必须验证成功""未登录必须阻塞"这类契约写进规格，而把 DOM 选择器等易变内容留在代码与 `references/` 中。

**`config.yaml` 写入项目上下文。**
技术栈、数据本地化、登录门禁铁律、状态机等作为约束注入后续所有产物生成，避免 AI 生成与项目相悖的设计。

## Risks / Trade-offs

- 规格与实际代码可能随迭代漂移 → 本基线先经人工 review 校对；后续每次变更的 apply 会持续以 delta 更新主规格，漂移在变更时收敛
- 外部平台改版可能让部分行为描述过时 → 规格描述行为契约而非页面结构，改版只影响代码实现，不改规格表述
- 能力域边界划分是主观决策 → 已在 proposal 与本文档明确依据，后续如发现更优边界，用新变更调整而不是在基线里打补丁

## Migration Plan

1. 人工评审 proposal 与 6 份 delta spec，逐条对照代码确认行为描述准确
2. `openspec validate` 通过后执行 apply，将 delta 合并进 `openspec/specs/`
3. archive 归档本变更；此后进入"新变更 → delta → apply"的常规循环

## Open Questions

无（本变更为纯规格化基线，不引入需要延后决策的未知项）。
