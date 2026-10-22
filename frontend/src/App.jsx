import {useCallback,useEffect,useState} from "react";
import "./app.css";
const sid=localStorage.getItem("sid")||(()=>{const v=(crypto.randomUUID?crypto.randomUUID():String(Math.random()).slice(2)+"abcdefgh");localStorage.setItem("sid",v);return v})();
async function api(path,{json,body,method}={}){
  const r=await fetch("/api"+path,{method:method||(json||body?"POST":"GET"),headers:{"X-Session":sid,...(json?{"Content-Type":"application/json"}:{})},body:json?JSON.stringify(json):body});
  const t=await r.json().catch(()=>({}));
  if(!r.ok){const d=t.detail;throw new Error(Array.isArray(d)?d.map(x=>x.msg||x).join(" "):d||`Request failed (${r.status})`)}
  return t}
const LAB={critical:"Critical",watch:"Watch",healthy:"Healthy",unscored:"Not scored"},CLS={critical:"r",watch:"a",healthy:"g",unscored:"b"},COL={critical:"var(--red)",watch:"var(--amb)",healthy:"var(--grn)",unscored:"var(--mute)"};
const Pill=({s,t})=><span className={"pill p-"+CLS[s]}>{t||LAB[s]}</span>;
const f2=x=>(+x).toFixed(2);
function useLoad(path){const [d,setD]=useState(null),[e,setE]=useState(null);
  const load=useCallback(()=>{api(path).then(x=>{setD(x);setE(null)}).catch(x=>setE(x.message))},[path]);
  useEffect(()=>{setD(null);load()},[load]);return [d,e,load]}
const Wait=({d,e,children})=>e?<div className="err" role="alert">{e}</div>:d===null?<p className="mute">Loading…</p>:children;
const Kpi=({l,v,s,na})=><div className="card kpi"><span>{l}</span><b className={na?"na":""}>{v}</b><small>{s}</small></div>;

function Chart({s}){const v=s.points.map(p=>p.v),hi=s.baseline+3*s.std,lo=Math.min(...v,s.baseline)-s.std,up=Math.max(...v,hi)+s.std,w=560,h=190,
  X=i=>34+i*(w-44)/Math.max(1,v.length-1),Y=y=>h-24-(y-lo)/(up-lo)*(h-40);
  return <svg viewBox={`0 0 ${w} ${h}`} width="100%" role="img" aria-label="Sensor history">
    <line x1="34" x2={w-10} y1={Y(s.baseline)} y2={Y(s.baseline)} stroke="var(--mute)" strokeDasharray="3 4"/>
    <line x1="34" x2={w-10} y1={Y(hi)} y2={Y(hi)} stroke="var(--red)" strokeDasharray="5 4"/>
    <text x={w-12} y={Y(hi)-4} textAnchor="end" fontSize="11" fill="var(--red)">Critical threshold (baseline + 3σ)</text>
    <text x={w-12} y={Y(s.baseline)-4} textAnchor="end" fontSize="11" fill="var(--mute)">Baseline mean</text>
    <polyline fill="none" stroke="var(--acc)" strokeWidth="2.2" points={v.map((y,i)=>X(i)+","+Y(y)).join(" ")}/>
    <text x="34" y={h-6} fontSize="11" fill="var(--mute)">{s.points[0].t}</text><text x={w-10} y={h-6} textAnchor="end" fontSize="11" fill="var(--mute)">{s.points.at(-1).t}</text></svg>}

