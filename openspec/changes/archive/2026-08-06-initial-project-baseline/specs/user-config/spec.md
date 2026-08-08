## Purpose

管理 JobBot 的本地配置与用户求职画像：LLM 端点与密钥、求职意向、简历上传解析，以及各平台的搜索规则，是搜索与投递全流程的输入来源。

## ADDED Requirements

### Requirement: LLM 连接配置

系统 SHALL 允许用户配置 OpenAI 兼容接口的 Base URL、模型名与 API Key，并持久化到本地配置；API Key 不得在读取配置时回传给前端，前端仅能得知是否已配置。

#### Scenario: 保存并测试连接
- **WHEN** 用户填写 Base URL、模型与 API Key 并保存，随后点击测试连接
- **THEN** 系统持久化配置，并调用 LLM 接口返回测试结果，成功或失败均有明确提示

#### Scenario: 未配置 Key 时使用 LLM
- **WHEN** 用户发起需要 LLM 的操作但尚未配置 API Key
- **THEN** 系统给出"未配置 API Key"的明确错误，不静默失败

### Requirement: 求职意向与画像

系统 SHALL 持久化用户的求职意向（城市、学历、专业、目标岗位、技能等）与目标城市；目标城市未指定时 SHALL 使用默认城市"南京"。

#### Scenario: 保存求职意向
- **WHEN** 用户在配置区填写意向描述并保存
- **THEN** 意向被持久化，后续搜索使用最新意向内容

### Requirement: 简历上传与结构化解析

系统 SHALL 支持上传 TXT、Word（.docx）与 PDF 简历并提取结构化信息（姓名、学历、专业、学校、技能、证书、目标城市等）；PDF 优先使用 pypdf 提取，不可用时自动降级到内置零依赖提取器；LLM 解析不可用时降级为规则解析。

#### Scenario: 上传文字版 PDF 简历
- **WHEN** 用户上传含文字层的 PDF 简历
- **THEN** 系统解析出结构化字段并在界面展示，供用户核对

#### Scenario: 上传扫描件或图片版 PDF
- **WHEN** 用户上传无文字层的 PDF
- **THEN** 系统给出明确提示（建议另存为 docx 或手动填写意向），不报错中断

#### Scenario: 上传旧版 .doc
- **WHEN** 用户上传 .doc 文件
- **THEN** 系统提示该格式无法直接解析，建议另存为 .docx 或 .txt

### Requirement: 平台搜索规则配置

系统 SHALL 支持按平台配置启用状态、标题排除词、薪资范围、学历白名单与信任检测关键词，并让配置实际生效于搜索过滤；未启用的平台不得参与搜索。

#### Scenario: 平台被禁用
- **WHEN** 用户在平台配置中将某平台 `enabled` 设为 false
- **THEN** 搜索流程不再调用该平台

#### Scenario: 标题排除词命中
- **WHEN** 搜索结果中的岗位标题包含配置的排除词
- **THEN** 该岗位被直接跳过，不进入评分
