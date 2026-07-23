# JobBot Agent — 产品设计说明书

> 开源通用版。本文档定义产品要做什么、长什么样、怎么工作。

---

## 一、产品定位

### 一句话

**加载到 AI Agent 里的求职技能包——用户说"帮我找工作"，Agent 自动搜三平台、评分、投递、回消息、追进度。**

### 目标用户

- 应届生 / 在校生找实习
- 工作 1-3 年的人换工作
- 帮孩子找实习的家长（由家长操作）

### 不是 SaaS

不部署服务器。全部跑在用户本地：
- 用户自己的 AI Agent（Hermes / OpenCode / Claude Code）
- 用户自己的浏览器（Playwright + Firefox）
- 用户自己的 API key
- 投递记录存本地 JSON，看板是本地 HTML
- **无需 Camofox、无需 npm、零翻墙依赖**

### 环境安装

Agent 加载技能包后自动执行，用户无需手动操作：

```bash
pip install playwright        # 3MB, 纯 Python
playwright install firefox    # 116MB, CDN 国内直连
```

`scripts/setup.py` 检测环境 → 缺失自动安装。安装失败时显示「请手动运行」并继续（51job + 实习僧 仍可用）。

### 当前阶段

技能包形态（v1.0 已发布）。后续可演进为独立 GUI 工具。

---

## 二、用户体验

### 2.1 首次使用：配置向导

```
用户加载 skill → Agent 说"你好我是 JobBot，帮你找工作"

Agent 引导用户提供信息（选一种）：
  A) 上传简历文件（PDF/Word/TXT）→ 自动解析
  B) 逐项问答：学历、专业、毕业年份、目标城市、意向岗位、薪资范围

Agent 展示解析结果，让用户确认。
Agent 自动生成 5~8 个搜索关键词，让用户调整。
Agent 保存到本地 config/user_profile.json。
Agent 说："配置完成！说「搜岗位」开始。"
```

### 2.2 日常使用：两个循环

#### 投递循环（主动出击）

```
用户："搜岗位"

Agent:
  ① 读 config/user_profile.json
  ② 按关键词在 51job → BOSS直聘 → 实习僧 逐个搜索
  ③ 规则粗筛（排除猎头/普工/销售/不相关）
  ④ LLM 精评（对比 JD 和简历，1~5 星）
  ⑤ 展示评分，用户确认投哪些
  ⑥ 逐个投递，验证成功
  ⑦ 更新本地 applications.json + 在线表格
  ⑧ 刷新 Dashboard
```

#### 回复循环（被动响应）

```
用户："检查消息"

Agent:
  ① 打开各平台检查未读消息
  ② 场景分类（打招呼/要简历/问技能/约面试/拒绝…）
  ③ AI 生成回复（去 AI 味，学生语气）
  ④ 展示给用户审核
  ⑤ 用户确认 → 发送 + 发简历附件
  ⑥ 面试邀约 → 高亮提醒，不私自确认
```

### 2.3 期望的对话体验

```
用户：帮我找工作
JobBot：你好！请告诉我你的基本情况，或者上传简历。

用户：张三，本科计算机，2027年毕业，南京，后端开发实习
JobBot：✅ 已生成配置。搜索关键词：Java后端、Python开发、Golang实习…
       现在开始搜索吗？

用户：搜
JobBot：【51job】找到 23 个 → 评分中…
       【BOSS直聘】找到 15 个 → 评分中…
       【实习僧】找到 5 个 → 评分中…
       
       ⭐⭐⭐⭐⭐ 2个  ⭐⭐⭐⭐ 5个  ⭐⭐⭐ 8个
       要投哪些？"全投" / "投前3个" / "跳过XX公司"

用户：投前3个
JobBot：✅ 3个投递成功。看板已更新 → data/dashboard.html

用户：检查消息
JobBot：BOSS 有 2 条新消息：
       ① 南暄禾雅 HR："你好啊，可以聊一聊～"
          建议："好的，计算机本科，南京随时到岗，发简历您看下？"
       ② XX科技 HR：约面试 7/20 下午 2 点 ⚠️ 需要确认！
```

---

## 三、Dashboard（本地 Web 看板）

### 3.1 定位

用户打开 `data/dashboard.html`（或 `python dashboard.py` 启动本地服务），看到：
- 投了哪些
- 哪些回了
- 哪些约面试了
- 今天/本周/总计统计

**不需要登录，纯本地 HTML，打开即看。**

### 3.2 页面布局