function Dataset({state,done}){
  const [stage,setStage]=useState("upload"),[p,setP]=useState(null),[m,setM]=useState(null),[q,setQ]=useState(null),[err,setErr]=useState(null),[busy,setBusy]=useState(false);
  const wrap=async fn=>{setBusy(true);setErr(null);try{await fn()}catch(e){setErr(e.message)}finally{setBusy(false)}};
  const pick=f=>f&&wrap(async()=>{const fd=new FormData();fd.append("file",f);const r=await api("/datasets",{body:fd});setP(r);setM(r.mapping);setQ(null);setStage("map")});
  const check=()=>wrap(async()=>{setQ(await api("/datasets/check",{json:m}));setStage("check")});
  const run=()=>wrap(async()=>{await api("/datasets/process",{json:m});setStage("upload");await done("Overview")});
  const clear=()=>wrap(async()=>{await api("/dataset",{method:"DELETE"});await done("Dataset")});
  const Err=()=>err?<div className="err" role="alert">{err}</div>:null;
  const Steps=({n})=><div className="steps">{["1 Upload","2 Match columns","3 Check data"].map((s,i)=><span key={s} className={i===n?"on":""}>{s}</span>)}</div>;
  const File=({label,pri})=><><input id="f" type="file" accept=".csv,.xlsx,.xls" hidden onChange={e=>{pick(e.target.files[0]);e.target.value=""}}/><button className={"btn "+(pri?"pri":"")} disabled={busy} onClick={()=>document.getElementById("f").click()}>{label}</button></>;
  if(stage==="map"&&p){const set=(k,v)=>setM({...m,[k]:v===""?null:v});
    return <><h1>Match columns</h1><p className="lead">{p.name} · {p.rows} rows. Correct anything that looks wrong.</p><Steps n={1}/><Err/>
    <div className="card"><div className="row">{[["timestamp","Timestamp",0],["id","Equipment ID",0],["failure","Failure flag (optional)",1]].map(([k,l,o])=><div key={k}><label htmlFor={"m"+k}>{l}</label><select id={"m"+k} value={m[k]||""} onChange={e=>set(k,e.target.value)}>{o||!m[k]?<option value="">None</option>:null}{p.columns.map(c=><option key={c}>{c}</option>)}</select></div>)}</div>
    <label>Sensor columns</label><div>{p.columns.map(c=><label key={c} className="chk"><input type="checkbox" checked={m.sensors.includes(c)} onChange={e=>setM({...m,sensors:e.target.checked?[...m.sensors,c]:m.sensors.filter(x=>x!==c)})}/>{c}</label>)}</div>
    <h2>Preview (first 5 rows)</h2><div className="scroll"><table><thead><tr>{p.columns.map(c=><th key={c}>{c}</th>)}</tr></thead><tbody>{p.preview.map((r,i)=><tr key={i}>{p.columns.map(c=><td key={c}>{String(r[c]??"")}</td>)}</tr>)}</tbody></table></div>
    <p><button className="btn pri" disabled={busy} onClick={check}>Check data</button> <button className="btn" onClick={()=>setStage("upload")}>Cancel</button></p></div></>}
  if(stage==="check"&&q)return <><h1>Check data</h1><p className="lead">Review before anything is processed</p><Steps n={2}/><Err/>
    <div className="grid g5"><Kpi l="Rows" v={q.rows} s="Total data rows"/><Kpi l="Missing values" v={q.missing_pct+"%"} s={q.missing+" empty cells. Skipped, not invented"}/><Kpi l="Duplicate rows" v={q.duplicates} s="Removed before analysis"/><Kpi l="Invalid timestamps" v={q.bad_timestamps} s="Excluded from analysis"/><Kpi l="Extreme outliers" v={q.outliers} s="Over 4σ from the column mean. Kept"/></div>
    <p><button className="btn pri" disabled={busy} onClick={run}>{busy?"Processing…":"Process and unlock"}</button> <button className="btn" onClick={()=>setStage("map")}>Back</button></p></>;
  if(state.unlocked){const d=state.dataset;return <><h1>Dataset</h1><p className="lead">The active dataset drives every page</p><Err/><div className="card"><h2>{d.name}</h2>
    <p>{d.quality.rows} rows · {d.machines} machines · {d.mapping.sensors.length} sensors · failure column: {d.mapping.failure||"none"}</p>
    <p className="mute">Removed before analysis: {d.quality.duplicates} duplicate row(s) and {d.quality.bad_timestamps} row(s) with unreadable timestamps. {d.quality.missing} empty value(s) skipped.</p>
    <File label="Replace dataset"/> <button className="btn" disabled={busy} onClick={clear}>Clear dataset</button></div></>}
  return <><h1>Upload your equipment data</h1><p className="lead">Everything stays locked until your file passes validation.</p><Steps n={0}/><Err/>
    <div className="drop"><b>Upload a CSV or Excel file</b><p className="mute">One row per reading. Needed: a timestamp, an equipment ID and at least one numeric sensor column. Optional: a failure flag (0/1).</p><File label={busy?"Reading…":"Choose file"} pri/></div></>}

