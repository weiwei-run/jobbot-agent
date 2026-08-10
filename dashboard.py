#!/usr/bin/env python3
"""JobBot Dashboard — python dashboard.py → http://localhost:9379

单文件本地看板（纯 stdlib）：LLM 配置 → 简历/意向 → 三平台搜索评分 →
岗位详情投递 → 投递记录管理。
"""
import http.server
import json
import os
import re
import socket
import sys
import threading
import uuid
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import engine  # noqa: E402
from llm import chat_json, load_config, save_config, test_connection  # noqa: E402

PORT = 9379
ROOT = Path(__file__).parent
DATA_FILE = ROOT / "data" / "applications.json"
CONFIG_FILE = ROOT / "config" / "user_profile.json"
CONFIG_TEMPLATE = ROOT / "config" / "user_profile_template.json"
RESUME_DIR = ROOT / "data" / "resume"

os.makedirs(ROOT / "data", exist_ok=True)
os.makedirs(RESUME_DIR, exist_ok=True)
if not DATA_FILE.exists():
    engine.save_db(engine._empty_db())

# 后台搜索任务（避免搜索期间 Dashboard 无响应，并支持进度反馈）
SEARCH_TASK: dict = {"running": False, "progress": {}, "result": None, "error": None}
APPLY_LOCK = threading.Lock()


HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>JobBot · AI求职助手</title>
<style>
:root{--bg:#0d1117;--fg:#e6edf3;--accent:#58a6ff;--good:#3fb950;--warn:#d29922;--err:#f85149;--card:#161b22;--border:#30363d}
*{box-sizing:border-box;margin:0;padding:0}
body{font:14px/1.6 system-ui,sans-serif;background:var(--bg);color:var(--fg);padding:20px;max-width:1120px;margin:0 auto}
h1{font-size:22px;margin-bottom:4px}.sub{color:#8b949e;margin-bottom:20px;font-size:13px}
section{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:18px;margin-bottom:16px}
h3{font-size:15px;margin-bottom:12px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.grid4{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.stat-card{background:var(--bg);border-radius:8px;padding:14px;text-align:center}
.stat-card .num{font-size:28px;font-weight:700}.stat-card .lbl{font-size:12px;color:#8b949e;margin-top:2px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;padding:8px 10px;color:#8b949e;font-weight:500;border-bottom:1px solid var(--border);cursor:pointer;user-select:none;white-space:nowrap}
th:hover{color:var(--fg)}
td{padding:8px 10px;border-bottom:1px solid var(--border);vertical-align:top}
tbody tr.main-row{cursor:pointer}tbody tr.main-row:hover td{background:rgba(88,166,255,.08)}
tr.expand-row td{border-bottom:1px solid var(--accent);padding:12px 14px;background:rgba(88,166,255,.04);font-size:13px}
tr.expand-row strong{color:var(--accent)}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.badge{padding:2px 8px;border-radius:10px;font-size:11px;white-space:nowrap}
.badge-discovered{background:#1a1a2a;color:#8b949e}.badge-applied{background:#2a1f0a;color:var(--warn)}
.badge-hr_replied{background:#0a1f2a;color:var(--accent)}.badge-interviewing,.badge-interview_scheduled{background:#0a2a1a;color:var(--good)}
.badge-offered{background:#0a2a1a;color:var(--good)}.badge-rejected{background:#2a0a0a;color:var(--err)}
.stars{color:var(--warn)}
.score-badge{background:var(--accent);color:#fff;border-radius:10px;padding:2px 8px;font-size:12px;font-weight:700;white-space:nowrap}
.chips{display:flex;gap:4px;flex-wrap:wrap;justify-content:flex-end;margin-top:4px}
.chip{background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:1px 6px;font-size:11px;color:#8b949e}
.ev-box,.gap-box{margin-top:6px;font-size:12px;line-height:1.7}
.ev{color:var(--good)}.gap{color:var(--warn)}
button,.btn{background:var(--accent);color:#fff;border:0;padding:8px 20px;border-radius:6px;cursor:pointer;font-size:13px;font-weight:600}
button:hover{opacity:.85}button:disabled{opacity:.4;cursor:not-allowed}
.btn-sm{background:var(--border);padding:4px 12px;font-size:12px}.btn-sm:hover{background:#484f58}
.btn-good{background:var(--good);color:#000}.btn-warn{background:var(--warn);color:#000}.btn-err{background:var(--err)}
textarea,input[type=text],input[type=password],select{width:100%;background:var(--bg);color:var(--fg);border:1px solid var(--border);border-radius:6px;padding:8px;font:13px system-ui;resize:vertical}
textarea:focus,input:focus,select:focus{outline:none;border-color:var(--accent)}
label{display:block;font-size:12px;color:#8b949e;margin-bottom:4px;margin-top:8px}
.row{display:flex;gap:12px;align-items:center;margin-top:12px;flex-wrap:wrap}
.hidden{display:none}
.filters{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:6px}
.filters button{padding:4px 14px;font-size:12px;background:var(--card);border:1px solid var(--border);color:var(--fg);border-radius:14px}
.filters button.active{background:var(--accent);border-color:var(--accent);color:#fff}
.toolbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:12px}
#toast{position:fixed;top:16px;right:16px;background:var(--good);color:#000;padding:10px 20px;border-radius:6px;font-weight:600;z-index:99;transition:opacity .3s}
/* 搜索进度悬浮提示：固定右上角、不拦截任何点击、搜索期间常驻、结束后自动收起 */
#search-status.search-float{position:fixed;top:52px;right:16px;background:var(--card);border:1px solid var(--border);color:var(--fg);padding:8px 14px;border-radius:8px;font-size:12px;line-height:1.5;max-width:340px;z-index:98;box-shadow:0 4px 14px rgba(0,0,0,.45);pointer-events:none}
/* 搜索进行中遮罩：全屏覆盖 + 居中进度面板，同时阻塞页面所有操作 */
#search-overlay{position:fixed;inset:0;background:rgba(13,17,23,.78);z-index:999;display:flex;align-items:center;justify-content:center}
#search-overlay .box{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:28px 36px;max-width:480px;width:90%;text-align:center;box-shadow:0 8px 30px rgba(0,0,0,.5)}
#search-overlay .spinner{width:34px;height:34px;border:3px solid var(--border);border-top-color:var(--accent);border-radius:50%;margin:0 auto 14px;animation:spin 1s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
#search-overlay .step{font-size:16px;font-weight:700;margin-bottom:6px}
#search-overlay .detail{font-size:13px;color:#8b949e;line-height:1.7;word-break:break-all}
#search-overlay .elapsed{font-size:12px;color:#8b949e;margin-top:10px}
.job-card{background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:12px 14px;margin-bottom:10px}
.job-card .top{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap}
.job-card .pos{font-weight:600}.job-card .comp{color:#8b949e;font-size:12px}
.job-card .meta{font-size:12px;color:#8b949e;margin-top:4px}
.job-card .jd{font-size:12px;color:#8b949e;margin-top:6px;max-height:48px;overflow:hidden}
.job-card .act{margin-top:8px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.job-card .apply-result{font-size:12px;margin-top:6px;padding:6px 10px;border-radius:6px;background:rgba(88,166,255,.08);color:var(--accent)}
.job-card .apply-result.ok{background:rgba(63,185,80,.08);color:var(--good)}
.job-card .apply-result.err{background:rgba(248,81,73,.08);color:var(--err)}
.risk-tag{padding:1px 8px;border-radius:8px;font-size:11px;background:#2a0a0a;color:var(--err)}
.reason{font-size:12px;color:var(--good)}
.kw{display:inline-block;background:var(--bg);border:1px solid var(--border);padding:2px 10px;border-radius:12px;margin:2px 4px 2px 0;font-size:12px}
.status-btns{display:flex;gap:4px;flex-wrap:wrap}
.status-btns button{padding:2px 8px;font-size:11px;border-radius:10px}
.warn-line{font-size:12px;color:var(--warn);margin:4px 0}
.env-chip{display:inline-flex;align-items:center;gap:6px;background:var(--bg);border:1px solid var(--border);border-radius:14px;padding:4px 12px;margin:4px 6px 4px 0;font-size:12px}
.env-chip .dot{width:8px;height:8px;border-radius:50%;background:#8b949e}
.env-chip .dot.ok{background:var(--good)}.env-chip .dot.err{background:var(--err)}.env-chip .dot.warn{background:var(--warn)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:760px){.grid2{grid-template-columns:1fr}.grid4{grid-template-columns:repeat(2,1fr)}}
</style></head>
<body>
<h1>🤖 JobBot Agent</h1>
<p class=sub>AI求职助手 · 本地运行 · 配置一次 LLM Key 即用 · 三大平台搜索 · AI 匹配评分</p>
<div id=toast style=opacity:0></div>
<div id=search-overlay class=hidden>
  <div class=box>
    <div class=spinner></div>
    <div class=step id=overlay-step>正在搜索…</div>
    <div class=detail id=overlay-detail></div>
    <div class=elapsed id=overlay-time></div>
  </div>
</div>

<section id=llm-section>
  <h3>🔑 第一步：配置 AI（LLM API Key）</h3>
  <div class=row>
    <div style="flex:2"><label>API 地址 (Base URL)</label><input type=text id=llm-base placeholder="https://api.deepseek.com/v1"></div>
    <div style="flex:2"><label>模型</label><input type=text id=llm-model placeholder="deepseek-chat"></div>
    <div style="flex:3"><label>API Key</label><input type=password id=llm-key placeholder="sk-..."></div>
  </div>
  <div class=row>
    <button onclick=saveLLM()>💾 保存 Key</button>
    <button class="btn-sm" onclick=testLLM()>🔌 测试连接</button>
    <span id=llm-status style="font-size:12px;color:var(--good)"></span>
  </div>
  <p style="font-size:12px;color:#8b949e;margin-top:8px">支持任何 OpenAI 兼容接口（DeepSeek / Kimi / 通义 / OpenAI…）。Key 只存在本地 config/llm.json。</p>
</section>

<section id=config-section>
  <h3 id=config-title>🚀 第二步：简历与求职意向</h3>
  <div class=grid2>
    <div>
      <label>上传简历（TXT / Word / PDF，AI 自动解析）</label>
      <div id=upload-area style="border:2px dashed var(--border);border-radius:8px;padding:14px;text-align:center;cursor:pointer;margin-bottom:10px" onclick="document.getElementById('resume-file').click()">
        <input type=file id=resume-file accept=".pdf,.doc,.docx,.txt" style=display:none onchange="uploadResume(this)">
        📎 点击上传 <span id=resume-name style=color:var(--good)></span>
      </div>
      <div id=resume-parse style="font-size:12px;color:#8b949e"></div>
    </div>
    <div>
      <label>意向描述（城市、学历、专业、目标岗位、技能…）</label>
      <textarea id=cfg-intent rows=5 placeholder="例：本科计算机，2027毕业，找南京 Python 后端开发实习，会用 Django/FastAPI，期望薪资3000-6000" oninput=scheduleSave()></textarea>
      <div class=row>
        <label style="margin:0">目标城市</label>
        <input type=text id=cfg-city value="南京" style="width:120px" oninput=scheduleSave()>
        <button onclick=saveConfig()>💾 保存意向</button>
        <span style="font-size:12px;color:#8b949e">输入后自动保存，搜索时也会自动保存，此按钮可不点</span>
      </div>
    </div>
  </div>
</section>

<section id=env-section class=hidden>
  <h3>🌐 平台与浏览器环境
    <button class="btn-sm" onclick=checkEnv()>🔍 检测环境</button>
    <button class="btn-sm" onclick=openLogin('boss_zhipin')>BOSS 登录</button>
    <button class="btn-sm" onclick=openLogin('wuyou')>51job 登录</button>
    <button class="btn-sm" onclick=openLogin('shixiseng')>实习僧登录</button>
  </h3>
  <div id=env-box></div>
  <p style="font-size:12px;color:#8b949e;margin-top:6px">51job 搜索无需浏览器；BOSS直聘/实习僧搜索与三大平台自动投递需要 Camofox 浏览器并登录一次。遇到验证码/风控请人工处理。</p>
</section>

<section id=login-section class=hidden>
  <h3>🔐 需要手动登录（JobBot 不会自动登录）</h3>
  <div id=login-box></div>
  <p style="font-size:12px;color:#8b949e;margin-top:6px">浏览器已停在登录页。请在弹出的浏览器窗口中手动完成登录（含验证码/扫码），然后回来点「已登录，继续」。确认登录前 JobBot 不会继续搜索或投递。</p>
</section>

<section id=search-section class=hidden>
  <h3>🔍 第三步：三平台搜索 + AI 评分
    <button onclick=runSearch()>⚡ 开始搜索</button>
    <span id=search-status class="search-float hidden"></span>
  </h3>
  <div id=profile-guide class="hidden" style="background:var(--bg);border:1px dashed var(--warn);border-radius:8px;padding:12px;margin-bottom:12px"></div>
  <div id=search-warnings></div>
  <div id=kw-box class=row style="margin-top:0"></div>
  <div class=filters id=job-platform-filters style="margin-bottom:8px"></div>
  <div id=job-list></div>
  <div id=pager style="display:none;text-align:center;margin:14px 0"></div>
</section>

<section id=stats-section class=hidden><h3>📊 投递总览</h3>
<div class=grid4 id=stats-grid></div></section>

<section id=table-section class=hidden>
  <h3>📋 投递记录 <span style="font-size:12px;color:#8b949e" id=record-count></span></h3>
  <div class=toolbar>
    <div class=filters id=platform-filters></div>
    <div class=filters id=status-filters></div>
    <div style="flex:1"></div>
    <button class=btn-sm onclick=toggleSort() id=sort-btn style="background:var(--card);color:var(--fg)">⏱ 时间 ↓</button>
    <button class=btn-sm onclick=exportCSV() style="background:var(--card);color:var(--fg)">📥 CSV</button>
  </div>
  <div style=overflow-x:auto><table><thead><tr>
    <th data-sort=company>公司</th><th data-sort=position>岗位</th><th data-sort=platform>平台</th><th data-sort=score>匹配</th><th data-sort=status>状态</th><th>操作</th><th data-sort=applied_at>时间</th>
  </tr></thead><tbody id=table-body></tbody></table></div>
  <p id=empty-msg style="text-align:center;color:#8b949e;padding:40px;display:none">暂无记录。点击上方「开始搜索」找岗位。</p>
</section>

<script>
let data={applications:[],stats:{}};
let llmCfg={};
let config={};
let settings={};
let loginPending=[];
let saveTimer=null;
let _resumeParse='';
let jobPage=1;
const loginPollers={};
const JOBS_PER_PAGE=10;
let platformFilter='all',statusFilter='all';
let sortKey='applied_at',sortDir='desc';
let expanded=null;
let profileMissing=[];
let jobPlatformFilter='all';

async function loadAll(){await Promise.all([loadData(),loadConfig(),loadLLM(),loadProfile()]);render();checkEnv();}
async function loadData(){const r=await fetch('/api/data');data=await r.json();}
async function loadConfig(){
  try{const r=await fetch('/api/config');config=await r.json();}catch(e){}
  let intent=config.intent||'';
  // 兼容旧版带【简历解析】标记的配置：自动拆成 手动意向 + 解析块
  _resumeParse=config.resume_parse||'';
  const mIdx=intent.indexOf('【简历解析】');
  if(mIdx>=0){
    _resumeParse=intent.slice(mIdx+6).replace(/^[，,]\s*/,'')||'';
    intent=intent.slice(0,mIdx).replace(/[，,]\s*$/,'');
  }
  document.getElementById('cfg-intent').value=intent?(intent+(_resumeParse?'，'+_resumeParse:'')):_resumeParse;
  if(config.city)document.getElementById('cfg-city').value=config.city;
  if(intent||_resumeParse)showApp();
}
async function loadLLM(){
  try{const r=await fetch('/api/llm');llmCfg=await r.json();
    document.getElementById('llm-base').value=llmCfg.base_url||'';
    document.getElementById('llm-model').value=llmCfg.model||'';
    if(llmCfg.has_key)document.getElementById('llm-key').placeholder='已保存 (sk-****)';
  }catch(e){}
}
async function loadProfile(){
  try{
    const r=await fetch('/api/profile');const d=await r.json();
    if(d.ok)renderProfileGuide(d);
  }catch(e){}
}
function renderProfileGuide(d){
  profileMissing=d.missing_fields||[];
  const box=document.getElementById('profile-guide');
  if(!profileMissing.length){box.innerHTML='';box.classList.add('hidden');return;}
  const labelMap={education:'最高学历',graduate_year:'毕业届别',expected_salary:'薪资期望（如 3000-6000）',job_type:'招聘类型'};
  const inputs={
    education:'<select id=pg-education><option value="">请选择</option>'+['高中','中专','大专','本科','硕士','博士'].map(x=>`<option>${x}</option>`).join('')+'</select>',
    graduate_year:'<input type=text id=pg-graduate_year placeholder="如 2027">',
    expected_salary:'<input type=text id=pg-expected_salary placeholder="如 3000-6000">',
    job_type:'<select id=pg-job_type><option value="">请选择</option>'+['实习','校招','社招'].map(x=>`<option>${x}</option>`).join('')+'</select>'
  };
  box.innerHTML='<div style="margin-bottom:6px"><strong>🪪 完善求职画像</strong>（补全后匹配评分更准）</div>'+
    profileMissing.map(k=>`<div style="margin:6px 0;max-width:280px"><label style="margin-top:0">${labelMap[k]||k}</label>${inputs[k]||''}</div>`).join('')+
    '<div class=row style="margin-top:10px"><button class="btn-sm btn-good" onclick="saveProfileGuide()">保存补全</button>'+
    '<button class="btn-sm" onclick="dismissProfileGuide()">暂不补全</button></div>';
  box.classList.remove('hidden');
}
async function saveProfileGuide(){
  const fields={
    education:document.getElementById('pg-education')?.value,
    graduate_year:document.getElementById('pg-graduate_year')?.value,
    expected_salary:document.getElementById('pg-expected_salary')?.value,
    job_type:document.getElementById('pg-job_type')?.value
  };
  let ok=true;
  for(const [k,v] of Object.entries(fields)){
    if(v===undefined||v==='')continue;
    const r=await fetch('/api/profile',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({field:k,value:v})});
    const d=await r.json();
    if(!d.ok){toast('❌ '+d.error);ok=false;break;}
  }
  if(ok){toast('✅ 画像已补全');loadProfile();}
}
function dismissProfileGuide(){
  document.getElementById('profile-guide').classList.add('hidden');
}
function showApp(){
  ['env-section','search-section','stats-section','table-section'].forEach(id=>{
    document.getElementById(id).classList.remove('hidden');
  });
}
function scheduleSave(){
  clearTimeout(saveTimer);
  saveTimer=setTimeout(autoSaveConfig,1200);
}
function splitIntent(cur){
  let intent=(cur||'').trim(), resumeParse=_resumeParse;
  if(resumeParse){
    const idx=(cur||'').lastIndexOf(resumeParse);
    if(idx>=0){
      intent=cur.slice(0,idx).replace(/[，,]\s*$/,'').trim();
    }else{
      // 解析块被手动改过：整段视为手动意向，解析块归零
      intent=cur.trim(); resumeParse='';
    }
  }
  return {intent:intent, resume_parse:resumeParse};
}
async function autoSaveConfig(){
  const sp=splitIntent(document.getElementById('cfg-intent').value);
  const cfg={intent:sp.intent, resume_parse:sp.resume_parse,
             city:document.getElementById('cfg-city').value.trim()||'南京'};
  try{
    await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(cfg)});
  }catch(e){}
}
function platformKey(name){
  const m={'BOSS直聘':'boss_zhipin','前程无忧':'wuyou','51job':'wuyou','实习僧':'shixiseng'};
  return m[name]||name;
}
function platformName(key){
  const m={'boss_zhipin':'BOSS直聘','wuyou':'51job','shixiseng':'实习僧'};
  return m[key]||key;
}
function showLoginRequired(keys){
  if(!keys||!keys.length)return;
  loginPending=[...new Set(keys.concat(loginPending))];
  renderLoginBox();
  document.getElementById('login-section').classList.remove('hidden');
}
function showSearchOverlay(step, detail){
  document.getElementById('overlay-step').textContent=step||'搜索中…';
  document.getElementById('overlay-detail').textContent=detail||'';
  document.getElementById('overlay-time').textContent='';
  document.getElementById('search-overlay').classList.remove('hidden');
}
function updateSearchOverlay(step, detail, secs){
  document.getElementById('overlay-step').textContent=step||'搜索中…';
  document.getElementById('overlay-detail').textContent=detail||'';
  document.getElementById('overlay-time').textContent='已耗时 '+secs+' 秒';
}
function hideSearchOverlay(){
  document.getElementById('search-overlay').classList.add('hidden');
}
function renderLoginBox(){
  const box=document.getElementById('login-box');
  if(!loginPending.length){box.innerHTML='';document.getElementById('login-section').classList.add('hidden');return;}
  box.innerHTML=loginPending.map(k=>`<span class="env-chip"><span class="dot warn"></span>${esc(platformName(k))}
    <button class="btn-sm" onclick="openLogin('${k}')">打开登录页</button>
    <button class="btn-sm btn-good" onclick="checkLogin('${k}')">已登录，继续</button></span>`).join('');
}
async function checkLogin(key){
  stopLoginPoll(key);
  const r=await fetch('/api/env/check',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({platform:key})});
  const d=await r.json();
  if(d.ok){
    toast('✅ '+platformName(key)+' 已登录，可继续操作');
    loginPending=loginPending.filter(x=>x!==key);
    renderLoginBox();
  }else{
    toast('❌ '+platformName(key)+' 还未登录：'+d.message);
  }
  checkEnv();
}
async function saveLLM(){
  const cfg={base_url:document.getElementById('llm-base').value.trim(),model:document.getElementById('llm-model').value.trim(),api_key:document.getElementById('llm-key').value.trim()};
  const r=await fetch('/api/llm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(cfg)});
  const d=await r.json();
  if(d.ok){toast('✅ Key 已保存');document.getElementById('llm-key').value='';loadLLM();}
  else toast('❌ '+d.error);
}
async function testLLM(){
  const s=document.getElementById('llm-status');s.textContent='测试中…';
  const r=await fetch('/api/llm/test',{method:'POST'});
  const d=await r.json();
  s.textContent=d.ok?('✅ '+d.reply):('❌ '+d.error);
}
async function uploadResume(input){
  if(!input.files[0])return;
  document.getElementById('resume-parse').textContent='⏳ AI 解析简历中（约10~30秒，需已配置 LLM Key）…';
  const fd=new FormData();fd.append('file',input.files[0]);
  const r=await fetch('/api/upload',{method:'POST',body:fd});
  const d=await r.json();
  document.getElementById('resume-name').textContent=' ✅ '+d._filename;
  document.getElementById('resume-parse').textContent=d._error||(d._warn||'');
  input.value='';  // 允许再次选择同一个文件重新解析
  let parsed=[];
  if(d.name)parsed.push('姓名:'+d.name);
  if(d.education)parsed.push('学历:'+d.education);
  if(d.school)parsed.push('学校:'+d.school);
  if(d.major)parsed.push('专业:'+d.major);
  if(d.position)parsed.push('意向岗位:'+d.position);
  if(d.city)parsed.push('目标城市:'+d.city);
  if(d.salary)parsed.push('期望薪资:'+d.salary);
  if(d.graduate_year)parsed.push('毕业年份:'+d.graduate_year);
  if(d.certificates&&d.certificates.length)parsed.push('证书:'+d.certificates.join('、'));
  if(d.skills&&d.skills.length)parsed.push('技能:'+d.skills.join('、'));
  if(d.experience)parsed.push('经历:'+d.experience);
  if(d._error){toast('❌ '+d._error);return;}
  if(parsed.length){
    const newParse=parsed.join('，');
    // 重传时替换旧解析块，而不是叠加：
    // 1) 剥掉末尾的旧解析块（_resumeParse）
    // 2) 若剩余部分仍是旧的解析块文本（以 姓名:/学历: 等结构化标签开头），一并丢弃
    let manual=document.getElementById('cfg-intent').value.trim();
    if(_resumeParse){
      const idx=manual.lastIndexOf(_resumeParse);
      if(idx>=0){ manual=manual.slice(0,idx).replace(/[，,]\s*$/,'').trim(); }
    }
    if(/^(姓名|学历|学校|专业|意向岗位|技能|证书|经历|期望薪资|毕业年份|目标城市)[:：]/.test(manual)) manual='';
    _resumeParse=newParse;
    document.getElementById('cfg-intent').value=manual?(manual+'，'+newParse):newParse;
    if(d.city)document.getElementById('cfg-city').value=d.city;
    showApp();
    toast('✅ 已用新简历刷新意向描述');
  }else{
    toast('✅ 简历已保存（未识别到结构化信息，可手动填写意向）');
    showApp();
  }
  await autoSaveConfig();
}
async function saveConfig(){
  const sp=splitIntent(document.getElementById('cfg-intent').value);
  const cfg={intent:sp.intent, resume_parse:sp.resume_parse,
             city:document.getElementById('cfg-city').value.trim()||'南京'};
  const r=await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(cfg)});
  const d=await r.json();
  if(d.ok){
    showApp();toast('✅ 意向已保存');
    if(d.missing_fields&&d.missing_fields.length)renderProfileGuide(d);
    else document.getElementById('profile-guide').classList.add('hidden');
  }
  else toast('❌ '+d.error);
}
async function checkEnv(){
  const box=document.getElementById('env-box');
  box.innerHTML='<span style="color:#8b949e">检测中…</span>';
  const r=await fetch('/api/env');const d=await r.json();
  renderEnv(d);
}
function renderEnv(d){
  const box=document.getElementById('env-box');
  let html='';
  html+='<span class="env-chip"><span class="dot '+(d.camofox?'ok':'err')+'"></span>Camofox '+(d.camofox?'已运行':'未运行')+'</span>';
  (d.platforms||[]).forEach(p=>{
    const st=(d.login_states||{})[p.key];
    let cls='',label='未检测';
    if(st===true){cls='ok';label='已登录';}
    else if(st===false){cls='err';label='未登录';}
    html+=`<span class="env-chip"><span class="dot ${cls}"></span>${esc(p.name)} ${label}</span>`;
  });
  box.innerHTML=html;
}
async function openLogin(platform){
  const r=await fetch('/api/env/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({platform})});
  const d=await r.json();
  if(d.ok){
    toast('✅ '+d.message);
    startLoginPoll(platform);
  }else{
    toast('❌ '+d.message);
  }
}
function stopLoginPoll(key){
  if(loginPollers[key]){clearTimeout(loginPollers[key]);delete loginPollers[key];}
}
function startLoginPoll(key){
  stopLoginPoll(key);
  let tries=0;
  (function tick(){
    tries++;
    fetch('/api/env/check',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({platform:key})})
      .then(r=>r.json())
      .then(d=>{
        if(d.ok){
          stopLoginPoll(key);
          toast('✅ '+platformName(key)+' 已登录成功，可直接开始搜索');
          loginPending=loginPending.filter(x=>x!==key);
          renderLoginBox();
          checkEnv();
        }else if(tries<90){
          loginPollers[key]=setTimeout(tick,3000);
        }else{
          toast('⏳ '+platformName(key)+' 登录等待超时，登录完成后可点「已登录，继续」确认');
        }
      })
      .catch(()=>{if(tries<90)loginPollers[key]=setTimeout(tick,3000);});
  })();
}
async function runSearch(){
  const intent=document.getElementById('cfg-intent').value.trim();
  const city=document.getElementById('cfg-city').value.trim()||'南京';
  if(!intent){toast('请先填写求职意向');return;}
  await autoSaveConfig();  // 搜索前自动保存，避免未点「保存意向」导致丢失
  const st=document.getElementById('search-status');
  document.getElementById('search-warnings').innerHTML='';
  const btn=document.querySelector('#search-section h3 button');
  btn.disabled=true;
  st.textContent='⏳ 正在启动搜索…';
  st.classList.remove('hidden');
  showSearchOverlay('正在启动搜索…','');
  const t0=Date.now();
  try{
    const r=await fetch('/api/search',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({intent,city})});
    const d=await r.json();
    if(!d.ok){
      toast('❌ '+d.error);st.textContent='❌ '+d.error;
      hideSearchOverlay();
      setTimeout(()=>st.classList.add('hidden'),8000);btn.disabled=false;return;
    }
    // 轮询进度：实时显示正在做什么
    const timer=setInterval(async ()=>{
      try{
        const sr=await fetch('/api/search/status');
        const s=await sr.json();
        const secs=Math.round((Date.now()-t0)/1000);
        st.textContent='⏳ '+esc(s.step||'搜索中')+'…（'+secs+'s）'+(s.detail?' · '+esc(s.detail):'');
        updateSearchOverlay(s.step||'搜索中…', s.detail||'', secs);
        if(s.running)return;
        clearInterval(timer);
        btn.disabled=false;
        if(s.error){
          st.textContent='❌ '+s.error;toast('❌ '+s.error);
          hideSearchOverlay();
          setTimeout(()=>st.classList.add('hidden'),8000);return;
        }
        hideSearchOverlay();
        renderSearchResult(s.result||{});
        const jobs=s.result&&s.result.jobs||[];
        const extra=[];
        if(s.result&&s.result.filtered)extra.push('已过滤 '+s.result.filtered+' 个不匹配/未核实岗位');
        if(s.result&&s.result.offline)extra.push('已过滤 '+s.result.offline+' 个已下线岗位');
        st.textContent=`共找到 ${jobs.length} 个匹配岗位${extra.length?'（'+extra.join('、')+'）':''}，点击「打开详情投递」自行查看并投递`;
        setTimeout(()=>st.classList.add('hidden'),10000);
      }catch(e){clearInterval(timer);btn.disabled=false;toast('❌ 搜索状态获取失败');st.textContent='❌ 搜索状态获取失败';hideSearchOverlay();setTimeout(()=>st.classList.add('hidden'),8000);}
    },1000);
  }catch(e){btn.disabled=false;toast('❌ 搜索启动失败');st.textContent='❌ 搜索启动失败';hideSearchOverlay();setTimeout(()=>st.classList.add('hidden'),8000);}
}
function renderSearchResult(d){
  document.getElementById('kw-box').innerHTML=(d.keywords||[]).map(k=>`<span class=kw>${esc(k)}</span>`).join('')||'';
  document.getElementById('search-warnings').innerHTML=(d.warnings||[]).map(w=>`<div class=warn-line>⚠ ${esc(w)}</div>`).join('');
  const kws=(d.keywords||[]).filter(Boolean);
  if(kws.length){
    const line=document.createElement('div');
    line.className='warn-line';
    line.textContent='更换关键词示例：'+kws.join('，');
    document.getElementById('search-warnings').appendChild(line);
  }
  if(d.login_required&&d.login_required.length){
    showLoginRequired(d.login_required);
  }else{
    loginPending=[];renderLoginBox();
  }
  checkEnv();
  jobPage=1;
  jobPlatformFilter='all';
  renderJobs(d.jobs||[], d);
  showApp();
}
function renderJobPlatformFilters(jobs){
  const el=document.getElementById('job-platform-filters');
  const platforms=[...new Set((jobs||[]).map(j=>j.platform).filter(Boolean))];
  if(!platforms.length){el.innerHTML='';return;}
  el.innerHTML='<button class="'+(jobPlatformFilter==='all'?'active':'')+'" onclick="setJobPlatformFilter(\'all\')">全部平台</button>'+
    platforms.map(p=>`<button class="${jobPlatformFilter===p?'active':''}" onclick="setJobPlatformFilter('${esc(p)}')">${esc(p)}</button>`).join('');
}
function setJobPlatformFilter(f){
  jobPlatformFilter=f;
  jobPage=1;
  renderJobs(window._lastJobs||[], window._lastSummary||{});
}
function renderJobs(jobs, summary){
  window._lastJobs=jobs||[];
  window._lastSummary=summary||{};
  const el=document.getElementById('job-list');
  renderJobPlatformFilters(jobs);
  const visible=jobPlatformFilter==='all'?(jobs||[]):(jobs||[]).filter(j=>j.platform===jobPlatformFilter);
  if(!visible.length){
    const parts=[];
    if(summary&&summary.filtered)parts.push('过滤掉 '+summary.filtered+' 个不匹配/未核实岗位');
    if(summary&&summary.offline)parts.push('过滤掉 '+summary.offline+' 个已下线岗位');
    el.innerHTML=(jobs&&jobs.length)
      ?'<p style="color:#8b949e;line-height:2">😕 当前筛选平台下没有岗位，试试「全部平台」。</p>'
      :'<p style="color:#8b949e;line-height:2">😕 没有找到符合条件的岗位'+
        (parts.length?'（'+parts.join('、')+'）':'')+'。<br>'+
        '建议：完善「意向描述」（目标城市、岗位方向、技能、薪资期望），或调整关键词/平台过滤规则，然后重新搜索。</p>';
    document.getElementById('pager').style.display='none';
    return;
  }
  const totalPages=Math.ceil(visible.length/JOBS_PER_PAGE);
  if(jobPage>totalPages)jobPage=totalPages;
  const start=(jobPage-1)*JOBS_PER_PAGE;
  const pageJobs=visible.slice(start,start+JOBS_PER_PAGE);
  el.innerHTML=pageJobs.map((j,idx)=>{
    const i=start+idx;  // 全局下标，投递/记录用
    const breakdown=j.score_breakdown||{};
    const chipLabels={hard_skills:'硬技能',project_intern:'项目',edu_major:'学历专业',cert_lang:'证书',city_industry:'城市方向'};
    const chips=Object.keys(breakdown).filter(k=>breakdown[k]!==undefined)
      .map(k=>`<span class=chip>${chipLabels[k]||k} ${breakdown[k]}</span>`).join('');
    const evs=(j.evidence||[]).slice(0,3).map(e=>
      `<div class=ev>✅ ${esc(e.item||e.type)}${e.confidence>=1?'（命中）':e.confidence>=0.5?'（部分）':'（弱）'}：${esc((e.evidence||'').slice(0,60))}</div>`).join('');
    const gaps=(j.gaps||[]).slice(0,3).map(g=>`<div class=gap>❌ ${esc(g)}</div>`).join('');
    return `
  <div class=job-card id="jc-${i}">
    <div class=top>
      <div><span class=pos>${esc(j.position)}</span> ${j.risk==='suspicious'?'<span class=risk-tag>⚠ 可疑</span>':''}<br>
      <span class=comp>${esc(j.company)}</span></div>
      <div style="text-align:right">
        <span class=score-badge>${j.score}分 · ${esc(j.grade||'')}</span> ${'⭐'.repeat(j.star||0)}
        ${j.score_failed?'<div class=gap>⚠ 评分失败，按备选展示</div>':''}
        ${chips?`<div class=chips>${chips}</div>`:''}
      </div>
    </div>
    <div class=meta>${j.platform?('🏢 '+esc(j.platform)+' · '):''}💰 ${esc(j.salary||'—')} · 📍 ${esc(j.location||'—')} · 🎓 ${esc(j.degree||'—')} · ⏱ ${esc(j.work_year||'—')}</div>
    ${evs?`<div class=ev-box>${evs}</div>`:''}
    ${gaps?`<div class=gap-box>${gaps}</div>`:''}
    ${j.reason?`<div class=reason>💡 ${esc(j.reason)}</div>`:''}
    <div class=jd>${esc((j.jd_summary||'').slice(0,120))}</div>
    <div class=act>
      ${j.url?`<a href="${esc(j.url)}" target=_blank class="btn-sm btn-good" style="display:inline-block;padding:4px 12px">🔗 打开详情投递</a>`:''}
      <button class=btn-sm onclick=addJob(${i})>📝 加入记录</button>
      ${j.risk==='suspicious'?`<span style="font-size:12px;color:var(--err)">可疑词: ${esc((j.risk_hits||[]).join('、'))}</span>`:''}
    </div>
  </div>`;
  }).join('');
  renderPager(visible.length);
}
function renderPager(total){
  const p=document.getElementById('pager');
  const pages=Math.max(1,Math.ceil(total/JOBS_PER_PAGE));
  p.style.display='block';
  p.innerHTML=`<button class=btn-sm onclick=prevPage() ${jobPage<=1?'disabled':''}>← 上一页</button>`+
    `<span style="margin:0 12px;color:#8b949e">第 ${jobPage} / ${pages} 页 · 共 ${total} 个岗位</span>`+
    `<button class=btn-sm onclick=nextPage() ${jobPage>=pages?'disabled':''}>下一页 →</button>`;
}
function prevPage(){
  if(jobPage>1){jobPage--;renderJobs(window._lastJobs||[]);}
}
function nextPage(){
  const total=(window._lastJobs||[]).length;
  if(jobPage*JOBS_PER_PAGE<total){jobPage++;renderJobs(window._lastJobs||[]);}
}
async function addJob(i){
  const j=window._lastJobs[i];
  const r=await fetch('/api/apply',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.assign({},j,{_manual:true}))});
  const d=await r.json();
  if(d.ok){toast('✅ 已加入记录');loadData();}
  else toast('❌ '+d.message||d.error);
}
async function setStatus(url,status){
  const r=await fetch('/api/status',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url,status})});
  const d=await r.json();
  if(d.ok){toast('✅ 状态已更新');loadData();}
  else toast('❌ '+d.error);
}
function toggleSort(){
  if(sortKey==='applied_at'&&sortDir==='desc'){sortKey='score';sortDir='desc';}
  else if(sortKey==='score'&&sortDir==='desc'){sortKey='applied_at';sortDir='asc';}
  else if(sortKey==='applied_at'&&sortDir==='asc'){sortKey='score';sortDir='asc';}
  else{sortKey='applied_at';sortDir='desc';}
  const labels={'applied_at':sortDir==='desc'?'⏱ 时间 ↓':'⏱ 时间 ↑','score':sortDir==='desc'?'⭐ 评分 ↓':'⭐ 评分 ↑'};
  document.getElementById('sort-btn').textContent=labels[sortKey];
  render();
}
function exportCSV(){
  const rows=filteredRows();
  const hdr=['公司','岗位','平台','薪资','地点','评分','状态','联系人','投递时间','JD摘要'];
  const csv=[hdr.join(',')];
  rows.forEach(a=>csv.push([a.company||'',a.position||'',a.platform||'',a.salary||'',a.location||'',a.score||'',a.status||'',a.hr_name||a.contact_person||'',(a.applied_at||'').slice(0,10),'"'+(a.jd_summary||'').replace(/"/g,'""')+'"'].join(',')));
  const blob=new Blob(['\uFEFF'+csv.join('\n')],{type:'text/csv;charset=utf-8'});
  const u=URL.createObjectURL(blob);
  const el=document.createElement('a');el.href=u;el.download='jobbot-export.csv';el.click();
  URL.revokeObjectURL(u);
  toast('✅ CSV 已下载');
}
function filteredRows(){
  let apps=data.applications||[];
  if(platformFilter!=='all')apps=apps.filter(a=>a.platform===platformFilter);
  if(statusFilter!=='all')apps=apps.filter(a=>a.status===statusFilter);
  apps.sort((a,b)=>{
    const va=a[sortKey]||'',vb=b[sortKey]||'';
    if(sortKey==='score')return sortDir==='desc'?(vb-va):(va-vb);
    return sortDir==='desc'?String(vb).localeCompare(String(va)):String(va).localeCompare(String(vb));
  });
  return apps;
}
function render(){
  expanded=null;
  const apps=data.applications||[],s=data.stats||{};
  document.getElementById('stats-grid').innerHTML=[
    {n:s.total_applied||0,l:'总记录',c:'var(--accent)'},
    {n:s.hr_replied||0,l:'HR 回复',c:'var(--good)'},
    {n:s.interview_scheduled||0,l:'约面试',c:'var(--warn)'},
    {n:s.rejected||0,l:'已拒绝',c:'var(--err)'}
  ].map(x=>`<div class=stat-card><div class=num style=color:${x.c}>${x.n}</div><div class=lbl>${x.l}</div></div>`).join('');
  const platforms=[...new Set(apps.map(a=>a.platform).filter(Boolean))];
  document.getElementById('platform-filters').innerHTML=
    '<button onclick=setPlatformFilter("all") class='+(platformFilter==='all'?'active':'')+'>全部平台</button>'+
    platforms.map(p=>`<button onclick=setPlatformFilter("${p}") class=${platformFilter===p?'active':''}>${p}</button>`).join('');
  const statuses=[...new Set(apps.map(a=>a.status).filter(Boolean))];
  const statusLabel={discovered:'新发现',applied:'已投递',hr_replied:'已回复',interviewing:'面试中',interview_scheduled:'已约面试',offered:'Offer',rejected:'已拒绝'};
  document.getElementById('status-filters').innerHTML=
    '<button onclick=setStatusFilter("all") class='+(statusFilter==='all'?'active':'')+'>全部状态</button>'+
    statuses.map(s=>`<button onclick=setStatusFilter("${s}") class=${statusFilter===s?'active':''}>${statusLabel[s]||s}</button>`).join('');
  const rows=filteredRows();
  document.getElementById('record-count').textContent=`${rows.length} 条`;
  document.getElementById('empty-msg').style.display=rows.length?'none':'block';
  const badge={discovered:'badge-discovered',applied:'badge-applied',hr_replied:'badge-hr_replied',interviewing:'badge-interviewing',interview_scheduled:'badge-interviewing',offered:'badge-offered',rejected:'badge-rejected'};
  const statusFlow={discovered:['applied'],applied:['hr_replied','interview_scheduled','rejected'],hr_replied:['interview_scheduled','rejected'],interviewing:['offered','rejected'],interview_scheduled:['offered','rejected'],offered:[],rejected:[]};
  const flowLabel={applied:'已投递',hr_replied:'已回复',interview_scheduled:'约面试',interviewing:'面试中',offered:'Offer',rejected:'拒绝'};
  document.getElementById('table-body').innerHTML=rows.map((a,i)=>{
    const s=a.status||'discovered';
    const sc=a.score||0;
    const stars=sc>5?`${sc}分`:('<span class=stars>'+'⭐'.repeat(sc)+'</span>'||'—');
    const btns=(statusFlow[s]||[]).map(ns=>`<button class="btn-sm ${ns==='rejected'?'btn-err':ns==='offered'?'btn-good':''}" onclick="event.stopPropagation();setStatus('${esc(a.url)}','${ns}')">${flowLabel[ns]}</button>`).join('');
    return `<tr class=main-row onclick="toggleDetail(${i},this)" data-idx=${i}>
      <td>${esc(a.company)||'—'}</td><td>${a.url?`<a href="${esc(a.url)}" target=_blank onclick="event.stopPropagation()">${esc(a.position)||'—'}</a>`:(esc(a.position)||'—')}</td>
      <td>${esc(a.platform)||'—'}</td><td>${stars}</td>
      <td><span class="badge ${badge[s]||'badge-discovered'}">${statusLabel[s]||s}</span></td>
      <td><div class=status-btns>${btns}</div></td>
      <td>${(a.applied_at||'').slice(0,10)}</td></tr>`+
      `<tr class="expand-row hidden" id=detail-${i}><td colspan=7>${detailHTML(a)}</td></tr>`;
  }).join('');
}
function detailHTML(a){
  let h='';
  if(a.jd_summary)h+=`<p><strong>📝 JD摘要：</strong>${esc(a.jd_summary)}</p>`;
  if(a.salary)h+=`<p><strong>💰 薪资：</strong>${esc(a.salary)}</p>`;
  if(a.location)h+=`<p><strong>📍 地点：</strong>${esc(a.location)}</p>`;
  if(a.hr_name)h+=`<p><strong>👤 联系人：</strong>${esc(a.hr_name)}</p>`;
  if(a.reason)h+=`<p><strong>💡 评分理由：</strong>${esc(a.reason)}</p>`;
  if(a.score_breakdown)h+=`<p><strong>📊 分项分：</strong>${esc(JSON.stringify(a.score_breakdown))}</p>`;
  if(a.evidence&&a.evidence.length)h+=`<p><strong>✅ 命中证据：</strong>${a.evidence.map(e=>esc(e.item+(e.evidence?'（'+e.evidence.slice(0,50)+'）':''))).join('；')}</p>`;
  if(a.gaps&&a.gaps.length)h+=`<p><strong>❌ 缺口：</strong>${esc(a.gaps.join('；'))}</p>`;
  if(a.notes)h+=`<p><strong>📌 备注：</strong>${esc(a.notes)}</p>`;
  return h||'<span style=color:#8b949e>暂无详细信息</span>';
}
function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function toggleDetail(idx,row){
  const el=document.getElementById('detail-'+idx);
  if(expanded&&expanded!==idx){document.getElementById('detail-'+expanded).classList.add('hidden');}
  el.classList.toggle('hidden');
  expanded=el.classList.contains('hidden')?null:idx;
}
function setPlatformFilter(f){platformFilter=f;render();}
function setStatusFilter(f){statusFilter=f;render();}
function toast(m){
  const t=document.getElementById('toast');t.textContent=m;t.style.opacity='1';
  setTimeout(()=>t.style.opacity='0',3000);
}
loadAll();
setInterval(loadData,30000);
</script></body></html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == '/':
            self._html(HTML)
        elif self.path == '/api/data':
            self._json(engine.load_db())
        elif self.path == '/api/config':
            self._json(self._read_config())
        elif self.path == '/api/llm':
            cfg = load_config()
            self._json({"base_url": cfg["base_url"], "model": cfg["model"],
                        "has_key": bool(cfg["api_key"])})
        elif self.path == '/api/env':
            self._json(self._env_status())
        elif self.path == '/api/profile':
            self._handle_profile()
        elif self.path == '/api/search/status':
            self._json(self._search_status())
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == '/api/upload':
            self._handle_upload()
        elif self.path == '/api/config':
            self._handle_config()
        elif self.path == '/api/llm':
            self._handle_llm()
        elif self.path == '/api/llm/test':
            self._handle_llm_test()
        elif self.path == '/api/search':
            self._handle_search()
        elif self.path == '/api/apply':
            self._handle_apply()
        elif self.path == '/api/status':
            self._handle_status()
        elif self.path == '/api/profile':
            self._handle_profile()
        elif self.path == '/api/env/login':
            self._handle_env_login()
        elif self.path == '/api/env/check':
            self._handle_env_check()
        else:
            self.send_error(404)

    # ---- LLM ----
    def _handle_llm(self):
        try:
            cfg = self._body_json()
            existing = load_config()
            if cfg.get("base_url"):
                existing["base_url"] = cfg["base_url"]
            if cfg.get("model"):
                existing["model"] = cfg["model"]
            if cfg.get("api_key"):
                existing["api_key"] = cfg["api_key"]
            save_config(existing)
            self._json({"ok": True})
        except Exception as e:
            self._json({"ok": False, "error": str(e)})

    def _handle_llm_test(self):
        try:
            reply = test_connection()
            self._json({"ok": True, "reply": reply.strip()[:80]})
        except Exception as e:
            self._json({"ok": False, "error": str(e)[:200]})

    # ---- Config ----
    def _handle_config(self):
        try:
            cfg = self._body_json()
            CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
            enriched = engine.enrich_profile(cfg.get("intent", ""),
                                             cfg.get("resume_parse", ""),
                                             cfg.get("city", "南京"))
            self._json({"ok": True,
                        "missing_fields": enriched["missing_fields"],
                        "extract_failed": enriched["extract_failed"]})
        except Exception as e:
            self._json({"ok": False, "error": str(e)})

    def _handle_profile(self):
        """画像：GET 返回公开字段与缺失字段；POST 补全/修正单个字段。"""
        try:
            profile = engine.load_user_profile()
            if self.command == "POST":
                body = self._body_json()
                field = body.get("field", "")
                value = body.get("value")
                if field not in ("education", "graduate_year", "major", "skills",
                                 "certificates", "expected_cities", "expected_jobs",
                                 "expected_salary", "job_type"):
                    self._json({"ok": False, "error": "不支持的画像字段"})
                    return
                if field == "education" and value not in ("高中", "中专", "大专",
                                                          "本科", "硕士", "博士"):
                    self._json({"ok": False, "error": "学历取值不合法"})
                    return
                if field == "job_type" and value not in ("实习", "校招", "社招"):
                    self._json({"ok": False, "error": "招聘类型取值不合法"})
                    return
                if field == "graduate_year":
                    try:
                        value = int(value)
                    except (TypeError, ValueError):
                        self._json({"ok": False, "error": "毕业届别需为年份数字"})
                        return
                if field == "expected_salary":
                    if isinstance(value, str):
                        parts = re.split(r"[-~至,，]", value.strip())
                        if len(parts) == 2:
                            try:
                                value = [int(parts[0]), int(parts[1])]
                            except ValueError:
                                value = None
                    if not (isinstance(value, list) and len(value) == 2):
                        self._json({"ok": False, "error": "薪资期望格式如 3000-6000"})
                        return
                profile[field] = value
                engine.save_profile(profile)
            missing = engine.profile_missing_fields(profile)
            public = {k: profile.get(k) for k in (
                "education", "graduate_year", "major", "skills", "certificates",
                "expected_cities", "expected_jobs", "expected_salary", "job_type")}
            self._json({"ok": True, "profile": public, "missing_fields": missing,
                        "extract_failed": bool(profile.get("_extract_failed"))})
        except Exception as e:
            self._json({"ok": False, "error": str(e)})

    # ---- Search ----
    def _handle_search(self):
        if SEARCH_TASK.get("running"):
            self._json({"ok": False, "error": "已有搜索正在进行，请稍候"})
            return
        body = self._body_json()
        intent = body.get("intent", "")
        if not intent or len(intent.strip()) < 4:
            self._json({"ok": False, "error": "请先填写求职意向（城市、岗位、技能等）"})
            return
        progress = {"step": "准备中", "detail": ""}
        SEARCH_TASK.update({"running": True, "progress": progress,
                            "result": None, "error": None})

        def _run():
            try:
                result = engine.run_search(intent, body.get("city", "南京"),
                                           progress=progress)
                SEARCH_TASK["result"] = result
            except Exception as e:
                SEARCH_TASK["error"] = str(e)[:300]
            finally:
                SEARCH_TASK["running"] = False

        threading.Thread(target=_run, daemon=True).start()
        self._json({"ok": True, "started": True})

    def _handle_search_status(self):
        self._json(self._search_status())

    def _search_status(self):
        return {
            "running": SEARCH_TASK.get("running", False),
            "step": SEARCH_TASK.get("progress", {}).get("step", ""),
            "detail": SEARCH_TASK.get("progress", {}).get("detail", ""),
            "result": SEARCH_TASK.get("result"),
            "error": SEARCH_TASK.get("error"),
        }

    # ---- Apply ----
    def _handle_apply(self):
        if not APPLY_LOCK.acquire(blocking=False):
            self._json({"ok": False, "message": "已有投递在进行中，请稍候"})
            return
        try:
            body = self._body_json()
            manual = body.pop("_manual", False)
            if manual:
                # 新流程：用户先自行投递，再点「加入记录」→ 默认状态直接记为已投递
                rec = engine.add_application(body, status="applied")
                self._json({"ok": True, "message": "已加入记录（已投递）", "record": rec})
            else:
                result = engine.apply_job(body)
                if result.get("ok"):
                    self._json({"ok": True, "message": result.get("message", "投递成功")})
                else:
                    self._json({"ok": False, "message": result.get("message", "投递失败"),
                                "need_login": result.get("need_login", False)})
        except ValueError as e:
            self._json({"ok": False, "message": str(e)})
        except Exception as e:
            self._json({"ok": False, "message": str(e)[:300]})
        finally:
            APPLY_LOCK.release()

    # ---- Status ----
    def _handle_status(self):
        try:
            body = self._body_json()
            url, status = body.get("url", ""), body.get("status", "")
            if not url or not status:
                self._json({"ok": False, "error": "缺少 url 或 status"})
                return
            self._json(engine.update_status(url, status))
        except Exception as e:
            self._json({"ok": False, "error": str(e)[:200]})

    # ---- Environment ----
    def _env_status(self):
        import browser
        platforms = []
        for key, pcfg in engine.load_platforms().items():
            platforms.append({
                "key": key,
                "name": pcfg.get("name", key),
                "enabled": bool(pcfg.get("enabled")),
                "requires_browser": bool(pcfg.get("requires_browser")),
            })
        return {"camofox": browser.camofox_available(), "platforms": platforms,
                "login_states": engine.get_login_states()}

    def _handle_env_login(self):
        import browser
        body = self._body_json()
        self._json(browser.open_login(body.get("platform", "")))

    def _handle_env_check(self):
        import browser
        body = self._body_json()
        res = browser.check_login(body.get("platform", ""))
        engine.mark_login(body.get("platform", ""), bool(res.get("ok")))
        self._json(res)

    # ---- Upload & resume parse ----
    def _handle_upload(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            ct = self.headers.get('Content-Type', '')
            if 'multipart' not in ct:
                self._json({'_error': '上传失败：非 multipart'})
                return
            boundary = ct.split('boundary=')[1].encode()
            for part in body.split(b'--' + boundary):
                if b'filename=' not in part:
                    continue
                hdr, _, data = part.partition(b'\r\n\r\n')
                fn = part.split(b'filename="')[1].split(b'"')[0].decode(errors="ignore")
                data = data.rstrip(b'\r\n--')
                ext = os.path.splitext(fn)[1].lower()
                if ext not in ('.txt', '.pdf', '.doc', '.docx'):
                    self._json({'_error': '不支持的文件类型，请上传 TXT/Word/PDF'})
                    return
                safe_name = f"{uuid.uuid4().hex[:8]}{ext}"
                path = RESUME_DIR / safe_name
                path.write_bytes(data)
                extracted = self._parse_resume(path)
                extracted['_filename'] = fn
                self._json(extracted)
                return
            self._json({'_error': '上传失败：未找到文件'})
        except Exception as e:
            self._json({'_error': f'上传失败：{e}'})

    def _extract_text(self, path: Path) -> tuple[str, str]:
        """抽取文件全文文本。返回 (文本, 警告)。"""
        ext = path.suffix.lower()
        text = ""
        warn = ""
        if ext == ".txt":
            raw = path.read_bytes()
            text = raw.decode("utf-8", errors="ignore")
            if len([c for c in text if c == '\ufffd']) > len(text) * 0.1:
                text = raw.decode("gbk", errors="ignore")
        elif ext == ".docx":
            try:
                with zipfile.ZipFile(path) as z:
                    xml = z.read("word/document.xml")
                root = ET.fromstring(xml)
                ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                paras = ["".join(t.text or "" for t in p.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"))
                         for p in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p")]
                text = "\n".join(p for p in paras if p.strip())
            except Exception as e:
                return "", f"Word 解析失败：{e}"
        elif ext == ".pdf":
            try:
                from pypdf import PdfReader
                reader = PdfReader(str(path))
                text = "\n".join((p.extract_text() or "") for p in reader.pages)
            except Exception:
                text = ""
            if not text.strip():
                # 无 pypdf 或提取失败 → 用内置零依赖提取器
                try:
                    from pdftext import extract_pdf_text
                    text = extract_pdf_text(path.read_bytes())
                except Exception:
                    text = ""
            if not text.strip():
                return "", ("这份 PDF 无法直接读取文字（可能是扫描件/图片版或加密 PDF）。"
                            "建议用 Word/WPS 打开后另存为 docx 再上传，或直接在下方手动填写求职意向。")
        elif ext == ".doc":
            return "", "旧版 .doc 无法直接解析，请另存为 .docx 或 .txt"
        return text[:8000], warn

    def _llm_parse(self, text: str) -> dict | None:
        """LLM 分析简历全文，提取结构化信息。失败返回 None。"""
        prompt = (
            "你是简历信息提取助手。请从简历文本中提取求职者信息，只返回 JSON（不要 markdown 包裹）。\n"
            "字段不存在就填空字符串或空列表，不要编造：\n"
            '{"name":"姓名","education":"最高学历(大专/本科/硕士/博士/中专/高中)","school":"毕业学校",'
            '"major":"专业","position":"求职意向/意向岗位(多个用、分隔)","skills":["技能"],'
            '"city":"期望/目标城市","salary":"期望薪资","graduate_year":毕业年份(数字或空),'
            '"work_years":"工作年限","certificates":["证书"],"experience":"用一句话概括经历亮点(50字内)"}\n'
            f"简历文本：\n{text}"
        )
        try:
            data = chat_json([{"role": "user", "content": prompt}], temperature=0.1)
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        result: dict = {}
        for key in ("name", "education", "school", "major", "position", "city",
                    "salary", "work_years", "experience"):
            v = data.get(key)
            if isinstance(v, str) and v.strip():
                result[key] = v.strip()[:60]
        gv = data.get("graduate_year")
        if isinstance(gv, (int, str)) and str(gv).strip() and str(gv) != "0":
            result["graduate_year"] = str(gv).strip()[:8]
        for key in ("skills", "certificates"):
            v = data.get(key)
            if isinstance(v, list):
                cleaned = [str(x).strip() for x in v if str(x).strip()]
                if cleaned:
                    result[key] = cleaned[:12]
        return result if result else None

    def _regex_parse(self, text: str) -> dict:
        """规则解析兜底（LLM 不可用时的降级方案）。"""
        result: dict = {}

        text = (text or "")[:5000]
        m = re.search(r'(?:姓名|名字)[:：\s]*([\u4e00-\u9fa5]{2,4})', text)
        if m:
            result['name'] = m.group(1)
        DEGREE = '大专|本科|硕士|博士|中专|高中|研究生'
        # 学历：标准格式「学历：本科」
        m = re.search(r'(?:学历|教育)[:：\s]*(' + DEGREE + ')', text)
        if m:
            result['education'] = m.group(1)
        # 学校 + 学历 + 专业 同行（如：江西服装学院 本科 播音与主持艺术 2018-2022）
        m = re.search(r'([\u4e00-\u9fa5]{2,20}(?:大学|学院|学校))[\s　]*(' + DEGREE + r')[\s　]*([\u4e00-\u9fa5A-Za-z（）()]{2,20})', text)
        if m:
            result['school'] = m.group(1)
            result.setdefault('education', m.group(2))
            result.setdefault('major', m.group(3))
        # 学历：非标准格式「27岁 | 本科 | 党员」
        if 'education' not in result:
            m = re.search(r'\d+\s*岁[^。\n]{0,20}[|｜]\s*(' + DEGREE + ')', text)
            if m:
                result['education'] = m.group(1)
        # 学历：全文兜底（简历里出现「本科背景」等）
        if 'education' not in result:
            m = re.search('(' + DEGREE + ')', text)
            if m:
                result['education'] = m.group(1)
        # 专业：标准格式「专业：播音与主持艺术」
        if 'major' not in result:
            m = re.search(r'(?:专业)[:：\s]*([\u4e00-\u9fa5]{2,20})', text)
            if m:
                result['major'] = m.group(1)
        m = re.search(r'(?:求职意向|意向岗位|应聘岗位|目标岗位)[:：\s]*((?:(?!期望城市|目标城市|意向城市|现居|工作地点|手机|技能|学历|专业|姓名|求职意向)[\u4e00-\u9fa5A-Za-z0-9、，,()（）/+ ]){2,40})', text)
        if m:
            result['position'] = m.group(1).strip()[:40]
        city = None
        m = re.search(r'(?:期望城市|目标城市|意向城市|现居(?:城市|地|地址)|工作(?:地点|城市))[:：\s]*([\u4e00-\u9fa5]{2,6})', text)
        if m and m.group(1) in engine.CITY_CODES:
            city = m.group(1)
        if not city:
            for c in engine.CITY_CODES:
                if c in text:
                    city = c
                    break
        if city:
            result['city'] = city
        m = re.search(r'1[3-9]\d{9}', text)
        if m:
            result['phone'] = m.group(0)
        known = ['PLC', 'CAD', 'Python', 'Java', 'C++', 'SQL', 'Excel', '电工', '自动化',
                 '电气', '嵌入式', '单片机', 'Linux', 'ROS', 'SolidWorks', '西门子',
                 '三菱', 'ABB', 'PCB', 'FPGA', 'MATLAB', 'Office', 'Django', 'FastAPI',
                 'React', 'Vue', 'Docker', 'Git', 'MySQL', 'Redis']
        found = [k for k in known if k.lower() in text.lower()]
        if found:
            result['skills'] = found[:8]
        return result

    def _parse_resume(self, path: Path) -> dict:
        """简历解析：抽取全文 → LLM 分析 → 失败降级规则解析。"""
        text, warn = self._extract_text(path)
        if not text:
            return {"_warn": warn or "未能从文件中提取到文本内容"}
        result = self._llm_parse(text)
        if result:
            if warn:
                result["_warn"] = warn
            return result
        result = self._regex_parse(text)
        if not result:
            return {"_warn": warn or "未识别到结构化信息，已将简历保存，可手动填写意向"}
        result["_warn"] = "LLM 解析不可用，已用规则解析（配置 API Key 后可启用 AI 解析）"
        return result

    def _body_json(self):
        length = int(self.headers.get('Content-Length', 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def _read_config(self):
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            try:
                return json.loads(CONFIG_TEMPLATE.read_text(encoding="utf-8", errors="ignore"))
            except Exception:
                return {}

    def _html(self, h):
        self._respond(200, 'text/html', h)

    def _json(self, d):
        self._respond(200, 'application/json', json.dumps(d, ensure_ascii=False))

    def _respond(self, code, ct, body):
        self.send_response(code)
        self.send_header('Content-Type', f'{ct}; charset=utf-8')
        self.end_headers()
        self.wfile.write(body.encode('utf-8'))


if __name__ == '__main__':
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        if s.connect_ex(("127.0.0.1", PORT)) == 0:
            print(f"⚠️ 端口 {PORT} 已被占用：JobBot 可能已在运行，请先关闭旧实例再启动（或直接访问 http://localhost:{PORT}）。")
            sys.exit(1)
    print(f'JobBot Dashboard → http://localhost:{PORT}')
    print('使用流程：配置 LLM Key → 上传简历/填意向 → 开始搜索 → 点「投递」')
    try:
        http.server.ThreadingHTTPServer(('127.0.0.1', PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            import browser
            browser.stop_camofox()
        except Exception:
            pass
