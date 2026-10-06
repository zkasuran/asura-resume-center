"""Asura Resume Center — the dashboard (9router-style dark UI).

Grouped by project folder; each session row shows a CLI badge, title, time, and
a one-click copy of the exact resume command. Auto-refreshes from /api/sessions
so it stays in sync with the bridge.
"""

DASHBOARD_HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Asura Resume Center</title>
<style>
  :root{
    --bg:#0d1117; --panel:#161b22; --panel2:#1c2230; --border:#30363d;
    --fg:#e6edf3; --mut:#8b949e; --accent:#2f81f7; --green:#3fb950;
    --amber:#d29922; --red:#f85149; --grey:#6e7681; --chip:#21262d;
    --kiro:#a371f7; --claude:#f0883e;
  }
  *{box-sizing:border-box}
  body{margin:0;font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;background:var(--bg);color:var(--fg)}
  a{color:var(--accent)}
  .bar{position:sticky;top:0;z-index:20;background:linear-gradient(180deg,#161b22,#0d1117);border-bottom:1px solid var(--border);padding:12px 18px;display:flex;align-items:center;gap:16px;flex-wrap:wrap}
  .brand{font-weight:700;font-size:18px;letter-spacing:.3px}
  .brand span{color:var(--accent)}
  .tag{color:var(--mut);font-size:12px}
  .chips{display:flex;gap:8px;flex-wrap:wrap;margin-left:auto;align-items:center}
  .chip{background:var(--chip);border:1px solid var(--border);border-radius:20px;padding:4px 11px;font-size:12px;color:var(--mut)}
  .chip b{color:var(--fg)}
  .dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:5px;vertical-align:middle}
  .dot.k{background:var(--kiro)} .dot.c{background:var(--claude)}
  .wrap{padding:18px;max-width:1100px;margin:0 auto}
  .toolbar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:16px}
  input,select{background:var(--panel2);border:1px solid var(--border);color:var(--fg);border-radius:7px;padding:8px 10px;font:inherit}
  input:focus{outline:none;border-color:var(--accent)}
  .search{flex:1;min-width:220px}
  button{background:var(--chip);border:1px solid var(--border);color:var(--fg);border-radius:7px;padding:8px 12px;font:inherit;cursor:pointer}
  button:hover{border-color:var(--accent)}
  button.primary{background:var(--accent);border-color:var(--accent);color:#fff}
  .synced{font-size:11px;color:var(--mut)}
  .synced b{color:var(--green)}
  /* folder group */
  .group{background:var(--panel);border:1px solid var(--border);border-radius:11px;margin-bottom:14px;overflow:hidden}
  .ghead{display:flex;align-items:center;gap:10px;padding:11px 15px;background:var(--panel2);border-bottom:1px solid var(--border);cursor:pointer;user-select:none}
  .ghead .fname{font-weight:650;font-size:14px}
  .ghead .fpath{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;color:var(--mut);word-break:break-all}
  .ghead .gmeta{margin-left:auto;display:flex;gap:7px;align-items:center;flex-wrap:wrap}
  .caret{transition:transform .15s;color:var(--mut)}
  .group.collapsed .caret{transform:rotate(-90deg)}
  .group.collapsed .glist{display:none}
  .group.catchall{opacity:.72}
  .group.catchall .ghead{background:#141922}
  .group.catchall .fname{color:var(--mut);font-weight:600}
  .glist{padding:4px 0}
  /* session row */
  .row{display:flex;align-items:center;gap:12px;padding:9px 15px;border-bottom:1px solid #22272f}
  .row:last-child{border-bottom:none}
  .row:hover{background:#1a2130}
  .badge{display:inline-flex;align-items:center;gap:5px;padding:2px 9px;border-radius:20px;font-size:11px;font-weight:650;border:1px solid;white-space:nowrap;min-width:76px;justify-content:center}
  .b-kiro{color:var(--kiro);border-color:var(--kiro);background:rgba(163,113,247,.12)}
  .b-claude{color:var(--claude);border-color:var(--claude);background:rgba(240,136,62,.12)}
  .rtitle{flex:1;min-width:0}
  .rtitle .t{font-size:13.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .rtitle .sub{font-size:11px;color:var(--mut);font-family:ui-monospace,monospace;display:flex;gap:6px;align-items:center;min-width:0;flex-wrap:wrap}
  .rtitle .sub .wchip{color:var(--green);border:1px solid rgba(63,185,80,.4);background:rgba(63,185,80,.1);border-radius:5px;padding:1px 7px;white-space:nowrap;max-width:260px;overflow:hidden;text-overflow:ellipsis}
  .rtitle .sub .wchip.lead{border-color:var(--green);background:rgba(63,185,80,.18)}
  .rtitle .sub .rfolder{color:var(--accent);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:55%}
  .rtitle .sub .rlaunch{color:var(--grey);white-space:nowrap;opacity:.7}
  .rtitle .sub .sid{color:var(--grey);white-space:nowrap;opacity:.55}
  .rtime{font-size:11px;color:var(--mut);white-space:nowrap}
  .cmd{display:flex;align-items:center;gap:8px;background:var(--bg);border:1px solid var(--border);border-radius:7px;padding:5px 8px;max-width:430px;min-width:0}
  .cmd code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11.5px;color:#c9d1d9;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1}
  .copy{padding:3px 9px;font-size:11px;border-radius:6px;flex-shrink:0}
  .copy.ok{background:var(--green);border-color:var(--green);color:#04210c}
  .empty{text-align:center;color:var(--mut);margin-top:40px}
  #toast{position:fixed;bottom:18px;left:50%;transform:translateX(-50%);background:#2d333b;border:1px solid var(--border);border-radius:8px;padding:10px 16px;z-index:100;display:none;max-width:90%}
  #toast.ok{border-color:var(--green)}
  /* free-memory modal */
  .modal{position:fixed;inset:0;display:none;align-items:center;justify-content:center;background:rgba(0,0,0,.6);z-index:60}
  .modal.on{display:flex}
  .card{background:var(--panel);border:1px solid var(--border);border-radius:12px;width:min(760px,96%);max-height:90vh;display:flex;flex-direction:column;padding:18px}
  .card h3{margin:0 0 4px}
  .rhead{display:flex;align-items:center;justify-content:space-between}
  button.sm{padding:4px 8px;font-size:12px}
  button.danger{border-color:var(--red);color:var(--red)}
  button.danger:not(:disabled):hover{background:var(--red);color:#210606}
  button:disabled{opacity:.45;cursor:not-allowed}
  .rtabs{display:flex;gap:8px;margin:12px 0 10px}
  .rtab{background:var(--chip);border:1px solid var(--border);border-radius:7px;padding:7px 12px;font-size:13px}
  .rtab.active{border-color:var(--accent);color:var(--accent)}
  .rtab span{color:var(--mut);font-size:11px}
  .rtools{display:flex;gap:12px;align-items:center;margin-bottom:8px}
  .sel{display:flex;gap:6px;align-items:center;white-space:nowrap}
  .rlist{flex:1;overflow:auto;border:1px solid var(--border);border-radius:9px;background:var(--bg)}
  .ritem{display:flex;align-items:center;gap:10px;padding:8px 12px;border-bottom:1px solid #22272f}
  .ritem:last-child{border-bottom:none}
  .ritem:hover{background:#1a2130}
  .ritem input{width:16px;height:16px;flex-shrink:0}
  .ritem .meta{flex:1;min-width:0}
  .ritem .ml{font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .ritem .md{font-size:11px;color:var(--mut);font-family:ui-monospace,monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .ritem .sz{font-size:12px;color:var(--amber);white-space:nowrap;font-variant-numeric:tabular-nums}
  .ritem .age{font-size:11px;color:var(--mut);white-space:nowrap;min-width:42px;text-align:right;font-variant-numeric:tabular-nums}
  .ritem .wfb{font-size:11px;color:var(--green);border:1px solid rgba(63,185,80,.4);background:rgba(63,185,80,.1);border-radius:5px;padding:1px 6px;white-space:nowrap;cursor:help}
  .ritem .cli{font-size:10px;padding:1px 7px;border-radius:20px;border:1px solid;flex-shrink:0}
  .ritem .cli.k{color:var(--kiro);border-color:var(--kiro)} .ritem .cli.c{color:var(--claude);border-color:var(--claude)}
  .rfoot{display:flex;align-items:center;justify-content:space-between;margin-top:12px}
  .selinfo{font-size:13px;color:var(--fg)}.selinfo b{color:var(--amber)}
  @media (max-width:760px){ .ritem .md{display:none} }
  @media (max-width:760px){ .cmd{max-width:none;flex-basis:100%} .row{flex-wrap:wrap} }
</style>
</head>
<body>
<div class="bar">
  <div class="brand">Asura <span>Resume</span> Center</div>
  <div class="tag">resume any CLI session — grouped by project folder</div>
  <div class="chips" id="chips"></div>
</div>

<div class="wrap">
  <div class="toolbar">
    <input class="search" id="search" placeholder="filter by folder / title / command / CLI…"/>
    <select id="cliFilter">
      <option value="">all CLIs</option>
      <option value="kiro-cli">kiro-cli only</option>
      <option value="claude">claude only</option>
    </select>
    <button id="btnExpand">Expand all</button>
    <button id="btnReap" style="border-color:var(--red);color:var(--red)">🗑 Free memory</button>
    <button id="btnSync" class="primary">↻ Sync now</button>
  </div>
  <div class="synced" id="synced"></div>
  <div id="groups"></div>
  <p class="empty" id="empty" style="display:none">no sessions match.</p>
</div>

<!-- Free-memory modal -->
<div class="modal" id="mReap"><div class="card">
  <div class="rhead">
    <h3>🗑 Free memory</h3>
    <button class="sm" id="reapClose">✕</button>
  </div>
  <p class="muted">Select artifacts to delete. This <b style="color:var(--red)">permanently removes</b> files from disk and <b>cannot be undone</b>. Sessions bundle all their files (kiro-cli: json + jsonl + history + lock + tasks).</p>
  <div class="rtabs">
    <button class="rtab active" data-cat="sessions">Sessions <span id="tbSessions"></span></button>
    <button class="rtab" data-cat="memory">Memory <span id="tbMemory"></span></button>
    <button class="rtab" data-cat="projects">Projects <span id="tbProjects"></span></button>
  </div>
  <div class="rtools">
    <input class="search" id="reapSearch" placeholder="filter…" style="flex:1;min-width:140px"/>
    <select id="reapAge" title="only show sessions not worked on for at least…">
      <option value="0">any age</option>
      <option value="7">unworked ≥ 7 days</option>
      <option value="14">unworked ≥ 14 days</option>
      <option value="30">unworked ≥ 30 days</option>
      <option value="60">unworked ≥ 60 days</option>
      <option value="90">unworked ≥ 90 days</option>
    </select>
    <select id="reapSort" title="sort order">
      <option value="age">oldest first</option>
      <option value="size">largest first</option>
      <option value="recent">newest first</option>
    </select>
    <label class="muted sel"><input type="checkbox" id="reapAll"/> select all shown</label>
  </div>
  <div class="rlist" id="reapList"></div>
  <div class="rfoot">
    <div class="selinfo" id="reapSel">0 selected · 0 B</div>
    <div style="display:flex;gap:12px;align-items:center">
      <label class="muted sel" id="wfWrap" title="also delete the real project folders these sessions worked on"><input type="checkbox" id="reapWF"/> also delete working folders</label>
      <button id="reapCancel">Cancel</button>
      <button class="danger" id="reapDelete" disabled>Delete selected</button>
    </div>
  </div>
</div></div>

<!-- confirm -->
<div class="modal" id="mConfirm"><div class="card" style="width:min(460px,94%)">
  <h3 style="color:var(--red)">Confirm deletion</h3>
  <p id="confirmMsg" class="muted"></p>
  <p class="muted">Type <b>DELETE</b> to confirm:</p>
  <input id="confirmText" style="width:100%" placeholder="DELETE"/>
  <div class="rfoot" style="margin-top:14px">
    <span></span>
    <div style="display:flex;gap:10px">
      <button id="confirmCancel">Cancel</button>
      <button class="danger" id="confirmGo" disabled>Permanently delete</button>
    </div>
  </div>
</div></div>

<div id="toast"></div>

<script>
const $=id=>document.getElementById(id);
let STATE={snap:null, collapsed:{}, q:"", cli:""};

function toast(msg,ok){const t=$("toast");t.textContent=msg;t.className=ok?"ok":"";t.style.display="block";setTimeout(()=>t.style.display="none",1600);}
function esc(s){return (s||"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));}
function ago(ts){
  if(!ts) return "";
  const d=Math.max(0,(Date.now()/1000)-ts);
  if(d<60) return "just now";
  if(d<3600) return Math.floor(d/60)+"m ago";
  if(d<86400) return Math.floor(d/3600)+"h ago";
  if(d<2592000) return Math.floor(d/86400)+"d ago";
  return Math.floor(d/2592000)+"mo ago";
}

async function api(path,opts){
  const r=await fetch(path,opts);
  if(!r.ok) throw new Error("HTTP "+r.status);
  return r.json();
}

function matches(s, folder){
  const q=STATE.q.toLowerCase();
  if(STATE.cli && s.cli!==STATE.cli) return false;
  if(!q) return true;
  const wf=(s.worked_folders||[]).join(" ");
  return (s.title+" "+s.resume_command+" "+s.cli+" "+folder+" "+wf+" "+(s.launch_cwd||"")).toLowerCase().includes(q);
}

async function copyCmd(cmd, btn){
  try{
    await navigator.clipboard.writeText(cmd);
  }catch(e){
    const ta=document.createElement("textarea");ta.value=cmd;document.body.appendChild(ta);
    ta.select();try{document.execCommand("copy");}catch(_){}document.body.removeChild(ta);
  }
  if(btn){const old=btn.textContent;btn.textContent="✓ copied";btn.classList.add("ok");
    setTimeout(()=>{btn.textContent=old;btn.classList.remove("ok");},1200);}
  toast("resume command copied",true);
}

function render(){
  const snap=STATE.snap; if(!snap){return;}
  const st=snap.stats||{};
  $("chips").innerHTML=
    `<span class="chip"><b>${st.total||0}</b> sessions</span>`+
    `<span class="chip"><span class="dot k"></span>kiro-cli <b>${st.kiro||0}</b></span>`+
    `<span class="chip"><span class="dot c"></span>claude <b>${st.claude||0}</b></span>`+
    `<span class="chip"><b>${st.projects!=null?st.projects:(st.folders||0)}</b> projects</span>`;
  const synced = snap.synced_ts||snap.generated_ts;
  $("synced").innerHTML = synced ? `store synced <b>${ago(synced)}</b> · auto-refresh on` : "";

  const groups=snap.groups||[];
  const out=[];
  let shownSessions=0;
  for(const g of groups){
    const visible=g.sessions.filter(s=>matches(s,g.folder));
    if(!visible.length) continue;
    shownSessions+=visible.length;
    // catch-all buckets (home/scratch) collapse by default unless searching or toggled
    let collapsed;
    if(g.folder in STATE.collapsed) collapsed=STATE.collapsed[g.folder];
    else collapsed = g.catchall && !STATE.q;
    const col=collapsed?"collapsed":"";
    const rows=visible.map(s=>{
      const bcl=s.cli==="kiro-cli"?"b-kiro":"b-claude";
      const label=s.cli==="kiro-cli"?"kiro-cli":"claude";
      const wf=(s.worked_folders&&s.worked_folders.length)?s.worked_folders:[];
      let folderHtml;
      if(wf.length){
        // one chip per worked-on project (multi-project sessions show all)
        folderHtml = wf.map((f,i)=>{
          const nm=f.split("/").filter(Boolean).slice(-2).join("/");
          return `<span class="wchip${i===0?' lead':''}" title="worked on: ${esc(f)}">🛠 ${esc(nm)}</span>`;
        }).join("");
        if(s.launch_cwd) folderHtml += `<span class="rlaunch" title="CLI launched here">⇧ ${esc(s.launch_cwd)}</span>`;
      } else {
        const folder=s.folder||s.launch_cwd||"(unknown folder)";
        folderHtml = `<span class="rfolder" title="working folder: ${esc(folder)}">📁 ${esc(folder)}</span>`;
      }
      return `<div class="row">
        <span class="badge ${bcl}">${label}</span>
        <div class="rtitle">
          <div class="t">${esc(s.title)}</div>
          <div class="sub">
            ${folderHtml}
            <span class="sid" title="session id">${esc(s.session_id)}</span>
          </div>
        </div>
        <span class="rtime" title="${esc(s.updated_at)}">${ago(s.updated_ts)}</span>
        <div class="cmd">
          <code title="${esc(s.resume_command)}">${esc(s.resume_command)}</code>
          <button class="copy" data-cmd="${esc(s.resume_command)}">Copy</button>
        </div>
      </div>`;
    }).join("");
    out.push(`<div class="group ${col}${g.catchall?' catchall':''}" data-folder="${esc(g.folder)}">
      <div class="ghead" data-toggle="${esc(g.folder)}">
        <span class="caret">▾</span>
        <div>
          <div class="fname">${g.catchall?'🗂 ':'📁 '}${esc(g.name)}</div>
          <div class="fpath">${esc(g.folder)}</div>
        </div>
        <div class="gmeta">
          ${g.kiro?`<span class="chip"><span class="dot k"></span>${g.kiro}</span>`:""}
          ${g.claude?`<span class="chip"><span class="dot c"></span>${g.claude}</span>`:""}
          <span class="chip"><b>${visible.length}</b> shown</span>
          <span class="rtime">${ago(g.latest_ts)}</span>
        </div>
      </div>
      <div class="glist">${rows}</div>
    </div>`);
  }
  $("groups").innerHTML=out.join("");
  $("empty").style.display=shownSessions?"none":"block";

  document.querySelectorAll(".ghead").forEach(h=>h.addEventListener("click",e=>{
    if(e.target.closest("button")) return;
    const f=h.getAttribute("data-toggle");
    STATE.collapsed[f]=!STATE.collapsed[f];
    render();
  }));
  document.querySelectorAll(".copy").forEach(b=>b.addEventListener("click",e=>{
    e.stopPropagation(); copyCmd(b.getAttribute("data-cmd"), b);
  }));
}

async function load(force){
  try{
    STATE.snap = force ? await api("/api/sync",{method:"POST"}) : await api("/api/sessions");
    render();
  }catch(e){ toast("load failed: "+e.message); }
}

$("search").addEventListener("input",e=>{STATE.q=e.target.value;render();});
$("cliFilter").addEventListener("change",e=>{STATE.cli=e.target.value;render();});
$("btnSync").addEventListener("click",()=>{load(true).then(()=>toast("synced from disk",true));});
let allCollapsed=false;
$("btnExpand").addEventListener("click",()=>{
  allCollapsed=!allCollapsed;
  (STATE.snap?.groups||[]).forEach(g=>STATE.collapsed[g.folder]=allCollapsed);
  $("btnExpand").textContent=allCollapsed?"Expand all":"Collapse all";
  render();
});

load(false);
setInterval(()=>load(false), 5000); // stay synced

/* ----------------------- Free memory (reaper) ----------------------- */
let REAP={data:null, cat:"sessions", sel:new Set(), q:"", minAge:0, sort:"age", wf:false};

function humanBytes(n){
  let f=n; const u=["B","KB","MB","GB","TB"];
  for(let i=0;i<u.length;i++){ if(f<1024||i===u.length-1) return (i===0?f.toFixed(0):f.toFixed(1))+" "+u[i]; f/=1024; }
}
function ageLabel(d){
  if(d==null) return "";
  if(d<1) return "today";
  if(d<30) return Math.floor(d)+"d";
  if(d<365) return Math.floor(d/30)+"mo";
  return (d/365).toFixed(1)+"y";
}
function reapItems(){ return (REAP.data?.[REAP.cat])||[]; }
function reapVisible(){
  const q=REAP.q.toLowerCase();
  let items=reapItems().filter(a=>{
    if(REAP.cat==="sessions" && REAP.minAge>0 && (a.age_days||0) < REAP.minAge) return false;
    if(!q) return true;
    const wf=(a.worked_folders||[]).join(" ");
    return (a.label+" "+a.folder+" "+a.detail+" "+wf).toLowerCase().includes(q);
  });
  const s=REAP.sort;
  items=items.slice().sort((x,y)=>{
    if(s==="size") return (y.bytes||0)-(x.bytes||0);
    if(s==="recent") return (y.updated_ts||0)-(x.updated_ts||0);
    return (x.updated_ts||0)-(y.updated_ts||0); // age: oldest first
  });
  return items;
}
function reapUpdateFoot(){
  let bytes=0,n=0;
  for(const a of reapItems()) if(REAP.sel.has(a.id)){ bytes+=a.bytes; n++; }
  const wfNote = (REAP.wf && REAP.cat==="sessions") ? " <span style='color:var(--red)'>+ working folders</span>" : "";
  $("reapSel").innerHTML=`<b>${n}</b> selected · <b>${humanBytes(bytes)}</b>${wfNote}`;
  $("reapDelete").disabled = n===0;
  const vis=reapVisible();
  $("reapAll").checked = vis.length>0 && vis.every(a=>REAP.sel.has(a.id));
}
function reapRenderTabs(){
  const t=REAP.data?.totals||{};
  $("tbSessions").textContent = t.sessions?`(${t.sessions.count} · ${t.sessions.human})`:"";
  $("tbMemory").textContent   = t.memory?`(${t.memory.count} · ${t.memory.human})`:"";
  $("tbProjects").textContent = t.projects?`(${t.projects.count} · ${t.projects.human})`:"";
  document.querySelectorAll(".rtab").forEach(b=>b.classList.toggle("active",b.dataset.cat===REAP.cat));
  // age filter + working-folder option only make sense for sessions
  const isSess = REAP.cat==="sessions";
  $("reapAge").style.display = isSess?"":"none";
  $("wfWrap").style.display = isSess?"":"none";
}
function reapRenderList(){
  const vis=reapVisible();
  const isSess=REAP.cat==="sessions";
  $("reapList").innerHTML = vis.length? vis.map(a=>{
    const cli = a.cli==="kiro-cli"?`<span class="cli k">kiro</span>`:(a.cli==="claude"?`<span class="cli c">claude</span>`:"");
    const nwf=(a.worked_folders||[]).length;
    const age = isSess ? `<span class="age" title="last worked ${a.age_days}d ago">${ageLabel(a.age_days)}</span>` : "";
    const wfbadge = (isSess && nwf) ? `<span class="wfb" title="${esc((a.worked_folders||[]).join('\n'))}">📁${nwf}</span>` : "";
    const sub = isSess ? ((a.worked_folders&&a.worked_folders[0])||a.folder||a.detail) : (a.folder||a.detail);
    return `<label class="ritem">
      <input type="checkbox" data-id="${esc(a.id)}" ${REAP.sel.has(a.id)?"checked":""}/>
      ${cli}
      <div class="meta">
        <div class="ml">${esc(a.label)}</div>
        <div class="md">${esc(sub)}</div>
      </div>
      ${wfbadge}
      ${age}
      <span class="sz">${esc(a.human)}</span>
    </label>`;
  }).join("") : `<p class="empty" style="margin:24px">nothing matches this filter.</p>`;
  $("reapList").querySelectorAll("input[type=checkbox]").forEach(cb=>{
    cb.addEventListener("change",()=>{
      const id=cb.getAttribute("data-id");
      if(cb.checked) REAP.sel.add(id); else REAP.sel.delete(id);
      reapUpdateFoot();
    });
  });
  reapUpdateFoot();
}
async function openReap(){
  $("mReap").classList.add("on");
  $("reapList").innerHTML=`<p class="empty" style="margin:24px">scanning disk…</p>`;
  try{
    REAP.data=await api("/api/reap");
    REAP.sel=new Set(); REAP.q=""; $("reapSearch").value="";
    REAP.minAge=0; REAP.sort="age"; REAP.wf=false;
    $("reapAge").value="0"; $("reapSort").value="age"; $("reapWF").checked=false;
    reapRenderTabs(); reapRenderList();
  }catch(e){ toast("scan failed: "+e.message); }
}
function closeReap(){ $("mReap").classList.remove("on"); }

$("btnReap").addEventListener("click",openReap);
$("reapClose").addEventListener("click",closeReap);
$("reapCancel").addEventListener("click",closeReap);
document.querySelectorAll(".rtab").forEach(b=>b.addEventListener("click",()=>{
  REAP.cat=b.dataset.cat; reapRenderTabs(); reapRenderList();
}));
$("reapSearch").addEventListener("input",e=>{REAP.q=e.target.value;reapRenderList();});
$("reapAge").addEventListener("change",e=>{REAP.minAge=parseInt(e.target.value,10)||0;reapRenderList();});
$("reapSort").addEventListener("change",e=>{REAP.sort=e.target.value;reapRenderList();});
$("reapWF").addEventListener("change",e=>{REAP.wf=e.target.checked;reapUpdateFoot();});
$("reapAll").addEventListener("change",e=>{
  const vis=reapVisible();
  if(e.target.checked) vis.forEach(a=>REAP.sel.add(a.id));
  else vis.forEach(a=>REAP.sel.delete(a.id));
  reapRenderList();
});

/* two-step confirm */
$("reapDelete").addEventListener("click",()=>{
  const ids=[...REAP.sel]; if(!ids.length) return;
  let bytes=0; const wfolders=new Set();
  for(const a of reapItems()) if(REAP.sel.has(a.id)){
    bytes+=a.bytes;
    if(REAP.wf) (a.worked_folders||[]).forEach(f=>wfolders.add(f));
  }
  const wfOn = REAP.wf && REAP.cat==="sessions";
  let msg=`You are about to permanently delete <b>${ids.length}</b> item(s) `+
    `(<b style="color:var(--amber)">${humanBytes(bytes)}</b>) from the <b>${REAP.cat}</b> category.`;
  if(wfOn && wfolders.size){
    const list=[...wfolders].slice(0,8).map(f=>`<div class="mono" style="color:var(--red)">🗂 ${esc(f)}</div>`).join("");
    msg+=`<br><br><b style="color:var(--red)">PLUS the real project folders</b> these sessions worked on `+
      `(protected roots like ~/Downloads are skipped):<div style="margin-top:6px;max-height:140px;overflow:auto">${list}`+
      `${wfolders.size>8?`<div class="muted">…and ${wfolders.size-8} more</div>`:""}</div>`;
  }
  msg+=`<br>This <b>cannot be undone</b>.`;
  $("confirmMsg").innerHTML=msg;
  $("confirmText").value=""; $("confirmGo").disabled=true;
  $("mConfirm").dataset.wf = wfOn ? "1" : "0";
  $("mConfirm").classList.add("on"); $("confirmText").focus();
});
$("confirmText").addEventListener("input",e=>{ $("confirmGo").disabled = e.target.value.trim()!=="DELETE"; });
$("confirmCancel").addEventListener("click",()=>$("mConfirm").classList.remove("on"));
$("confirmGo").addEventListener("click",async()=>{
  const ids=[...REAP.sel];
  const wf = $("mConfirm").dataset.wf==="1";
  $("confirmGo").disabled=true; $("confirmGo").textContent="deleting…";
  try{
    const res=await api("/api/reap",{method:"POST",headers:{"content-type":"application/json"},
      body:JSON.stringify({ids,dry_run:false,include_worked_folders:wf})});
    $("mConfirm").classList.remove("on");
    const fd = res.folders_deleted ? ` · ${res.folders_deleted} folders` : "";
    toast(`freed ${res.freed_human} · deleted ${res.deleted}/${res.requested}${fd}`,true);
    await openReap();      // re-scan (sizes/counts refresh)
    await load(false);     // refresh the resume dashboard too
  }catch(e){ toast("delete failed: "+e.message); }
  finally{ $("confirmGo").textContent="Permanently delete"; }
});

</script>
</body>
</html>'''
