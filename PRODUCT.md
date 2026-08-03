# JobBot Agent — 产品设计说明

## 一句话定位

下载即用的本地 AI 求职助手：用户配置一次 LLM API Key → 上传简历/填意向 → 三大平台搜索评分 → 一键自动投递 → 看板追踪 → 在线表格同步。

## 目标用户

- 应届生 / 在校生找实习
- 工作 1-3 年换工作的人
- 帮孩子找实习/工作的家长

## 核心原则

- 本地优先：数据、Key、记录都在用户电脑上。
- 配置极简：只要求 LLM API Key；平台登录按需一次。
- 诚实反馈：登录墙、风控、验证码都明确提示，不静默失败、不绕过。
- 登录门禁：未登录时自动停在登录页并在 Dashboard 提示手动登录；用户确认「已登录，继续」后才继续搜索/投递。
- 投递必验证：自动投递后校验「已发送 / 投递成功」才算成功。

## 用户流程

```
python start.py → http://localhost:9379
  ① 填 LLM Base URL + API Key → 测试连接
  ② 上传简历（TXT/Word/PDF）→ 自动解析 → 编辑意向 → 保存
  ③ 开始搜索：AI 生成 5~8 关键词 → 三平台搜索 → 规则过滤 → LLM 1~5 星评分
  ④ 逐条「🚀 投递」（Camofox 自动操作 + 验证）或「加入记录」（手动投递）
  ⑤ 看板记录状态流转：discovered → applied → hr_replied → interview_scheduled → offered/rejected
  ⑥ 每次记录变化自动同步在线表格（webhook / 飞书）
```

## 状态模型

```
DISCOVERED → APPLIED → HR_REPLIED → INTERVIEW_SCHEDULED → OFFERED
                                     ↘ REJECTED
```

看板支持平台/状态筛选、评分与时间排序、详情展开、CSV 导出。

## 平台接入现状

| 平台 | 搜索 | 投递 | 登录要求 |
|------|------|------|---------|
| 51job | HTTP API → WAF 拦截时 Chrome headless | Camofox 点击投递 | 投递需登录 |
| BOSS直聘 | Camofox | Camofox「立即沟通」 | 需登录 |
| 实习僧 | Camofox | Camofox「投个简历」 | 需登录 |

## 配置项

- `config/platforms.yml`：平台开关、标题排除词、薪资范围、学历白名单、信任检测。
- `config/llm.json`：Base URL / model / api_key。
- `config/settings.json`：在线表格同步（webhook / 飞书）。

## 数据模型

`data/applications.json` 为唯一数据源：

```json
{
  "applications": [{
    "id": "uuid", "company": "", "position": "", "platform": "51job|BOSS直聘|实习僧",
    "salary": "", "location": "", "score": 1-5, "status": "...",
    "url": "", "jd_summary": "", "hr_name": "", "applied_at": "", "last_update": "",
    "messages": [], "notes": ""
  }],
  "stats": {"total_applied": 0, "hr_replied": 0, "interview_scheduled": 0, "rejected": 0}
}
```

## 风险与边界

- 平台风控：IP 封禁、验证码、页面改版。所有浏览器操作失败都给出可读提示。
- Camofox 首次安装约 150MB，仅投递/BOSS/实习僧需要。
- 反爬策略持续演进，解析器需随平台更新维护。
