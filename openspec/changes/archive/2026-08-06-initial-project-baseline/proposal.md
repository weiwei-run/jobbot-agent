## Why

JobBot Agent 已经具备完整的本地 AI 求职自动化能力（三平台搜索、LLM 评分、自动投递、看板追踪、在线表格同步），但从未有过规格化文档：能力边界、状态机、登录门禁等关键行为只散落在代码和运行手册里。本次变更把现有已实现行为固化为 OpenSpec 主规格基线，为后续每一次改动提供"当前系统应该做什么"的对照基准。

## What Changes

- 建立 6 个能力域的主规格（以 delta 形式新增，待 apply 合并进 `openspec/specs/`）：
  - `user-config`：LLM 配置、用户画像与意向、简历上传解析、平台规则配置
  - `platform-automation`：Camofox 浏览器客户端、登录门禁与登录状态检测、环境检测
  - `job-search`：关键词生成、三平台搜索（含 WAF 降级）、去重、硬指标过滤、LLM 评分、岗位有效性校验
  - `apply-and-tracking`：自动投递与成功验证、投递记录管理、状态机流转、在线同步触发
  - `local-dashboard`：本地 Web 看板与 API、统计筛选、CSV 导出、后台任务进度、登录引导
  - `online-sync`：投递记录同步到 webhook / 飞书多维表格
- 生成基线设计文档 `design.md` 与评审/归档任务清单 `tasks.md`
- 不改动任何项目代码，纯规格化基线

## Capabilities

### New Capabilities
- `user-config`: 本地配置与用户画像——LLM 端点/模型/Key、求职意向、简历上传与结构化解析、平台搜索规则（platforms.yml）
- `platform-automation`: 反检测浏览器自动化底座——Camofox 服务检测/启动、标签页与 JS 操作、平台登录检测与登录门禁、环境状态上报
- `job-search`: 搜索与匹配管线——意向生成 5~8 关键词、三平台并发搜索、跨平台去重、硬指标（学历/年限/地域）过滤、LLM 1~5 星评分、下线岗位校验
- `apply-and-tracking`: 投递与追踪——三平台自动投递并验证成功状态、唯一数据源 `data/applications.json`、状态机流转、记录增改触发在线同步
- `local-dashboard`: 本地看板——单文件 Web 界面（端口 9379）、LLM/意向/同步设置、搜索与投递操作、统计与筛选、CSV 导出、后台搜索任务进度
- `online-sync`: 在线表格同步——webhook JSON 推送与飞书多维表格批量写入，异步执行不阻塞投递

### Modified Capabilities

- 无（主规格为空，本次全部为新增）

## Impact

- 代码零改动；仅新增 `openspec/specs/` 下 6 个能力规格与本次变更的规划产物
- 无 API、依赖或运行时行为变化
- 后续所有变更将以本基线规格为对照；已识别但未实现的方向（回复工作流、手动投递自动识别、更多平台扩展）不纳入本次基线
