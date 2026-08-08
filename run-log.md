# JobBot 运行日志

> 每次 OpenCode 运行 JobBot 后记录。

---

## 2026-08-08 #1 — 修复：重传简历后意向描述未刷新（前端解析块状态 bug，与格式无关）

- **现象**: 先传一份简历、再传另一份 PDF 简历后，【意向描述】仍保留旧内容，目标城市也未变
- **根因**: `splitIntent` 依赖 `_resumeParse` 在文本框末尾做后缀匹配来剥离旧解析块；一旦匹配失败（手动编辑过意向、或页面/配置状态不同步），整段文本被当成手动意向且 `resume_parse` 被清空，之后重传只把新解析块**追加**到旧内容后面，看起来"没更新"。与 PDF/docx 格式无关（实测两种格式解析均正常）
- **修复**: `uploadResume` 重传时先剥掉末尾旧解析块，若剩余部分仍以 `姓名:/学历:` 等结构化标签开头则整体丢弃，再拼新解析块
- **验证**: 模拟坏状态/正常状态/全新上传三种场景，旧内容均被干净替换；`python -m py_compile` 通过

## 2026-08-08 #0 — BOSS/实习僧 搜索解析修复（Camofox evaluate 契约变化）

- **现象**: BOSS直聘搜索报「未解析到岗位（可能被风控拦截或页面结构变化）」，但浏览器手动浏览、登录均正常
- **根因**: 三个平台抽取 JS 是裸箭头函数 `() => {...}`，Camofox evaluate 对其只返回 `{ok:true}` 无 `result`；且新版 Camofox 对数组返回结构化 JSON（Python list），应用代码 `json.loads()` 只认字符串
- **修复**: 三个抽取 JS 改为 IIFE 自调用；新增 `platforms._parse_extract()` 兼容 list/字符串；BOSS 公司选择器适配新版 `span.boss-name`（旧 `[class*=company]` 误匹配 company-location）；实习僧改用结构化选择器（`.city` / `.intern-detail__company .title`），标题清理字体图标私有区字符
- **验证**: BOSS 搜「新媒体运营」返回 17 条（公司/地点/链接正确）；实习僧返回 11 条

## 2026-08-06 #0 — 建立 OpenSpec 基线 + 变更约定

- **动作**: 通读代码生成 6 能力域基线规格（user-config / platform-automation / job-search / apply-and-tracking / local-dashboard / online-sync），归档为 `openspec/changes/archive/2026-08-06-initial-project-baseline/`
- **约定**: 是否改变用户可见行为/数据格式/外部接口 → 是走完整 OpenSpec 流程，否则轻量处理（skip_specs 或 run-log）；已写入根目录 `AGENTS.md`，重启 Codex 自动加载
- **注意**: 本机 `openspec archive` 报 EPERM（Node 目录改名问题），采用手动合并+Move-Item 归档

## 2026-07-20 #1 — 配置向导测试

- **Agent**: OpenCode v1.18.3
- **模型**: big-pickle (free)
- **输入**: "我在南京找电气自动化实习，大专，2027毕业，PLC+CAD"
- **输出**: 
  - ✅ 读取 AGENTS.md 成功，自称为 JobBot
  - ✅ 读取 config/user_profile_template.json + platforms.yml
  - ✅ 生成 user_profile.json（字段完整）
  - ✅ 生成搜索关键词（9个，分 P0-P3 优先级）
  - ✅ 询问用户确认并是否开始搜索
- **时长**: ~15秒
- **文件产物**: config/user_profile.json (796B)

---

## 2026-07-20 #0 — 环境搭建

- OpenCode 安装：npm install -g opencode-ai（需 npm 镜像）
- Postinstall：手动运行 postinstall.mjs
- AGENTS.md：复制到 ~/.config/opencode/AGENTS.md
- LongCat key：curl 验证通过，但 OpenCode 原生集成报 "incorrect api key"
- Workaround：opencode/hy3-free 或 opencode/big-pickle 免费模型可用

---

## 2026-08-08 #2 — 图片自动识别（OCR）桥接

- **背景**：Codex 当前配置为 DeepSeek（deepseek-v4-flash，无视觉能力），用户发截图时模型无法直接看图
- **动作**：新增 `scripts/ocr_image.ps1`（Windows 内置 OCR，zh-Hans-CN 优先）；AGENTS.md 增加「图片自动识别（OCR）约定」，消息带图片/截图路径时自动 OCR 再回复
- **验证**：真实中文截图（BOSS直聘页面）OCR 读取正常；`view_image` 在当前模型下不可用，OCR 为唯一读图通道

---

## 2026-08-08 #3 — BOSS直聘拦截检测 + Camofox 重启

- **现象**：Camofox 服务在跑但引擎卡死，创建标签页连续超时（HTTP 500, tab create timed out）
- **处理**：结束占用 9377 端口的 node 进程 → 冷启动 server.js + camoufox 引擎（登录 cookie 存于 profile，登录态保留）
- **检测结果**：BOSS直聘未拦截。搜索页 `zhipin.com/web/geek/jobs?query=PLC&city=101190100` 与详情页 `/job_detail/7a3e18ec8997214c0nFy09i9EFpT.html` 均正常加载，无安全验证/验证码/登录墙/IP 黑名单标记，账号（肖豪威）已登录
- **注意**：引擎冷启动后首次创建标签页较慢（本次约 90s/重试 3 次成功），遇到 `tab create timed out` 时重试即可
