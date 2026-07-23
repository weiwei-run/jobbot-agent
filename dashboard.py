#!/usr/bin/env python3
"""JobBot Dashboard — python dashboard.py → http://localhost:9379
ponytail: stdlib HTTP server + single inline HTML, data via local JSON."""

import http.server, json, os, sys
from pathlib import Path

PORT = 9379
ROOT = Path(__file__).parent
DATA_FILE = ROOT / "data" / "applications.json"
CONFIG_FILE = ROOT / "config" / "user_profile.json"
CONFIG_TEMPLATE = ROOT / "config" / "user_profile_template.json"

os.makedirs(ROOT / "data", exist_ok=True)
if not DATA_FILE.exists():
    DATA_FILE.write_text(json.dumps({"applications": [], "stats": {"total_applied": 0, "hr_replied": 0, "interview_scheduled": 0, "rejected": 0}}, ensure_ascii=False, indent=2), encoding="utf-8")

HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>JobBot · AI求职助手</title>
<style>
:root{--bg:#0d1117;--fg:#e6edf3;--accent:#58a6ff;--good:#3fb950;--warn:#d29922;--err:#f85149;--card:#161b22;--border:#30363d}
*{box-sizing:border-box;margin:0;padding:0}
body{font:14px/1.6 system-ui,sans-serif;background:var(--bg);color:var(--fg);padding:20px;max-width:1100px;margin:0 auto}
h1{font-size:22px;margin-bottom:4px}.sub{color:#8b949e;margin-bottom:20px;font-size:13px}
section{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:18px;margin-bottom:16px}
h3{font-size:15px;margin-bottom:12px;display:flex;align-items:center;gap:8px}
.grid4{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.stat-card{background:var(--bg);border-radius:8px;padding:14px;text-align:center}
.stat-card .num{font-size:28px;font-weight:700}.stat-card .lbl{font-size:12px;color:#8b949e;margin-top:2px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;padding:8px 10px;color:#8b949e;font-weight:500;border-bottom:1px solid var(--border);cursor:pointer;user-select:none;white-space:nowrap}
th:hover{color:var(--fg)}
td{padding:8px 10px;border-bottom:1px solid var(--border)}
tbody tr.main-row{cursor:pointer}tbody tr.main-row:hover td{background:rgba(88,166,255,.08)}
tr.expand-row td{border-bottom:1px solid var(--accent);padding:12px 14px;background:rgba(88,166,255,.04);font-size:13px}
tr.expand-row strong{color:var(--accent)}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.badge{padding:2px 8px;border-radius:10px;font-size:11px;white-space:nowrap}
.badge-applied{background:#2a1f0a;color:var(--warn)}.badge-replied{background:#0a1f2a;color:var(--accent)}
.badge-interview{background:#0a2a1a;color:var(--good)}.badge-rejected{background:#2a0a0a;color:var(--err)}
.badge-discovered{background:#1a1a2a;color:#8b949e}
.stars{color:var(--warn)}
button,.btn{background:var(--accent);color:#fff;border:0;padding:8px 20px;border-radius:6px;cursor:pointer;font-size:13px;font-weight:600}
button:hover{opacity:.85}button:disabled{opacity:.4;cursor:not-allowed}
.btn-sm{background:var(--border);padding:4px 12px;font-size:12px}.btn-sm:hover{background:#484f58}
textarea,input[type=text]{width:100%;background:var(--bg);color:var(--fg);border:1px solid var(--border);border-radius:6px;padding:8px;font:13px system-ui;resize:vertical}
textarea:focus,input[type=text]:focus{outline:none;border-color:var(--accent)}
label{display:block;font-size:12px;color:#8b949e;margin-bottom:4px;margin-top:8px}
.row{display:flex;gap:12px;align-items:center;margin-top:12px;flex-wrap:wrap}
.hidden{display:none}
.filters{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:6px}
.filters button{padding:4px 14px;font-size:12px;background:var(--card);border:1px solid var(--border);color:var(--fg);border-radius:14px}
.filters button.active{background:var(--accent);border-color:var(--accent);color:#fff}
.toolbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:12px}
#toast{position:fixed;top:16px;right:16px;background:var(--good);color:#000;padding:10px 20px;border-radius:6px;font-weight:600;z-index:99;transition:opacity .3s}
.msg-line{padding:2px 0;font-size:12px}.msg-line .from{font-weight:600;margin-right:6px}
.msg-line .from.me{color:var(--accent)}.msg-line .from.hr{color:var(--good)}
th.sort-asc::after{content:' ↑'}th.sort-desc::after{content:' ↓'}
</style></head>
<body>
<h1>🤖 JobBot Agent</h1>
<p class=sub>开源通用求职技能包 · 本地运行 · 数据不上传</p>
<div id=toast style=opacity:0></div>

<section id=stats-section><h3>📊 投递总览</h3>
<div class=grid4 id=stats-grid></div></section>

<section id=config-section>
  <h3 id=config-title>🚀 第一步：填写求职信息</h3>
  <div id=upload-area style="border:2px dashed var(--border);border-radius:8px;padding:18px;text-align:center;cursor:pointer;margin-bottom:14px" onclick="document.getElementById('resume-file').click()">
    <input type=file id=resume-file accept=".pdf,.doc,.docx,.txt" style=display:none onchange="uploadResume(this)">
    📎 上传简历 (PDF/Word/TXT) <span id=resume-name style=color:var(--good)></span>
  </div>
  <label>意向描述（城市、学历、专业、目标岗位、技能…）</label>
  <textarea id=cfg-intent rows=4 placeholder="例：大专，电气自动化，2027毕业，找南京PLC调试或自动化实习，学过CAD和西门子PLC，有电工证，期望薪资3000-5000"></textarea>
  <div class=row>
    <button onclick=saveConfig()>💾 保存配置</button>
    <span style=font-size:12px;color:var(--good) id=cfg-saved></span>
  </div>
</section>

<section id=table-section>
  <h3>📋 投递记录 <span style=font-size:12px;color:#8b949e id=record-count></span></h3>
  <div class=toolbar>
    <div class=filters id=platform-filters></div>
    <div class=filters id=status-filters></div>
    <div style="flex:1"></div>
    <button class=btn-sm onclick=toggleSort() id=sort-btn style=background:var(--card);color:var(--fg) title=排序>⏱ 时间 ↓</button>
    <button class=btn-sm onclick=exportCSV() style=background:var(--card);color:var(--fg)>📥 CSV</button>
  </div>
  <div style=overflow-x:auto><table><thead><tr>
    <th data-sort=company>公司</th><th data-sort=position>岗位</th><th data-sort=platform>平台</th><th data-sort=score>匹配</th><th data-sort=status>状态</th><th data-sort=applied_at>时间</th>
  </tr></thead><tbody id=table-body></tbody></table></div>
  <p id=empty-msg style=text-align:center;color:#8b949e;padding:40px;display:none>暂无记录。加载技能包后说「帮我找工作」开始。</p>
</section>

<script>
let data={applications:[],stats:{}};
let config={};
let platformFilter='all',statusFilter='all';
let sortKey='applied_at',sortDir='desc';
let expanded=null;

async function loadAll(){await Promise.all([loadData(),loadConfig()]);render();}
async function loadData(){
  const r=await fetch('/api/data');data=await r.json();
}
async function loadConfig(){
  try{const r=await fetch('/api/config');config=await r.json()}catch(e){}
  document.getElementById('cfg-intent').value=config.intent||'';
  if(!config.intent){
    document.getElementById('stats-section').style.display='none';
    document.getElementById('table-section').style.display='none';
  }
}
async function uploadResume(input){
  if(!input.files[0])return;
  const fd=new FormData();fd.append('file',input.files[0]);
  const r=await fetch('/api/upload',{method:'POST',body:fd});
  const d=await r.json();
  document.getElementById('resume-name').textContent=' ✅ '+d._filename;
  document.getElementById('upload-area').style.borderColor='var(--good)';
  let parsed=[];
  if(d.name)parsed.push('姓名:'+d.name);
  if(d.education)parsed.push('学历:'+d.education);
  if(d.major)parsed.push('专业:'+d.major);
  if(d.phone)parsed.push('电话:'+d.phone);
  if(d.skills&&d.skills.length)parsed.push('技能:'+d.skills.join('、'));
  if(parsed.length){
    document.getElementById('cfg-intent').value=parsed.join('，')+'，';
    toast('✅ 已解析 '+parsed.length+' 项信息');
  }else toast('✅ 简历已保存');
}
async function saveConfig(){
  const cfg={intent:document.getElementById('cfg-intent').value};
  await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(cfg)});
  document.getElementById('config-section').style.display='none';
  document.getElementById('stats-section').style.display='block';
  document.getElementById('table-section').style.display='block';
  document.getElementById('cfg-saved').textContent='✅ 已保存';
  toast('✅ 配置已保存');
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
  rows.forEach(a=>csv.push([a.company||'',a.position||'',a.platform||'',a.salary||'',a.location||'',a.score||'',a.status||'',a.contact_person||'',(a.applied_at||'').slice(0,10),'"'+(a.jd_summary||'').replace(/"/g,'""')+'"'].join(',')));
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
    {n:s.total_applied||0,l:'总投递',c:'var(--accent)'},
    {n:s.hr_replied||0,l:'HR 回复',c:'var(--good)'},
    {n:s.interview_scheduled||0,l:'约面试',c:'var(--warn)'},
    {n:s.rejected||0,l:'已拒绝',c:'var(--err)'}
  ].map(x=>`<div class=stat-card><div class=num style=color:${x.c}>${x.n}</div><div class=lbl>${x.l}</div></div>`).join('');

  const platforms=[...new Set(apps.map(a=>a.platform).filter(Boolean))];
  document.getElementById('platform-filters').innerHTML=
    '<button onclick=setPlatformFilter("all") class='+(platformFilter==='all'?'active':'')+'>全部平台</button>'+
    platforms.map(p=>`<button onclick=setPlatformFilter("${p}") class=${platformFilter===p?'active':''}>${p}</button>`).join('');

  const statuses=[...new Set(apps.map(a=>a.status).filter(Boolean))];
  const statusLabel={applied:'已投递',hr_replied:'已回复',interview_scheduled:'面试',interviewing:'面试中',rejected:'已拒绝',discovered:'新发现'};
  document.getElementById('status-filters').innerHTML=
    '<button onclick=setStatusFilter("all") class='+(statusFilter==='all'?'active':'')+'>全部状态</button>'+
    statuses.map(s=>`<button onclick=setStatusFilter("${s}") class=${statusFilter===s?'active':''}>${statusLabel[s]||s}</button>`).join('');

  const rows=filteredRows();
  document.getElementById('record-count').textContent=`${rows.length} 条`;
  document.getElementById('empty-msg').style.display=rows.length?'none':'block';
  const badge={applied:'badge-applied',hr_replied:'badge-replied',interviewing:'badge-interview',interview_scheduled:'badge-interview',rejected:'badge-rejected',discovered:'badge-discovered'};
  document.getElementById('table-body').innerHTML=rows.map((a,i)=>{
    const s=a.status||'applied', stars='⭐'.repeat(a.score||0)||'—';
    return `<tr class=main-row onclick="toggleDetail(${i},this)" data-idx=${i}>
      <td>${a.company||'—'}</td><td>${a.url?`<a href="${a.url}" target=_blank onclick="event.stopPropagation()">${a.position||'—'}</a>`:(a.position||'—')}</td>
      <td>${a.platform||'—'}</td><td class=stars>${stars}</td>
      <td><span class="badge ${badge[s]||'badge-applied'}">${statusLabel[s]||s}</span></td>
      <td>${(a.applied_at||'').slice(0,10)}</td></tr>`+
      `<tr class="expand-row hidden" id=detail-${i}><td colspan=6>${detailHTML(a)}</td></tr>`;
  }).join('');
}

function detailHTML(a){
  let h='';
  if(a.jd_summary)h+=`<p><strong>📝 JD摘要：</strong>${esc(a.jd_summary)}</p>`;
  if(a.salary)h+=`<p><strong>💰 薪资：</strong>${esc(a.salary)}</p>`;
  if(a.location)h+=`<p><strong>📍 地点：</strong>${esc(a.location)}</p>`;
  if(a.contact_person)h+=`<p><strong>👤 联系人：</strong>${esc(a.contact_person)}${a.contact_phone?' · '+esc(a.contact_phone):''}</p>`;
  if(a.notes)h+=`<p><strong>📌 备注：</strong>${esc(a.notes)}</p>`;
  if(a.messages&&a.messages.length){
    h+='<p><strong>💬 对话：</strong></p>';
    a.messages.forEach(m=>h+=`<div class=msg-line><span class="from ${m.from}">[${m.from==='me'?'我':'HR'}]</span>${esc(m.content)} <span style=color:#8b949e;font-size:11px>${(m.time||'').slice(0,16)}</span></div>`);
  }
  return h||'<span style=color:#8b949e>暂无详细信息</span>';
}

function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}

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
  setTimeout(()=>t.style.opacity='0',2000);
}
loadAll();
setInterval(loadData,30000);
</script></body></html>"""

RESUME_DIR = ROOT / "data" / "resume"
os.makedirs(RESUME_DIR, exist_ok=True)

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        if self.path == '/':                         self._html(HTML)
        elif self.path == '/api/data':               self._json(self._read_data())
        elif self.path == '/api/config':             self._json(self._read_config())
        else:                                         self.send_error(404)

    def do_POST(self):
        if self.path == '/api/upload':
            self._handle_upload()
        elif self.path == '/api/config':
            length = int(self.headers.get('Content-Length', 0))
            cfg = json.loads(self.rfile.read(length))
            self._write_config(cfg)
            self._json({"ok": True})
        else:
            self.send_error(404)

    def _handle_upload(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length)
        ct = self.headers.get('Content-Type', '')
        if 'multipart' in ct:
            boundary = ct.split('boundary=')[1].encode()
            for p in body.split(b'--' + boundary):
                if b'filename=' in p:
                    hdr, _, data = p.partition(b'\r\n\r\n')
                    fn = p.split(b'filename="')[1].split(b'"')[0].decode()
                    path = os.path.join(RESUME_DIR, fn)
                    with open(path, 'wb') as f:
                        f.write(data.rstrip(b'\r\n--'))
                    extracted = self._parse_resume(path)
                    extracted['_filename'] = fn
                    self._json(extracted)
                    return
        self._json({'_error': '上传失败'})

    def _parse_resume(self, path):
        import re
        result = {}
        try:
            text = open(path, encoding='utf-8', errors='ignore').read()[:5000]
        except:
            text = open(path, encoding='gbk', errors='ignore').read()[:5000]
        m = re.search(r'(?:姓名|名字)[:：\s]*([\u4e00-\u9fa5]{2,4})', text)
        if m: result['name'] = m.group(1)
        m = re.search(r'(?:学历|教育)[:：\s]*(大专|本科|硕士|博士|中专|高中)', text)
        if m: result['education'] = m.group(1)
        m = re.search(r'(?:专业)[:：\s]*([\u4e00-\u9fa5]{2,20})', text)
        if m: result['major'] = m.group(1)
        m = re.search(r'(?:城市|地点|期望城市)[:：\s]*(北京|上海|广州|深圳|杭州|南京|成都|武汉|苏州|重庆|西安|天津|长沙|郑州)', text)
        if m: result['cities'] = [m.group(1)]
        m = re.search(r'1[3-9]\d{9}', text)
        if m: result['phone'] = m.group(0)
        m = re.search(r'[\w.-]+@[\w.-]+', text)
        if m: result['email'] = m.group(0)
        known = ['PLC','plc','CAD','Python','Java','C++','SQL','Excel','电工','自动化','电气','嵌入式','单片机','Linux','ROS','SolidWorks','西门子','三菱','ABB','PCB','FPGA','MATLAB','Office','PS','PR','AE']
        found = [k for k in known if k.lower() in text.lower()]
        if found: result['skills'] = found[:8]
        return result

    def _read_data(self):
        try: return json.loads(DATA_FILE.read_text(encoding="utf-8", errors="ignore"))
        except: return {"applications": [], "stats": {}}

    def _read_config(self):
        try: return json.loads(CONFIG_FILE.read_text(encoding="utf-8", errors="ignore"))
        except:
            try: return json.loads(CONFIG_TEMPLATE.read_text(encoding="utf-8", errors="ignore"))
            except: return {}

    def _write_config(self, cfg):
        CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8", errors="ignore")

    def _html(self, h): self._respond(200, 'text/html', h)
    def _json(self, d): self._respond(200, 'application/json', json.dumps(d, ensure_ascii=False))
    def _respond(self, code, ct, body):
        self.send_response(code); self.send_header('Content-Type', f'{ct}; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*'); self.end_headers()
        self.wfile.write(body.encode('utf-8'))

if __name__ == '__main__':
    print(f'JobBot Dashboard → http://localhost:{PORT}', flush=True)
    http.server.HTTPServer(('127.0.0.1', PORT), Handler).serve_forever()