function Overview(){const [o,e]=useLoad("/overview"),[eq]=useLoad("/equipment"),[q,setQ]=useState(""),[so,setSo]=useState("risk");
  return <Wait d={o&&eq} e={e}>{o&&eq&&(()=>{const k=o.kpis,h=k.health;let L=eq.filter(a=>a.id.toLowerCase().includes(q.toLowerCase()));if(so==="id")L=[...L].sort((a,b)=>a.id.localeCompare(b.id));
    return <><h1>Overview</h1><p className="lead">{o.dataset}</p><div className="grid g5">
    <Kpi l="Equipment monitored" v={k.equipment.value} s={k.equipment.definition}/>
    <Kpi l="Health (critical / watch / healthy)" v={<><span style={{color:COL.critical}}>{h.critical}</span> / <span style={{color:COL.watch}}>{h.watch}</span> / <span style={{color:COL.healthy}}>{h.healthy}</span></>} s={h.definition}/>
    <Kpi l="Observed failures" v={k.failures.available?k.failures.value:"Insufficient data"} s={k.failures.available?`${k.failures.rate_pct}% of records. ${k.failures.definition}`:k.failures.reason} na={!k.failures.available}/>
    <Kpi l="Open work orders" v={k.open_work_orders.value} s={k.open_work_orders.definition}/>
    <Kpi l="Remaining useful life" v="Insufficient data" s={k.remaining_useful_life.reason} na/></div>
    <div className="card scroll"><h2>Equipment</h2><div className="row"><div><label htmlFor="q">Search equipment</label><input id="q" type="search" value={q} onChange={e=>setQ(e.target.value)}/></div><div><label htmlFor="so">Sort by</label><select id="so" value={so} onChange={e=>setSo(e.target.value)}><option value="risk">Highest risk</option><option value="id">Name</option></select></div></div>
    <table><thead><tr><th>Equipment</th><th>Health</th><th>Status</th><th>Main driver</th><th>Records</th></tr></thead><tbody>{L.length?L.map(a=><tr key={a.id}><td>{a.id}</td><td>{a.health==null?"–":<div className="bar"><i style={{width:a.health+"%",background:COL[a.status]}}/></div>}</td><td><Pill s={a.status}/></td><td>{a.worst&&a.max_z>=1.5?`${a.worst} (${a.sensors[a.worst].z>0?"+":""}${f2(a.sensors[a.worst].z)} σ)`:"Nothing unusual"}</td><td>{a.records}</td></tr>):<tr><td colSpan="5" className="mute">No equipment matches “{q}”.</td></tr>}</tbody></table></div></>})()}</Wait>}

