# BOSS直聘 陷阱与注意事项

## 搜索陷阱

### 1. 筛选参数导致 0 结果
jobType + experience + degree 三个参数同时设置 → 经常 0 结果。**建议**：先只用 city + keyword，不加 experience 和 degree。搜到结果后再人工判断学历/经验。

### 2. 列表标注的学历/经验是假的
搜索列表页标注的"大专""经验不限"等标签经常不准确，**必须进详情页确认**。

### 3. 工作地点不一致
列表显示"南京"但详情页可能在外省。例如"南京永成包装自动化"实际在新集。**必须进详情页核实**。

### 4. 薪资乱码
BOSS 反爬字体加密导致薪资显示乱码。如果对薪资无硬性要求，直接忽略。

### 5. 技能陷阱
- 要求 SolidWorks → 学的是 AutoCAD，不同软件 → 排除
- 要求 Python/软件开发 → 方向不匹配 → 排除
- 建筑电气 ≠ 工业电气自动化 → 排除

## 投递陷阱

### 1. 「立即沟通」按钮点击无效
普通 click() 对 BOSS 的 React SPA 按钮不生效。需要：
```javascript
// 递归派发 mousedown + mouseup + click 到 btn-startchat-wrap 及所有子元素
function clickAll(el) {
  const r = el.getBoundingClientRect();
  const cx = r.x+r.width/2, cy = r.y+r.height/2;
  el.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,clientX:cx,clientY:cy}));
  el.dispatchEvent(new MouseEvent('mouseup',{bubbles:true,clientX:cx,clientY:cy}));
  el.dispatchEvent(new MouseEvent('click',{bubbles:true,clientX:cx,clientY:cy}));
  for(const c of el.children) clickAll(c);
}
clickAll(document.querySelector('.btn-startchat-wrap'));
```

### 2. 投递后必须验证
点击「立即沟通」后的状态可能是：
- "已发送" → 投递成功 ✅
- "继续沟通" → 只打开了聊天窗口，需要再点一次发送消息
- 弹出确认框 → 关掉回到搜索结果

验证时**必须在右侧聊天面板内查**，不能用全局 `document.body.innerText` —— 会匹配到其他聊天的历史消息。

### 3. Tab 超时失效
长时间（>30分钟）不操作的 tab 会失效。每次长时间中断后创建新 tab。

## 登录陷阱

### 1. Cookie 过期
数天未使用后 Cookie 可能过期，导航后自动跳转登录页。检查快照中是否有"验证码登录/注册"。

处理：输入手机号 → 发送验证码 → 用户输入 → 确认登录。

### 2. IP 黑名单
频繁访问后公网 IP 被 BOSS 拉黑。表现为页面返回 JSON：`{"message":"Your IP is blacklisted"}`。

处理：告知用户，等待解封或换网络。重启浏览器**不会**换 IP。

## 回复陷阱

### 1. 发简历弹窗
点击「发简历」后可能弹出：
- "是否同意发送简历"确认框（需点"同意"）
- 简历选择器（需选文件 → 点"发送"）
- 两个弹窗顺序出现

发送后必须验证「附件简历请求已发送」。

### 2. 验证 scope 限定
验证发送/回复是否成功时，**只在右侧聊天面板内查询**（offsetWidth > 600 且包含目标 HR 名的 div），绝不全局查询。

### 3. computer_use 不可用于 Camofox
如果使用 Camofox 浏览器（Firefox 引擎），computer_use 的 cua-driver 检测不到窗口。只能用 JS evaluate 操作。

## 通用

### SPA 路由卡死
BOSS 的 Vue SPA 偶尔路由卡死，导航后 URL 变了但内容不更新。此时需刷新页面或创建新 tab。

### 聊天列表点击
左侧联系人列表点不开右侧面板时，尝试：
```javascript
li.click();
li.dispatchEvent(new MouseEvent("mousedown",{bubbles:true}));
li.dispatchEvent(new MouseEvent("mouseup",{bubbles:true}));
```
等 8 秒后验证右侧面板有内容（offsetWidth > 800 && offsetHeight > 200 && 包含目标 HR 名）。
