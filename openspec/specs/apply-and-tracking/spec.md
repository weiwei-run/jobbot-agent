# apply-and-tracking Specification

## Purpose

完成投递执行与全过程追踪：在三平台自动投递并验证成功状态，以本地 JSON 文件为唯一数据源维护投递记录，支持状态机流转并在每次变更后触发在线同步。

## Requirements

### Requirement: 自动投递与成功验证

系统 SHALL 对候选岗位执行对应平台的自动投递，且 MUST 在操作后验证成功状态才算投递成功：BOSS直聘验证"已发送/继续沟通/送达"，51job 验证"投递成功/已投递"，实习僧验证"投递成功/已投递"；未登录 SHALL 停在登录页提示手动登录，岗位下线 SHALL 提示换岗，其余失败 SHALL 返回明确原因。

#### Scenario: 投递成功并验证
- **WHEN** 用户对岗位点击投递且平台操作成功
- **THEN** 系统验证到成功状态，将岗位记录为已投递并展示成功消息

#### Scenario: 投递时未登录
- **WHEN** 投递过程中检测到平台未登录
- **THEN** 系统停止操作、打开登录页并提示手动登录后重试，不投递

#### Scenario: 岗位已下线
- **WHEN** 投递目标岗位已下线或审核中
- **THEN** 系统不投递并明确提示该岗位已下线

### Requirement: 投递记录管理

系统 SHALL 以本地数据文件为唯一数据源维护投递记录，每条记录包含公司、岗位、平台、薪资、地点、评分、理由、URL、JD 摘要、联系人、状态与时间戳；同一岗位（URL 或平台岗位 ID）重复投递 SHALL 被拒绝或合并，不得产生重复记录。

#### Scenario: 新增投递记录
- **WHEN** 一次自动投递成功
- **THEN** 系统新增一条记录并刷新统计

#### Scenario: 重复记录
- **WHEN** 已存在相同 URL 或平台岗位 ID 的记录时再次添加
- **THEN** 系统拒绝新增重复记录并给出提示

### Requirement: 状态机流转

系统 SHALL 支持记录状态流转（discovered、applied、hr_replied、interviewing、interview_scheduled、offered、rejected），更新状态时 SHALL 刷新统计（总投递、HR 已回复、已约面试、被拒）并触发在线同步。

#### Scenario: 更新记录状态
- **WHEN** 用户或流程将记录状态更新为面试已约
- **THEN** 记录状态与更新时间被持久化，统计随之刷新

### Requirement: 手动记录

系统 SHALL 允许用户手动添加投递记录（无需经过自动投递），用于记录线下或手动完成的投递。

#### Scenario: 手动加入记录
- **WHEN** 用户手动提交公司、岗位等信息
- **THEN** 系统创建一条记录并纳入统计与同步
