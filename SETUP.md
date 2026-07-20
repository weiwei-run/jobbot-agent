# JobBot 安装指南

## 前提条件

### 你需要先安装的

1. **Hermes Agent**（或其他支持 skill 的 AI Agent）
   - Hermes 安装文档：https://hermes-agent.nousresearch.com/docs

2. **Python 3.10+**
   - 下载：https://www.python.org/downloads/
   - 安装时勾选「Add Python to PATH」

3. **Playwright**（浏览器自动化）
   ```bash
   pip install playwright httpx jinja2
   playwright install chromium
   ```

## 安装步骤

### 1. 下载 JobBot

```bash
# 克隆或下载到本地
git clone https://github.com/YOUR_USER/jobbot-agent.git
# 或直接解压 zip 到任意目录
```

### 2. 环境检测

```bash
cd jobbot-agent
python scripts/setup.py
```

看到 `✅ 环境就绪！` 就继续。

### 3. 填写简历

```bash
# 复制模板
cp config/user_profile_template.json config/user_profile.json

# 用文本编辑器打开 config/user_profile.json，填写你的信息
```

必填项：`name`, `education`, `major`, `graduate_year`, `expected_cities`, `expected_jobs`, `job_type`

### 4. 调整平台配置（可选）

编辑 `config/platforms.yml`，可以：
- 关闭不想用的平台（把 `enabled: true` 改成 `false`）
- 调整搜索的城市
- 调整标题过滤的黑白名单

### 5. 加载到 Hermes

在 Hermes 中说：

```
加载 jobbot 技能，路径是 /path/to/jobbot-agent/SKILL.md
```

或者用 Hermes 的 skill 导入功能。

### 6. 开始使用

对 Hermes 说：

```
帮我找工作
```

Agent 会引导你完成首次配置，然后自动开始搜索投递。

---

## 日常使用

| 你说的话 | Agent 做什么 |
|---------|-------------|
| "帮我搜岗位" / "帮我投递" | 搜索三平台 + 评分 + 等你确认投递 |
| "检查消息" / "看回复" | 检查各平台 HR 回复 + 生成回复草稿 |
| "看进度" / "打开看板" | 打开 `data/dashboard.html` 查看投递状态 |
| "更新简历" | 修改 user_profile.json 并重新生成关键词 |

---

## 常见问题

### Q: 需要我提供 API key 吗？
A: JobBot 本身不需要额外 API key。它使用你配置给 Hermes/Agent 的大模型（DeepSeek、OpenAI 等）。你自己承担 Agent 的 API 费用。

### Q: 招聘平台需要登录怎么办？
A: JobBot 会打开浏览器让你扫码或输入验证码。登录一次后 Cookie 会保存，下次自动使用。

### Q: 支持哪些招聘平台？
A: 当前支持 BOSS直聘、前程无忧(51job)、实习僧。智联招聘后续更新。

### Q: 我的数据安全吗？
A: 所有数据存在你的本地 `data/` 目录下，不上传任何服务器。投递记录、简历、配置都在你自己电脑上。

### Q: 会封号吗？
A: 使用你自己的招聘平台真实账号进行正常求职行为，不会违规。JobBot 会控制每日投递上限、随机延时模仿真人操作。

### Q: 能用于非 Hermes 的 Agent 吗？
A: 理论上任何支持文件读取和浏览器操作的 AI Agent 都可以。SKILL.md 中的指令是平台中立的。我们也提供了 AGENTS.md（适用于 OpenCode/Claude Code）。