function Equipment(){const [list,e]=useLoad("/equipment"),[id,setId]=useState(null),[sn,setSn]=useState(null);
  const sel=id||list?.[0]?.id,[a,e2]=useLoad(sel?"/equipment/"+encodeURIComponent(sel):"/state");
  return <Wait d={list} e={e}>{list&&<><h1>Equipment Monitor</h1><p className="lead">Pick a machine to see the evidence behind its status</p>
    <div className="row"><div style={{maxWidth:260}}><label htmlFor="as">Equipment</label><select id="as" value={sel} onChange={e=>{setId(e.target.value);setSn(null)}}>{list.map(x=><option key={x.id}>{x.id}</option>)}</select></div></div>
    <Wait d={a&&a.sensors?a:null} e={e2}>{a&&a.sensors&&(()=>{const ns=Object.keys(a.sensors),n=ns.includes(sn)?sn:a.worst||ns[0];
    return !ns.length?<div className="card">Not enough readings to score this machine (at least 10 per sensor are needed).</div>:<div className="grid g2"><div className="card"><h2>{n}</h2><p><Pill s={a.status}/> {a.health}% health</p><p>{ns.map(k=><button key={k} className={"btn sm "+(k===n?"pri":"")} style={{marginRight:6}} onClick={()=>setSn(k)}>{k}</button>)}</p><Chart s={a.sensors[n]}/></div>
    <div className="card scroll"><h2>Evidence</h2><table><thead><tr><th>Sensor</th><th>Recent</th><th>Baseline</th><th>Shift</th></tr></thead><tbody>{ns.map(k=>{const x=a.sensors[k];return <tr key={k}><td>{k}</td><td>{f2(x.recent)}</td><td>{f2(x.baseline)}</td><td><Pill s={x.status} t={(x.z>0?"+":"")+f2(x.z)+" σ"}/></td></tr>})}</tbody></table>
    <p className="mute">Recent = mean of the last 3 readings. Baseline = mean of the first 60% of this machine's history. This is a statistical rule, not a trained model, and it does not predict a failure date.</p></div></div>})()}</Wait></>}</Wait>}

function Alerts(){const [f,setF]=useState(""),[L,e,reload]=useLoad("/alerts"+(f?"?status="+f:"")),[err,setErr]=useState(null);
  const set=async(key,status)=>{try{await api("/alerts/status",{method:"PATCH",json:{key,status}});reload()}catch(x){setErr(x.message)}};
  return <><h1>Alerts</h1><p className="lead">Raised by comparing the latest readings in the file with each machine's baseline. These are historical records, not live events.</p>
  <div className="row"><div style={{maxWidth:200}}><label htmlFor="af">Status</label><select id="af" value={f} onChange={x=>setF(x.target.value)}><option value="">All</option>{["Open","Acknowledged","Resolved"].map(o=><option key={o}>{o}</option>)}</select></div></div>
  {err&&<div className="err" role="alert">{err}</div>}<Wait d={L} e={e}>{L&&<div className="card scroll">{L.length?<table><thead><tr><th>Severity</th><th>Equipment</th><th>Why it triggered</th><th>Recommended action</th><th>Data time</th><th>Status</th><th></th></tr></thead><tbody>{L.map(a=><tr key={a.key}><td><Pill s={a.severity}/></td><td>{a.asset}</td><td>{a.why}</td><td>{a.action}</td><td>{a.data_timestamp}</td><td>{a.status}</td><td>{a.status==="Open"&&<button className="btn sm" onClick={()=>set(a.key,"Acknowledged")}>Acknowledge</button>} {a.status!=="Resolved"&&<button className="btn sm" onClick={()=>set(a.key,"Resolved")}>Resolve</button>}</td></tr>)}</tbody></table>:<p className="mute">No alerts match this filter.</p>}</div>}</Wait></>}

function Maintenance(){const [R,e]=useLoad("/maintenance/recommendations"),[W,e2,reload]=useLoad("/workorders"),[err,setErr]=useState(null);
  const call=async(path,opt)=>{try{await api(path,opt);reload()}catch(x){setErr(x.message)}};
  return <><h1>Maintenance</h1><p className="lead">Generated recommendations are suggestions. Work orders are records created here.</p>{err&&<div className="err" role="alert">{err}</div>}
  <Wait d={R} e={e}>{R&&<div className="card scroll"><h2>Recommended inspections (generated, ranked by risk)</h2>{R.length?<table><thead><tr><th>Priority</th><th>Equipment</th><th>Action</th><th>Evidence</th><th></th></tr></thead><tbody>{R.map(r=><tr key={r.asset}><td>{r.priority}</td><td>{r.asset} <Pill s={r.status}/></td><td>{r.action}</td><td>{r.evidence}</td><td><button className="btn sm" onClick={()=>call("/workorders",{json:{title:`Inspect ${r.asset}: ${r.sensor}`,asset:r.asset}})}>Create work order</button></td></tr>)}</tbody></table>:<p className="mute">Nothing needs attention in this dataset.</p>}</div>}</Wait>
  <Wait d={W} e={e2}>{W&&<div className="card scroll"><h2>Work orders (records)</h2>{W.length?<table><thead><tr><th>Job</th><th>Assigned to</th><th>Due</th><th>Status</th></tr></thead><tbody>{W.map(w=><tr key={w.id}><td>{w.title}</td><td><input type="text" aria-label="Assignee" defaultValue={w.assignee} onBlur={x=>x.target.value!==w.assignee&&call("/workorders/"+w.id,{method:"PATCH",json:{assignee:x.target.value}})}/></td><td><input type="date" aria-label="Due date" defaultValue={w.due} onChange={x=>call("/workorders/"+w.id,{method:"PATCH",json:{due:x.target.value}})}/></td><td><select aria-label="Status" value={w.status} onChange={x=>call("/workorders/"+w.id,{method:"PATCH",json:{status:x.target.value}})}>{["Open","In progress","Done"].map(o=><option key={o}>{o}</option>)}</select></td></tr>)}</tbody></table>:<p className="mute">No work orders yet.</p>}<p className="mute">Cost and downtime savings are not shown. This dataset has no cost or production inputs.</p></div>}</Wait></>}

function Model(){const [m,e,reload]=useLoad("/model"),[err,setErr]=useState(null),[busy,setBusy]=useState(false);
  const train=async()=>{setBusy(true);setErr(null);try{await api("/model/train",{method:"POST"});reload()}catch(x){setErr(x.message)}finally{setBusy(false)}};
  return <><h1>ML Monitor</h1><p className="lead">Only models that have actually been trained appear here</p>{err&&<div className="err" role="alert">{err}</div>}<Wait d={m} e={e}>{m&&(m.trained?
    <><div className="grid g5"><Kpi l="Model" v={m.version} s={m.task}/><Kpi l="Trained" v={m.trained_at.slice(0,16).replace("T"," ")} s={`${m.train_rows} train rows, ${m.test_rows} later test rows`}/>
    {m.metrics?<><Kpi l="Precision" v={f2(m.metrics.precision)} s="On the later test period"/><Kpi l="Recall" v={f2(m.metrics.recall)} s="On the later test period"/><Kpi l="ROC-AUC" v={m.metrics.roc_auc==null?"n/a":f2(m.metrics.roc_auc)} s="n/a if the test period has one class"/></>:null}</div>
    {m.note&&<div className="card">{m.note}</div>}
    {m.metrics&&<div className="grid g2"><div className="card"><h2>Confusion matrix</h2><table><tbody><tr><td></td><th>Predicted normal</th><th>Predicted failure</th></tr><tr><th>Actually normal</th><td>{m.metrics.confusion_matrix.tn}</td><td>{m.metrics.confusion_matrix.fp}</td></tr><tr><th>Actually failure</th><td>{m.metrics.confusion_matrix.fn}</td><td>{m.metrics.confusion_matrix.tp}</td></tr></tbody></table></div>
    <div className="card"><h2>What the model uses</h2>{m.importances.map(([n,v])=><div key={n}>{n}<span className="mute"> {(v*100).toFixed(0)}%</span><div className="bar"><i style={{width:v*100+"%",background:"var(--acc)"}}/></div></div>)}</div></div>}
    <div className="card mute">Experiment tracking: {m.mlflow}. {m.drift}</div></>
    :<div className="card"><h2>No model trained yet</h2><p>Right now the app only uses a statistical rule (distance from each machine's baseline). That is not a machine-learning model, so no accuracy is shown.</p><p className="mute">Training uses a time-ordered split: it learns from the earlier 70% of records and is tested on the later 30%. With a failure column it trains a classifier (needs enough failure events). Without one it trains an anomaly detector and reports no accuracy.</p><button className="btn pri" disabled={busy} onClick={train}>{busy?"Training…":"Train model"}</button></div>)}</Wait></>}

const PAGES={Overview,"Equipment Monitor":Equipment,Alerts,Maintenance,"ML Monitor":Model};
export default function App(){const [st,setSt]=useState(null),[cur,setCur]=useState("Dataset"),[err,setErr]=useState(null);
  const refresh=useCallback(async page=>{try{const s=await api("/state");setSt(s);setCur(s.unlocked?page:"Dataset")}catch(e){setErr(e.message)}},[]);
  useEffect(()=>{refresh("Dataset")},[refresh]);
  if(err)return <main><div className="err" role="alert">Cannot reach the backend: {err}</div></main>;
  if(!st)return <main><p className="mute">Loading…</p></main>;
  const Page=PAGES[cur];
  return <div className="app"><nav><div className="logo">SentinelOps</div><div className="sub">Predictive maintenance</div>
    {Object.keys(PAGES).map(p=><button key={p} disabled={!st.unlocked} className={p===cur?"on":""} onClick={()=>setCur(p)}>{p}</button>)}
    <div className="sep">Setup</div><button className={cur==="Dataset"?"on":""} onClick={()=>setCur("Dataset")}>Dataset</button></nav>
    <main>{st.unlocked&&Page?<Page key={cur}/>:<Dataset state={st} done={refresh}/>}</main></div>}
