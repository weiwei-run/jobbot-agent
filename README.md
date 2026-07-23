# JobBot Agent — 开源通用求职技能包

## 定位

一个可分发到任何 AI Agent（Hermes / OpenCode / Claude Code / OpenClaw）的技能包。
用户提供自己的简历和意向岗位 → Agent 自动对接三平台（BOSS直聘/前程无忧/实习僧）搜索、评分、投递、回复、追踪。

---

## 它能做什么

| 能力 | 说明 |
|------|------|
| **三平台搜索** | BOSS直聘 + 前程无忧(51job) + 实习僧，关键词自动轮换，结果去重 |
| **智能评分** | LLM 对比 JD 和你的简历，1~5 星评分，只投真正匹配的 |
| **一键投递** | 确认后自动点击投递，实时验证投递成功状态 |
| **自动回复** | HR 消息自动识别意图（12 种场景），生成自然回复，去 AI 味 |
| **发简历** | 自动处理弹窗、选择文件、发送，验证发送成功 |
| **面试通知** | 检测到面试邀约立即提醒，不私自确认时间 |
| **状态看板** | 本地 HTML 看板，投递/回复/面试状态一目了然 |
| **诈骗检测** | 自动识别培训贷、押金诈骗、薪资虚高等可疑岗位 |
| **零服务器** | 全部跑在本地，数据不上传，Agent 和 API key 都是你自己的 |

---

## 支持平台

| 平台 | 接入文件 | 安装方式 | 一句话启动 |
|------|---------|---------|-----------|
| **OpenCode** | `AGENTS.md` | 放到项目目录或 `~/.config/opencode/AGENTS.md` | `opencode` 启动后说"帮我找工作" |
| **Hermes** | `SKILL.md` | `skill_view('jobbot')` 加载 | 说"加载 jobbot 技能" |
| **OpenClaw** | `SKILL.md` | 放到 `~/.openclaw/skills/jobbot/` | 说"用 jobbot 帮我找工作" |
| **Claude Code** | `AGENTS.md` | 项目根目录 `CLAUDE.md` 写入 `@AGENTS.md` | `claude` 启动后说"帮我找工作" |

> 💡 不锁定平台。Skill 文件是通用 Markdown，任何能读文件的 AI Agent 都能用。

---

## 快速开始

### 前提条件

- Python 3.10+
- 一个已安装的 AI Agent（Hermes / OpenCode / Claude Code / OpenClaw）
- Playwright 浏览器

### 三步跑起来

```bash
# 1. 安装依赖
pip install -r requirements.txt
playwright install chromium

# 2. 环境检测
python scripts/setup.py

# 3. 填写简历
cp config/user_profile_template.json config/user_profile.json
# 编辑 user_profile.json，填写你的基本信息
```

### 加载到你的 Agent

```bash
# OpenCode（推荐 — 社区最大，安装最简单）
cp AGENTS.md ~/.config/opencode/AGENTS.md
opencode
# 输入：帮我找工作

# Hermes
# 在对话中说：加载 jobbot 技能

# OpenClaw
mkdir -p ~/.openclaw/skills/jobbot
cp SKILL.md ~/.openclaw/skills/jobbot/

# Claude Code
echo "@AGENTS.md" > CLAUDE.md
claude
```

详细安装指南见 [SETUP.md](SETUP.md)。

---

## 招聘平台

| 平台 | 搜索方式 | 投递方式 | 风险 | 状态 |
|------|---------|---------|------|------|
| **BOSS直聘** | 浏览器操作 | JS 事件派发 | IP 封禁风险 | ✅ |
| **前程无忧(51job)** | 纯 API（零验证码） | 浏览器点击 | 低 | ✅ |
| **实习僧** | SSR + 字体解码 | 浏览器投递 | 低 | ✅ |
| 智联招聘 | — | — | — | 待接入 |

---

## Agent 对话示例

```
你：帮我找工作
Agent：你好！我是 JobBot 求职助手。请告诉我你的基本信息……

你：我叫张三，本科计算机，2027年毕业，想在南京找后端开发实习
Agent：✅ 配置完成！已生成 7 个搜索关键词。现在开始搜索吗？

你：搜
Agent：【搜索中…】BOSS 找到 15 个，51job 找到 23 个，实习僧 5 个
      【评分完成】⭐⭐⭐⭐⭐ 2个，⭐⭐⭐⭐ 5个，⭐⭐⭐ 8个
      要投哪些？"全投" / "投前3个" / "跳过XX公司"

你：投前5个
Agent：【投递中…】✅ 5个投递成功，看板已更新
      data/dashboard.html

你：检查消息
Agent：【扫描中…】BOSS 有 2 条新消息，51job 有 1 条
      南暄禾雅 HR："你好啊，可以聊一聊~"
      我的建议回复："好的您好。我是计算机本科，已经在南京了随时到岗。我发一下简历您看看？"
      要发吗？

你：发
Agent：✅ 已发送 + 简历已发
```

---

## 文件结构

```
jobbot-agent/
├── SKILL.md                    ← Hermes / OpenClaw 技能文件
├── AGENTS.md                   ← OpenCode / Claude Code 指令文件
├── README.md                   ← 本文件
├── SETUP.md                    ← 详细安装指南
├── requirements.txt            ← Python 依赖
├── config/
│   ├── user_profile_template.json  ← 简历模板
│   └── platforms.yml              ← 平台配置
├── references/                     ← 参考文档
│   ├── boss-pitfalls.md            ← BOSS 直聘陷阱全解（13个）
│   ├── wuyou-api.md                ← 51job API 完整文档
│   ├── reply-sop.md                ← 回复话术 SOP（12种场景）
│   └── trust-detection.md          ← 诈骗岗位检测规则
├── scripts/
│   ├── setup.py                    ← 一键环境检测
│   └── report.py                   ← HTML 看板生成
└── data/                           ← 投递记录（本地生成）
```

---

## 操作铁律

Agent 在运行 JobBot 时必须遵守：

1. **投递后必须验证** — 不假设成功，每次检查发送状态
2. **回复必须去 AI 味** — 学生语气，简短自然。不说"感谢您的关注""希望能跟着前辈学习"
3. **面试邀约立即通知** — 不私自确认时间，等用户决策
4. **每次重读配置** — 用户可能改了简历或偏好，不依赖记忆
5. **遇到障碍主动告知** — 登录过期/验证码/IP封禁 → 通知用户，不卡死

---

## 项目故事

手动搜索、浏览、投递、回复 HR 消息，每天花 2-3 小时。用 AI Agent 自动化后，整个流程压缩到 30 分钟。支持三平台，开源可分发。

如果你也在找工作，或者在帮家人朋友找——试试让 AI 帮你跑。

---

## 许可证

MIT © 2026 weiwei-run