```
┌──────────────────────────────────────────────────────┐
│  JobBot Dashboard                       [刷新] [设置] │
├──────────┬──────────┬──────────┬─────────────────────┤
│  总投递  │  HR回复  │  面试中  │   今日新增           │
│   42     │    8     │    2     │    3               │
├──────────┴──────────┴──────────┴─────────────────────┤
│                                                       │
│  📊 投递进度（按状态）                                 │
│  ████████████████░░░░  已投递 25                       │
│  ████████░░░░░░░░░░░░  HR已读 12                      │
│  ██████░░░░░░░░░░░░░░  已回复 8                        │
│  ██░░░░░░░░░░░░░░░░░░  面试中 2                        │
│                                                       │
├───────────────────────────────────────────────────────┤
│  📋 最近投递                                           │
│  公司        │ 岗位         │ 平台   │ 状态     │ 时间  │
│  ───────────┼──────────────┼───────┼─────────┼────── │
│  南暄禾雅    │ 电气工程师    │ BOSS  │ ✅ 已回复 │ 07-21 │
│  博睿光电    │ PLC调试      │ 51job │ ⏳ 已投递 │ 07-21 │
│  一山高      │ 设备维护     │ BOSS  │ 📅 面试  │ 07-20 │
│                                                       │
├───────────────────────────────────────────────────────┤
│  ⚠️ 需要处理                                          │
│  · 南暄禾雅 HR 发了新消息："什么时候能到岗？"          │
│  · XX科技 约面试 7/25 — 待确认                         │
└───────────────────────────────────────────────────────┘
```

### 3.3 页面交互

| 操作 | 行为 |
|------|------|
| 点击某条记录 | 展开详情（JD 摘要、回复历史、评分） |
| 刷新按钮 | 从 `applications.json` 重新渲染 |
| 设置按钮 | 打开 `config/user_profile.json` 编辑界面 |
| 导出按钮 | 导出 CSV |

### 3.4 Dashboard 技术方案

- 单文件 HTML + 内联 JS + 内联 CSS
- 数据源：`data/applications.json`
- 可选：`python dashboard.py` 启动本地 HTTP 服务（仅当需要在同一网络下其他设备查看时）
- 不依赖任何框架，零 npm install

---

## 四、技术架构

### 4.1 整体架构

```
用户 ←→ AI Agent (Hermes/OpenCode/Claude Code)
              │
              ├── 加载 SKILL.md / AGENTS.md（指令）
              │
              ├── 读 config/user_profile.json（用户画像）
              ├── 读 config/platforms.yml（平台配置）
              │
              ├── 操作浏览器（Playwright + Firefox）
              │   ├── 搜索岗位
              │   ├── 投递/沟通
              │   └── 检查消息/回复
              │
              ├── ⚠️ 平台登录阻塞 — 不绕过，等用户手动登
              │
              ├── 写 data/applications.json（投递记录）
              │
              └── 生成 data/dashboard.html（看板）
```

**关键原则：逻辑在 SKILL.md 里，Agent 按指令执行。不写死成 Python 代码。**

### 4.2 文件结构

```
jobbot-agent/
├── SKILL.md              ← 技能指令（Agent 读这个就知道怎么做）
├── AGENTS.md             ← OpenCode/Claude Code 版指令
├── PRODUCT.md            ← 本文件（产品设计说明）
├── README.md             ← 面向用户的介绍
├── SETUP.md              ← 安装指南
├── requirements.txt      ← Python 依赖（仅脚本需要）
│
├── config/
│   ├── user_profile_template.json  ← 简历模板（用户复制后填）
│   └── platforms.yml              ← 平台配置（搜索规则等）
│
├── references/           ← Agent 的参考手册
│   ├── boss-pitfalls.md           ← BOSS 直聘各种坑
│   ├── wuyou-api.md               ← 51job API 文档
│   ├── wuyou-search.md            ← 51job 浏览器搜索方案
│   ├── reply-sop.md               ← 回复话术 SOP
│   └── trust-detection.md         ← 诈骗检测规则
│
├── scripts/
│   ├── setup.py                   ← 环境检测
│   └── report.py                  ← 生成 Dashboard HTML
│
├── dashboard.py          ← 本地 Dashboard HTTP 服务（可选）
│
└── data/                 ← 用户数据（本地，不上传）
    ├── applications.json  ← 投递记录
    └── dashboard.html     ← 看板（自动生成）
```

### 4.3 数据模型

`data/applications.json`：

