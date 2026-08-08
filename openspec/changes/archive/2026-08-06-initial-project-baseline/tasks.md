## 1. 基线评审

- [x] 1.1 评审 proposal：确认 6 个能力域划分与范围符合项目现状
- [x] 1.2 逐条对照代码核对 `user-config` spec 的行为描述
- [x] 1.3 逐条对照代码核对 `platform-automation` spec 的行为描述
- [x] 1.4 逐条对照代码核对 `job-search` spec 的行为描述
- [x] 1.5 逐条对照代码核对 `apply-and-tracking` spec 的行为描述
- [x] 1.6 逐条对照代码核对 `local-dashboard` spec 的行为描述
- [x] 1.7 逐条对照代码核对 `online-sync` spec 的行为描述
- [x] 1.8 修正评审中发现的行为描述偏差

## 2. 校验与归档

- [x] 2.1 运行 `openspec validate` 确认基线变更通过校验
- [x] 2.2 执行 apply，将 6 份 delta spec 合并进主规格
- [x] 2.3 执行 archive 归档本变更，主规格成为后续变更的基准
