# AGENTS.md — jobbot-agent 协作约定

本文件会在每次 Codex/agent 会话启动时自动加载。约定生效日期：2026-08-06。

## OpenSpec 变更流程约定

本仓库用 OpenSpec 做规格化变更追踪。主规格在 `openspec/specs/`（6 个能力域基线已于
2026-08-06 归档），项目上下文在 `openspec/config.yaml`。

一次改动走哪种流程，用一条标准判定：

> 是否改变用户可见行为、数据格式或外部接口？
> 是 → 完整 OpenSpec 流程；否 → 轻量处理。

### 完整流程（改变行为契约）

1. `openspec new change <kebab-case-name>`
2. 按 `openspec instructions` 生成 proposal / specs(delta) / design / tasks，等用户确认
3. 实现 → `openspec validate` → 合并 delta 进 `openspec/specs/` → 归档到 `openspec/changes/archive/YYYY-MM-DD-<name>`

### 轻量流程（行为契约不变：纯重构 / 性能 / 微修复）

- 开 change 但 `.openspec.yaml` 加 `skip_specs: true`，只写 proposal + tasks；或
- 超小修复（typo、一行级）：直接修 + 在 `run-log.md` 记录一笔

### 修复 bug 时

- 修复"实现不符合 spec 的 bug"：spec 不变，按轻量流程处理
- 修复改变了行为契约：必须走完整流程（delta spec）
- 修复暴露了 spec 未覆盖的行为：先补 spec，再修代码

## 本机环境注意事项

- PowerShell 沙箱里 `openspec` 会命中被执行策略拦截的 `.ps1`，一律用 `openspec.cmd` 调用
- 本机 `openspec archive` 报目录重命名 EPERM（Node CLI 句柄问题）：不要卡住，
  改用手动流程——先合并 delta 到 `openspec/specs/`，再用 `Move-Item` 把变更目录
  移到 `openspec/changes/archive/YYYY-MM-DD-<name>`

## 项目铁律（详见根目录 SKILL.md / PRODUCT.md）

- 登录门禁：绝不自动登录、不填验证码、不绕过登录墙
- 投递后必须验证成功状态，不假设成功
- 数据本地化：密钥/简历/记录只存本地，`config/llm.json`、`data/resume/` 等不入库
- 中文注释与界面文案；JSON/YAML 统一 UTF-8

## 图片自动识别（OCR）约定

- 当前 Codex 走 DeepSeek 模型，**不支持图片输入**，不要依赖 `view_image` 等视觉工具。
- 用户消息中出现图片附件、粘贴的截图或本地图片路径（`.png/.jpg/.jpeg/.bmp/.gif/.webp`）时，
  **必须先运行** `powershell -ExecutionPolicy Bypass -File scripts/ocr_image.ps1 <图片路径>`
  提取文字，再基于 OCR 结果回复；不得跳过识别或猜测图片内容。
- 多张图片逐个识别；若识别失败或文字为空，如实告知用户，并请其提供文字版内容。
- 若用户直接粘贴图片导致模型侧报错，提示用户改为把图片文件路径发过来。
