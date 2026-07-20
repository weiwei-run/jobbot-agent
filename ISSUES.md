# JobBot 测试循环 · ISSUES.md

> 记录 OpenCode 运行 JobBot 时遇到的问题。
> 格式：日期 + 问题描述 + 日志片段 + 期望行为。

---

## 待修复

### #1 LongCat API Key 在 OpenCode 中报 "incorrect api key"
- **日期**: 2026-07-20
- **现象**: `LONGCAT_API_KEY=ak_2dQ...` + `--model longcat/LongCat-2.0` → `Error: incorrect api key`
- **验证**: 同一 key 用 curl 调 `https://api.longcat.chat/openai/v1/chat/completions` 正常返回
- **可能原因**: OpenCode 内置的 LongCat 提供商可能使用 Anthropic 兼容端点而非 OpenAI 兼容端点
- **Workaround**: 使用免费模型 `opencode/hy3-free` 或 `opencode/big-pickle` 可正常跑通
- **状态**: 🔴 待解决

---

## 已修复

<!-- 修复后移到此处 -->

---

## 测试记录

| 日期 | Agent | 模型 | 搜岗位 | 投递 | 回复 | 看板 | 备注 |
|------|-------|------|--------|------|------|------|------|
| 7/20 | OpenCode 1.18.3 | big-pickle (free) | — | — | — | — | 配置向导 ✅，搜索待测 |
| 7/20 | OpenCode 1.18.3 | LongCat-2.0 | — | — | — | — | ❌ Key 认证失败 |