```json
{
  "user": {
    "name": "string",
    "education": "string",
    "major": "string",
    "graduation": "string",
    "city": "string"
  },
  "applications": [
    {
      "id": "uuid",
      "company": "string",
      "position": "string",
      "platform": "boss|wuyou|shixiseng",
      "url": "string",
      "jd_summary": "string",
      "salary": "string",
      "location": "string",
      "score": 1-5,
      "status": "discovered|applied|hr_read|hr_replied|interviewing|offered|rejected",
      "contact_person": "string|null",
      "contact_phone": "string|null",
      "applied_at": "ISO8601",
      "last_update": "ISO8601",
      "messages": [
        {
          "from": "hr|me",
          "content": "string",
          "time": "ISO8601"
        }
      ],
      "notes": "string"
    }
  ],
  "stats": {
    "total_applied": 0,
    "hr_replied": 0,
    "interview_scheduled": 0,
    "rejected": 0
  }
}
```

---

## 五、Dashboard 详细设计

### 5.1 状态流转

```
DISCOVERED → APPLIED → HR_READ → HR_REPLIED → INTERVIEWING → OFFERED
                                                     ↓
                                                REJECTED
```

### 5.2 看板数据刷新

- `python scripts/report.py` 读取 `applications.json` → 生成 `dashboard.html`
- 每次投递/回复后自动运行
- Dashboard 打开时每 30 秒自动刷新（轮询 `applications.json` 的 mtime）

### 5.3 筛选和排序

- 按状态筛选：全部 / 已投递 / 已回复 / 面试中 / 已拒绝
- 按平台筛选：全部 / BOSS / 51job / 实习僧
- 按评分排序
- 按时间排序（默认最新在前）

---

## 六、当前问题清单

以下是当前实现与本文档描述的差距：

### 6.1 Dashboard 不完整

- 当前 `dashboard.py` 只是简陋的 HTTP 服务 + 内联 HTML
- 缺少筛选、排序、展开详情
- 缺少统计数据可视化
- `applications.json` 是空的（没有真实数据）

### 6.2 配置向导未独立

- 当前依赖 Agent（Hermes/OpenCode）一步一步问
- 没有一个独立的配置页面（用户可以直接打开 dashboard 填简历）

### 6.3 浏览器依赖未处理

- 用户机器可能没装 Playwright + Firefox
- `setup.py` 需自动检测 + 安装（`pip install playwright && playwright install firefox`）
- 安装失败 → 提示手动运行，51job + 实习僧 仍可用
- BOSS 直聘需要登录 Cookie 持久化，登录过期时阻塞等用户手动操作，**不尝试绕过**

### 6.4 三平台接入

三端统一：Playwright + Firefox，同一浏览器引擎。首次使用各平台需手动登录一次，Cookie 持久化后续复用。

| 平台 | 搜索 | 投递 | 消息 | 注意 |
|------|------|------|------|------|
| BOSS直聘 | ✅ | ✅ | ✅ | 首次登录阻塞等用户 |
| 前程无忧(51job) | ✅ | ✅ | ✅ | API 被 WAF 拦截，走浏览器 |
| 实习僧 | ✅ | ✅ | ⚠️ | SSR+字体解码，消息暂未验证 |

### 6.5 ⚠️ 平台登录铁律

遇到任何平台跳转登录页 → **立即停止，通知用户手动登录。不尝试自动填充验证码、不绕过、不换方案。** 登录完成后用户告知 Agent 继续。

### 6.6 缺少统一入口

- 用户需要先装 Agent → 加载 skill → 对话启动
- 没有一个 `python start.py` 一键启动的体验

### 6.7 缺少导出功能

- 没有 CSV 导出
- 没有投递报告生成

---

## 七、改造目标

基于本文档，需要完成以下改造：

| # | 改造项 | 优先级 |
|---|--------|--------|
| 1 | 重写 Dashboard（单文件 HTML，完整功能） | P0 |
| 2 | 配置向导独立化（Dashboard 内嵌简历编辑） | P0 |
| 3 | `applications.json` 作为唯一数据源，废弃腾讯文档写入 | P0 |
| 4 | `setup.py` 自动安装浏览器依赖（Playwright + Firefox） | P0 |
| 5 | `python start.py` 一键启动（Dashboard + 环境检测） | P1 |
| 6 | 投递记录 CSV 导出 | P1 |
| 7 | SKILL.md 精简，完全参数化 | P1 |
| 8 | Dashboard 内嵌消息查看/回复审核台 | P2 |

---

*文档版本：v1.0 · 2026-07-22 · 待主人审阅*
