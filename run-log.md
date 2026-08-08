# JobBot 运行日志

> 每次 OpenCode 运行 JobBot 后记录。

---

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
