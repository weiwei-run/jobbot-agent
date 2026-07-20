# 消息回复 SOP（标准操作流程）

## 消息检查流程

用户说"检查消息"后：
1. 打开各平台聊天/消息页面
2. 扫描未读消息
3. 对每条未读消息按场景分类处理

---

## 场景分类与话术

### 通用原则

- **去AI味**：不谈"感谢您的关注""希望能跟着前辈多学习"
- **学生语气**：简短、直接、有什么说什么
- **每次必做**：自我介绍 + 发简历
- **关键信息要带**：学历、专业、到岗时间

---

### 场景表

| # | 判断 | 话术模板 |
|---|------|---------|
| 1 | HR 打招呼/要聊 | "好的您好。我是[专业][学历]，已经在[城市]了随时到岗。我发一下简历您看看？" |
| 2 | HR 要简历 | "好的，发您了。我是[专业][学历]，已经在[城市]，随时到岗。" |
| 3 | HR 问"在南京么" | "在的，已经在[城市]了，随时可以到岗实习。" |
| 4 | HR 问技能（如"会CAD吗"） | "在学校学过[技能]，课程设计也做过不少。" |
| 5 | HR 问"能出差么" | "出差短期可以的。" |
| 6 | HR 问待遇 | "找个能学技术的机会，待遇按公司标准就行。" |
| 7 | HR 问实习多久 | "可以实习到毕业，已经在[城市]了随时到岗。" |
| 8 | HR 问是否接受条件 | "可以接受，[学历][专业]，随时到岗。" |
| 9 | HR 拒绝/婉拒 | 不回复，或简单回"好的" |
| 10 | 系统通知（简历已发等） | 不回复 |
| 11 | HR 要加微信 | "好的，我的微信是[微信号]" → **通知用户** |
| 12 | HR 约面试 | **立即通知用户确认**，不私自确认时间 |

---

## 发简历流程（BOSS直聘）

1. 在聊天界面找到「发简历」按钮
2. 点击后可能弹出：
   - "是否同意发送简历"确认框 → 点"同意"
   - 简历选择器弹窗 → 选第一个文件 → 点"发送"
3. 验证「附件简历请求已发送」

### 发简历 JS 代码参考

```javascript
// 1. 点「发简历」
const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
let node;
while (node = walker.nextNode()) {
  if (node.textContent.includes("发简历") && node.parentElement.offsetParent) {
    node.parentElement.click();
    break;
  }
}

// 2. 如果有"同意"按钮
const agree = document.querySelector('.message-dialog-both .card-btn');
if (agree) {
  agree.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
  agree.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
  agree.click();
}

// 3. 选简历文件 + 点发送
const item = document.querySelector('.resume-list .list-item');
if (item) item.click();
const send = document.querySelector('.btn-send:not(.disabled)');
if (send) send.click();

// 4. 验证（只在右侧面板内查）
// 检查：textContent.includes('附件简历请求已发送')
```

---

## 发送消息 JS 代码参考

```javascript
// React contenteditable 输入
const el = document.querySelector('[contenteditable="true"]');
el.focus();
el.innerHTML = '';
el.dispatchEvent(new Event('input', {bubbles: true}));
document.execCommand('insertText', false, '消息内容');

// 点击发送
const btns = document.querySelectorAll('button, span, div');
for (const b of btns) {
  if (b.textContent.trim() === '发送' && b.offsetParent && b.offsetWidth < 120) {
    b.click();
    break;
  }
}

// 验证「送达」
```

---

## 面试邀约处理

检测到面试邀约的关键词："面试""面聊""过来聊聊""约个时间""下周见""面试时间""面试地点"

处理流程：
1. 提取：公司名、岗位、时间、地点
2. 生成格式化通知
3. **不私自确认** — 必须等用户决策
4. 用户确认后更新 tracking 状态

通知格式：
```
🎉 面试邀约！
公司：[公司名]
岗位：[岗位名]
时间：[时间]
地点：[地点]
备注：[其他信息]
---
是否确认这个时间？回复"确认"或"需要调整"
```
