## REMOVED Requirements

### Requirement: 同步开关与方式
**Reason**: 产品定位调整为本地单机「推荐 → 用户自行投递 → 本地看板跟进」闭环，在线表格同步（webhook / 飞书）属早期多端/家长场景，与当前定位不符，整体移除。
**Migration**: 投递记录仍保存在本地 `data/applications.json`；不再推送任何外部表格。需要时可通过 git 历史恢复 `spreadsheet.py` 与设置界面。

### Requirement: Webhook 同步
**Reason**: 随在线表格同步整体移除（见「同步开关与方式」）。
**Migration**: 无替代；本地看板记录与 CSV 导出已覆盖跟进需求。

### Requirement: 飞书多维表格同步
**Reason**: 随在线表格同步整体移除（见「同步开关与方式」）。
**Migration**: 无替代；本地看板记录与 CSV 导出已覆盖跟进需求。

### Requirement: 变更后自动异步同步
**Reason**: 随在线表格同步整体移除（见「同步开关与方式」），记录新增/更新不再触发任何外部推送。
**Migration**: 记录写入本地 `data/applications.json` 后仅更新本地看板，不再发起网络请求。
