# JobBot 运行日志

> 每次 OpenCode 运行 JobBot 后记录。

---

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
