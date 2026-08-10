# JobBot Agent × Agent 工具接入指南

> 给电脑上已经装了 AI Agent 工具（OpenCode、Codex、Claude Code、Cursor、WorkBuddy 等）的用户：怎么让 agent 帮你操作和维护 JobBot。

## 一、先说结论

JobBot 这个项目本身就是"为 agent 协作而组织"的：根目录的 `AGENTS.md` 是给 agent 看的协作约定，`SKILL.md` / `PRODUCT.md` 说明产品，`run-log.md` 记录每次运行历史，`openspec/` 是规格化变更追踪，`scripts/` 有自测与 OCR 脚本。

**用法一句话**：把 `jobbot-agent` 文件夹作为 agent 的工作目录/项目打开，然后直接对话。大多数 agent 会自动读取 `AGENTS.md` 并按约定工作。

## 二、怎么把 JobBot 交给 agent

### 通用步骤（所有 agent 适用）

1. 获取代码（同用户手册）：

   ```bash
   git clone https://github.com/weiwei-run/jobbot-agent.git
   cd jobbot-agent
   ```

2. 把当前目录设为 agent 的工作区/项目根目录。
3. 让 agent 先读这几个文件（多数会自动读，没读就让它读）：
   - `AGENTS.md` —— 协作约定（最重要）
   - `README.md` / `PRODUCT.md` —— 是什么、怎么用
   - `run-log.md` —— 之前跑过什么、踩过什么坑
   - `openspec/` —— 正在进行的变更与规格

### 分工具说明

**OpenCode**

```bash
cd jobbot-agent
opencode
```

进入对话后直接说需求即可（OpenCode 自动加载 `AGENTS.md`）。

**Codex CLI / Codex 桌面端**

```bash
cd jobbot-agent
codex
```

或在桌面端"打开项目"选择 `jobbot-agent` 目录。

**Claude Code / Cursor / WorkBuddy 等**

把 `jobbot-agent` 目录作为项目/工作空间打开。若工具默认不读 `AGENTS.md`（部分工具读 `CLAUDE.md` 等），第一句话让它"先读根目录 AGENTS.md、README.md、PRODUCT.md、run-log.md，再开始"。

## 三、可以让 agent 帮你做什么

### 日常使用类

- "帮我启动 JobBot" → agent 执行 `python start.py`
- "看看最近的运行日志/有什么问题" → 读 `run-log.md`
- "帮我把意向改成……" → 修改 `config/user_profile.json`（注意格式是 JSON）
- "统计一下投递记录里约面试的有几家" → 分析 `data/applications.json`
- "我发一张截图，帮我看看页面哪里不对" → 发**图片文件路径**，agent 会按约定先跑 `scripts/ocr_image.ps1` 识别再回答（当前模型不支持直接看图）

### 排查与维护类

- "搜索报"未解析到岗位"，帮我查一下平台解析逻辑" → agent 检查 `platforms.py`
- "跑一遍自测" → `python -B scripts/selftest_scoring.py`
- "更新一下 run-log，记录今天这次运行"
- "把改动提交并同步 GitHub 和 Gitee 两个仓库"（项目配置了双远程：`origin` + `gitee`）

### 开发迭代类（按项目约定）

JobBot 的 `AGENTS.md` 规定：**改变用户可见行为/数据格式/外部接口的改动，必须走 OpenSpec 完整流程**。你只要说"我想加个 XX 功能"，agent 会：

1. 创建变更提案（`openspec new change`）；
2. 生成 proposal / 规格 / 设计 / 任务清单，**先给你确认**；
3. 确认后实现 → 跑 `openspec validate` → 合并规格 → 归档。

纯重构/小修可以直接改并记入 `run-log.md`。

## 四、JobBot 给 agent 划的红线（agent 会遵守）

- **登录门禁**：绝不自动登录、不填验证码、不绕过登录墙；未登录时停下来提示你手动登录。
- **数据本地化**：`config/llm.json`、`config/user_profile.json`、`data/` 里的简历与记录都是你的隐私，只在本地使用。
- **投递由你完成**：当前产品定位下 agent/JobBot 不自动投递，只提供岗位链接和「加入记录」。
- **诚实反馈**：评分失败、风控、解析失败都会如实标注，不编造结果。
- **中文优先**：界面文案与注释用中文。

## 五、示例对话

**日常：**

> 用户：帮我看看今天应该搜什么关键词，我简历是电气自动化大专，找南京实习，会 PLC 和 ABB 机器人。
>
> Agent：读 `config/user_profile.json` 确认画像 → 建议关键词：工业机器人调试、ABB机器人编程、PLC调试、电气技术员…（如需可直接改意向后跑 `python start.py` 搜索）

**排查：**

> 用户：实习僧又搜不到岗位了，之前也是。帮我看看是不是页面结构变了。
>
> Agent：查看 `run-log.md` 历史记录 → 检查 `platforms.py` 里实习僧的抽取 JS 与选择器 → 对照当前页面结构给出修复或建议，并按约定走变更流程。

**变更：**

> 用户：我想在结果卡片上加一个"公司规模"字段，看看可行性。
>
> Agent：先进入探索/提案模式，整理需求 → 生成 OpenSpec 提案给你确认 → 确认后实现。

## 六、注意事项

- Agent 用的是**它自己的模型和 API 配置**，和 JobBot 里配的 LLM Key 是两回事；别把 JobBot 的 Key 贴给 agent 之外的人。
- 让 agent 改 `config/`、`data/` 前，自己先备份（复制一份即可）。
- 项目同时推 GitHub 和 Gitee，让 agent 同步时它会两个都推（`git push origin main` + `git push gitee main`）。
- 如果 agent 工具读不到 `AGENTS.md`，把文件内容贴给它，或明确要求"先读 AGENTS.md 再执行任务"。
