# 51job（前程无忧）API 参考

## 搜索 API

### 端点
```
GET https://we.51job.com/api/job/search-pc
```

### 参数

| 参数 | 必填 | 说明 | 示例 |
|------|------|------|------|
| api_key | 是 | 固定值 | 51job |
| timestamp | 是 | 毫秒时间戳 | 1753001234567 |
| keyword | 是 | URL编码的搜索词 | %E7%94%B5%E5%B7%A5 |
| searchType | 是 | 固定值 | 2 |
| jobArea | 是 | 城市代码 | 070200（南京） |
| pageNum | 是 | 页码（从1开始） | 1 |
| pageSize | 是 | 每页数量 | 20 |
| source | 是 | 固定值 | 1 |
| scene | 是 | 固定值 | 7 |
| sortType | 否 | 0=综合 1=最新 | 0 |

### 筛选参数（可选）

| 参数 | 说明 | 示例 |
|------|------|------|
| workYear | 工作年限 | 02=在校生/应届生 |
| degree | 学历 | 04=大专, 03=中专 |
| salary | 月薪 | 02=2-3千, 03=3-4.5千 |
| issueDate | 发布时间 | 0=24h内, 1=近三天 |

### 城市代码

| 城市 | jobArea |
|------|---------|
| 南京 | 070200 |
| 北京 | 010000 |
| 上海 | 020000 |
| 广州 | 030200 |
| 深圳 | 040000 |
| 杭州 | 080200 |
| 成都 | 090200 |
| 武汉 | 180200 |
| 苏州 | 070500 |

### 返回格式

```json
{
  "status": "1",
  "resultbody": {
    "job": {
      "totalcount": 637,
      "items": [{
        "jobId": "169787887",
        "jobName": "电工",
        "jobDescribe": "一、岗位职责\\n1、...",
        "provideSalaryString": "7-9千",
        "jobSalaryMin": "7000",
        "jobSalaryMax": "9000",
        "jobAreaString": "南京·江宁区",
        "workYearString": "3年及以上",
        "degreeString": "中技/中专",
        "fullCompanyName": "美埃（中国）环境科技股份有限公司",
        "companyTypeString": "外资（非欧美）",
        "companySizeString": "500-1000人",
        "industryType1Str": "电子技术/半导体/集成电路",
        "jobTags": ["低压电工证", "3年及以上"],
        "hrName": "谢亮亮",
        "hrIsOnline": false,
        "isApply": false,
        "jobHref": "https://jobs.51job.com/nanjing-jnq/169787887.html"
      }]
    }
  }
}
```

### 关键字段

| 字段 | 用途 |
|------|------|
| jobId | 投递时的唯一标识 |
| jobName | 岗位名称 |
| jobDescribe | **完整JD**（含\\n换行），LLM 评分核心输入 |
| provideSalaryString | 薪资显示文本 |
| fullCompanyName | 公司全名 |
| jobAreaString | 工作地点 |
| workYearString | 经验要求 |
| degreeString | 学历要求 |
| hrName | HR 名称 |
| isApply | 是否已投递（去重用） |
| jobHref | 岗位详情链接 |

## 投递 API

```
POST https://cupid.51job.com/open/user-apply/open/user-apply/light-apply-job
```

### 必需 Headers
```
user-token: {从登录后 localStorage 获取}
account-id: {账号ID}
sign: {由浏览器 JS 自动生成，无需手动计算}
from-domain: 51job_web
```

### Body
```json
{
  "accountId": "账号ID",
  "applyJobList": [{
    "jobId": "岗位ID",
    "jobType": "0",
    "requestId": "随机UUID"
  }],
  "setQuickPost": false,
  "fromType": "列表页",
  "version": "400",
  "multiAttachmentResumeSupported": true
}
```

> ⚠️ `sign` 字段由前端 JS 动态生成（HMAC-SHA256），不要手动计算。建议用浏览器点击「投递」按钮方式，浏览器自动处理签名。

## 登录

登录页：`https://login.51job.com/login.php?lang=c`

SMS 验证码登录流程：
1. 输入手机号
2. 点击「发送验证码」
3. 用户输入验证码
4. 点击登录

登录后从 localStorage 提取：
- `token` — API 鉴权
- `accountId` — 账号ID
- `userInfo.resumeId` — 简历ID

## 陷阱

1. **Token 过期**：长时间不用需重新 SMS 登录
2. **简历不完整**：51job 简历未填写完整可能导致投递失败
3. **重复投递**：`isApply: true` 的岗位跳过
4. **部分岗位无「投递」按钮**：只有「去聊聊」→ 跳过
5. **投递后弹窗**：每次投递成功弹出微信扫码沟通二维码，需关闭弹窗才能继续
6. **SMS 冷却**：发送按钮有 60 秒冷却，切换号码不能跳过
7. **培训/外包公司**：公司行业为"人力资源"或 JD 含"异地实习""培训费"→ 警惕
8. **机器人岗稀缺**：南京大专可投的机器人实习岗极少，需双轨策略（机器人碰运气 + PLC保底）
