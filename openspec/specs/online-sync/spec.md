# online-sync Specification

## Purpose

将投递记录自动同步到在线表格，支持通用 Webhook（JSON 推送，可对接 Zapier/Make/自建服务）与飞书多维表格两种方式，同步在后台异步执行，不阻塞投递流程。

## Requirements

### Requirement: 同步开关与方式

系统 SHALL 支持在设置中开启/关闭同步并选择方式（关闭、webhook、飞书），设置持久化到本地；关闭时 SHALL 不进行任何推送。

#### Scenario: 同步关闭
- **WHEN** 在线表格同步未开启
- **THEN** 投递记录变更不触发任何推送

### Requirement: Webhook 同步

系统 SHALL 在 webhook 方式下把投递记录以 JSON（含记录列表与数量）POST 到配置的地址；目标返回 HTTP 4xx/5xx 时 SHALL 报告失败原因。

#### Scenario: webhook 推送成功
- **WHEN** 投递记录变更且 webhook 地址配置正确
- **THEN** 系统推送记录并返回成功与推送条数

#### Scenario: webhook 返回错误
- **WHEN** webhook 目标返回非 2xx 状态码
- **THEN** 系统返回包含状态码的失败提示

### Requirement: 飞书多维表格同步

系统 SHALL 在飞书方式下使用 app_id/app_secret 获取 tenant_access_token，将记录批量写入配置的多维表格（app_token + table_id）；关键配置缺失时 SHALL 报错。

#### Scenario: 飞书配置缺失
- **WHEN** 飞书方式下 app_id、app_secret、app_token 或 table_id 未配置完整
- **THEN** 系统返回明确的配置缺失提示

### Requirement: 变更后自动异步同步

系统 SHALL 在新增或更新投递记录后自动触发同步，且同步 SHALL 在后台线程执行，不阻塞记录写入或投递流程。

#### Scenario: 新增记录自动同步
- **WHEN** 同步开启时新增一条投递记录
- **THEN** 系统在后台将该记录推送到已配置的同步目标
