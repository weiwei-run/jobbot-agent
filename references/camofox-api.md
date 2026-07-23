# Camofox REST API 参考

> Camofox 浏览器引擎通过 HTTP API 驱动。所有请求到 `http://localhost:9377`。

## 通用参数

- `userId`: 固定为 `"jobbot"`
- Content-Type: `application/json`
- tab ID: 创建标签页时返回的 `id` 字段

## API 速查

### POST /tabs — 创建标签页

```bash
curl -s -X POST http://localhost:9377/tabs \
  -H "Content-Type: application/json" \
  -d '{"userId":"jobbot","url":"https://www.zhipin.com"}'
# → {"id":"tab_abc123","userId":"jobbot","url":"..."}
```

### POST /tabs/:id/navigate — 导航

```bash
curl -s -X POST http://localhost:9377/tabs/TAB_ID/navigate \
  -H "Content-Type: application/json" \
  -d '{"userId":"jobbot","url":"https://www.zhipin.com/web/geek/job?query=PLC&city=101190100"}'
```

### GET /tabs/:id/snapshot — 获取页面快照

```bash
curl -s "http://localhost:9377/tabs/TAB_ID/snapshot?userId=jobbot"
# → 返回页面可访问性树（AX tree），每个交互元素带 ref 编号 @e1, @e2 ...
```

### POST /tabs/:id/click — 点击元素

```bash
curl -s -X POST http://localhost:9377/tabs/TAB_ID/click \
  -H "Content-Type: application/json" \
  -d '{"userId":"jobbot","ref":"@e15"}'
```

### POST /tabs/:id/evaluate — 执行 JavaScript

```bash
curl -s -X POST http://localhost:9377/tabs/TAB_ID/evaluate \
  -H "Content-Type: application/json" \
  -d '{"userId":"jobbot","expression":"document.title"}'
# → {"result":"BOSS直聘-找工作"}
```

### POST /tabs/:id/type — 输入文字

```bash
curl -s -X POST http://localhost:9377/tabs/TAB_ID/type \
  -H "Content-Type: application/json" \
  -d '{"userId":"jobbot","text":"你好，我对这个岗位感兴趣","ref":"@e8"}'
```

### DELETE /tabs/:id — 关闭标签页

```bash
curl -s -X DELETE http://localhost:9377/tabs/TAB_ID
```

## BOSS 直聘特殊处理

### 立即沟通按钮

BOSS 的「立即沟通」按钮使用 React 事件委托，普通 click 可能无效。使用 JS 事件派发：

```bash
# 递归 clickAll 模式
curl -s -X POST http://localhost:9377/tabs/TAB_ID/evaluate \
  -H "Content-Type: application/json" \
  -d '{"userId":"jobbot","expression":"(function clickAll(s){document.querySelectorAll(s).forEach(function(e){e.dispatchEvent(new MouseEvent(\"mousedown\",{bubbles:true}));e.dispatchEvent(new MouseEvent(\"mouseup\",{bubbles:true}));e.dispatchEvent(new MouseEvent(\"click\",{bubbles:true}))})})(\".chat-btn, [class*=chat], [class*=沟通], [class*=contact]\")"}'
```

### 投递验证

点击「立即沟通」后必须验证结果：
1. 重新获取 snapshot
2. 检查是否出现「已发送」/「继续沟通」/「送达」
3. 如果出现「继续沟通」→ 再次点击 → 再验证

### BOSS 搜索 URL

```
https://www.zhipin.com/web/geek/job?query={keyword}&city=101190100
```
- 城市代码：南京=101190100
- 不建议加 `jobType=1902`（严重限制技术岗结果）

## 51job 搜索

URL: `https://we.51job.com/pc/search?keyword={keyword}&jobArea=070200`
城市代码：南京=070200

51job 使用阿里云 WAF（waf-nc-mask）。Camofox 可正常提取页面内容，从 snapshot 直接解析岗位列表。

## 实习僧

URL: `https://www.shixiseng.com/interns?keyword={keyword}&city={city}&type=intern`

投递弹窗处理：
1. 点击「投个简历」弹出 dialog
2. evaluate click 选中「附件简历」
3. evaluate click `.common-deliver__footer`（确认投递按钮）
4. 直接点「确认投递」无效（React 事件委托）

## 启动/停止

启动前必清残留：
```bash
# Windows
taskkill //F //IM camoufox.exe 2>/dev/null
taskkill //F //IM firefox.exe 2>/dev/null

# macOS/Linux
pkill -f camoufox 2>/dev/null
```

启动：
```bash
# Windows
set CAMOUFOX_INSTALL_DIR=%USERPROFILE%\AppData\Local\camoufox\camoufox
node "%APPDATA%\npm\node_modules\@askjo\camofox-browser\server.js"

# macOS/Linux
CAMOUFOX_INSTALL_DIR=~/.cache/camoufox/camoufox \
  node "$(npm root -g)/@askjo/camofox-browser/server.js"
```

服务器在 10 秒内就绪，端口 9377。
