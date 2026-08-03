# JobBot Agent — 本地 AI 求职助手

一个下载即用、完全跑在你自己电脑上的求职自动化工具：配置一次 LLM API Key，上传简历、填写意向，就能在 **BOSS直聘 / 前程无忧(51job) / 实习僧** 三大平台搜索岗位、AI 评分、一键自动投递，并把投递进度同步到本地看板和在线表格。

> 数据全部留在本地，只有调用 LLM 和搜索/投递岗位时需要联网。

---

## 它能做什么

| 能力 | 说明 |
|------|------|
| 三平台搜索 | 51job（HTTP API + WAF 自动降级）、BOSS直聘 / 实习僧（Camofox 浏览器） |
| AI 智能评分 | LLM 对比 JD 与你的简历，1~5 星，只展示值得投的岗位 |
| 一键自动投递 | 点「投递」自动打开岗位并操作投递，成功后验证「已发送/投递成功」 |
| 简历解析 | 上传 TXT / Word / PDF，自动提取姓名、学历、专业、技能填到意向里 |
| 投递看板 | 本地 Dashboard：总览统计、状态流转（已投递→已回复→约面试→Offer/拒绝）、筛选、CSV 导出 |
| 在线表格同步 | 投递记录自动推送到 Webhook 或飞书多维表格 |
| 诈骗检测 | 关键词/薪资虚高识别，可疑岗位打标提示 |
| 登录门禁 | 平台未登录/验证码时明确提示，绝不绕过 |

---

## 快速开始（三步）

### 1. 环境要求

- Windows / macOS / Linux
- Python 3.10+（https://python.org）
- Node.js 16+（仅自动投递与 BOSS/实习僧搜索需要，用于 Camofox 浏览器）

### 2. 启动

```bash
python start.py
```

浏览器自动打开 `http://localhost:9379`。

### 3. 在页面里完成三件事

1. **配置 AI**：填写 LLM Base URL + API Key（DeepSeek / Kimi / 通义 / OpenAI 等任何 OpenAI 兼容接口），点「测试连接」。
2. **上传简历 / 填写意向**：上传简历（或直接写"本科计算机，南京后端实习，Python"），点「保存意向」。
3. **搜索与投递**：点「开始搜索」→ 查看 AI 评分结果 → 点「🚀 投递」自动投递；或点「加入记录」手动记录。

> 51job 搜索无需登录；BOSS直聘 / 实习僧 搜索与三大平台自动投递需要安装 Camofox 浏览器并登录一次（页面「检测环境」会引导）。投递前请确认各平台简历已完善。

**登录门禁**：遇到平台未登录时，JobBot **不会自动登录、不填验证码、不绕过**。它会：把浏览器停在登录页 → 在 Dashboard 显示「🔐 需要手动登录」提示 → 等你手动登录完成后点「已登录，继续」→ 再继续搜索/投递。未确认登录前不会执行任何投递操作。

---

## 在线表格同步

在 Dashboard「在线表格同步」设置：

- **Webhook**：填任意 webhook 地址（可对接 Zapier / Make / 自建服务），每次新增/更新记录推送 JSON。
- **飞书多维表格**：在 open.feishu.cn 创建企业自建应用 → 开通多维表格权限 → 填入 app_id / app_secret / 多维表格 app_token / table_id。

开启后，新增投递或更新状态会自动同步。

---

## 目录结构

```
jobbot-agent/
├─ start.py              # 一键启动（端口冲突自动检测）
├─ dashboard.py          # 本地看板（单文件，纯 stdlib）
├─ engine.py             # 核心引擎：关键词/搜索/评分/记录/状态
├─ platforms.py          # 三平台搜索 + 自动投递（含 WAF/登录墙处理）
├─ browser.py            # Camofox 浏览器客户端
├─ llm.py                # OpenAI 兼容 LLM 客户端
├─ spreadsheet.py        # 在线表格同步（webhook / 飞书）
├─ config/
│  ├─ platforms.yml      # 平台开关与过滤规则（标题/薪资/学历/信任检测）
│  ├─ llm.json           # LLM 配置（本地，不入库）
│  ├─ settings.json      # 在线表格同步配置（本地，不入库）
│  └─ user_profile.json  # 求职意向（本地，不入库）
├─ data/                 # 投递记录与看板数据（本地）
└─ references/           # 平台对接参考资料
```

## 配置说明

- `config/platforms.yml`：每个平台的 `enabled` 开关、`title_filter.negative` 排除词、`salary_filter` 薪资范围、`education_allow` 学历白名单、`trust_filter` 信任检测关键词。排除词按你的求职方向调整（例如找技术岗时不要放 Java/Python）。
- `config/llm.json`：可在 Dashboard 填写，也可直接编辑；支持任意 OpenAI 兼容接口。

## 已知边界

- BOSS直聘 / 实习僧 的页面结构可能随平台改版变化，搜索或投递失败会给出明确提示，请按提示人工处理。
- 频繁操作可能触发平台风控（IP 封禁/验证码），遇到时放慢节奏或更换网络。
- 自动投递依赖 Camofox 浏览器（约 150MB），仅投递功能需要安装。

## 许可

MIT © 2026 weiwei-run
