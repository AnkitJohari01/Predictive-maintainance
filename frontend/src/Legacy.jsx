import {useCallback,useEffect,useRef,useState} from "react";
import "./app.css";
const sid=localStorage.getItem("sid")||(()=>{const v=(crypto.randomUUID?crypto.randomUUID():String(Math.random()).slice(2)+"abcdefgh");localStorage.setItem("sid",v);return v})();
async function api(path,{json,body,method}={}){
  const r=await fetch("/api"+path,{method:method||(json||body?"POST":"GET"),headers:{"X-Session":sid,...(json?{"Content-Type":"application/json"}:{})},body:json?JSON.stringify(json):body});
  const t=await r.json().catch(()=>({}));
  if(!r.ok){const d=t.detail;if(r.status===409&&typeof d==="string"&&d.startsWith("No active dataset"))window.dispatchEvent(new Event("dataset-lost"));throw new Error(Array.isArray(d)?d.map(x=>x.msg||x).join(" "):d||`Request failed (${r.status})`)}
  return t}
const LAB={critical:"Critical",watch:"Watch",healthy:"Healthy",unscored:"Not scored"},CLS={critical:"r",watch:"a",healthy:"g",unscored:"b"},COL={critical:"var(--red)",watch:"var(--amb)",healthy:"var(--grn)",unscored:"var(--mute)"};
const Pill=({s,t})=><span className={"pill p-"+CLS[s]}>{t||LAB[s]}</span>;
const f2=x=>(+x).toFixed(2);
function useLoad(path){const [d,setD]=useState(null),[e,setE]=useState(null),version=useRef(0);
  const load=useCallback(async()=>{const current=++version.current;try{const value=await api(path);if(current===version.current){setD({path,value});setE(null)}}catch(x){if(current===version.current)setE({path,value:x.message})}},[path]);
  useEffect(()=>{setD(null);setE(null);load();return()=>{version.current++}},[load]);return [d?.path===path?d.value:null,e?.path===path?e.value:null,load]}
const Wait=({d,e,children})=>e?<div className="err" role="alert">{e}</div>:d===null?<p className="mute">Loading…</p>:children;
const Kpi=({l,v,s,na})=><div className="card kpi" data-testid={"kpi-"+l}><span>{l}</span><b className={na?"na":""}>{v}</b><small>{s}</small></div>;

function Chart({s}){
  const container=useRef(null),[width,setWidth]=useState(640);
  useEffect(()=>{const observer=new ResizeObserver(entries=>setWidth(Math.max(210,Math.round(entries[0].contentRect.width))));if(container.current)observer.observe(container.current);return()=>observer.disconnect()},[]);
  const [selected,setSelected]=useState(s.points.length-1),index=Math.min(selected,s.points.length-1);
  const v=s.points.map(p=>p.v),hi=s.baseline+3*s.std,low=s.baseline-3*s.std,
    lo=Math.min(...v,low)-s.std,up=Math.max(...v,hi)+s.std,w=width,h=260;
  const times=s.points.map(p=>Date.parse(p.t)),span=Math.max(1,times.at(-1)-times[0]);
  const X=i=>60+(times[i]-times[0])*(w-78)/span,Y=y=>h-30-(y-lo)/(up-lo)*(h-48);
  const point=s.points[index],stamp=t=>new Date(t).toISOString().slice(0,16).replace('T',' ')+" UTC";
  const hover=e=>{const bounds=e.currentTarget.getBoundingClientRect(),target=times[0]+((e.clientX-bounds.left)/bounds.width*w-60)/(w-78)*span;
    setSelected(times.reduce((best,t,i)=>Math.abs(t-target)<Math.abs(times[best]-target)?i:best,0))};
  return <figure className="chart" ref={container}><div className="chart-key"><span>Sensor reading</span><span>Baseline mean</span><span>Critical bounds (±3σ)</span></div>
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" role="img" aria-label="Sensor history" onPointerMove={hover}>
      {[lo,(lo+up)/2,up].map(t=><g key={t}><line x1="60" x2={w-18} y1={Y(t)} y2={Y(t)} stroke="var(--line)"/><text x="52" y={Y(t)+4} textAnchor="end" fontSize="11" fill="var(--mute)">{Number(t.toPrecision(4))}</text></g>)}
      {[low,hi].map(t=><line key={t} x1="60" x2={w-18} y1={Y(t)} y2={Y(t)} stroke="var(--red)" strokeDasharray="5 4"/>)}
      <line x1="60" x2={w-18} y1={Y(s.baseline)} y2={Y(s.baseline)} stroke="var(--mute)" strokeDasharray="3 4"/>
      <polyline fill="none" stroke="var(--acc)" strokeWidth="2.5" points={v.map((y,i)=>X(i)+","+Y(y)).join(" ")}/>
      <line x1={X(index)} x2={X(index)} y1="18" y2={h-30} stroke="var(--acc)" opacity=".3"/>
      <circle cx={X(index)} cy={Y(point.v)} r="5" fill="var(--acc)" stroke="white" strokeWidth="2"/>
      <text x="60" y={h-8} fontSize="11" fill="var(--mute)">{stamp(s.points[0].t).slice(0,10)}</text><text x={w-18} y={h-8} textAnchor="end" fontSize="11" fill="var(--mute)">{stamp(s.points.at(-1).t).slice(0,10)}</text>
    </svg><input type="range" min="0" max={s.points.length-1} value={index} onChange={e=>setSelected(+e.target.value)} aria-label="Reading in sensor history"/>
    <figcaption data-testid="chart-reading"><strong>{f2(point.v)}</strong><span>{stamp(point.t)}</span></figcaption><small className="mute">{s.points.length} representative readings. Hover or use the slider to inspect. Values use the uploaded column's units.</small></figure>
}

function UploadControl({label,pri,onPick,busy}){return <><input id="telemetry-upload" type="file" aria-label="Upload equipment dataset" accept=".csv,.xlsx,.xls,.json" hidden onChange={e=>{const file=e.target.files[0];e.target.value="";onPick(file)}}/><button className={"btn "+(pri?"pri":"")} disabled={busy} onClick={()=>document.getElementById("telemetry-upload").click()}>{label}</button></>;}
function Dataset({state,done,onBusy}){
  const [stage,setStage]=useState("upload"),[p,setP]=useState(null),[m,setM]=useState(null),[q,setQ]=useState(null),[err,setErr]=useState(null),[busy,setBusy]=useState(false);
  const wrap=async fn=>{setBusy(true);onBusy(true);setErr(null);try{await fn()}catch(e){setErr(e.message)}finally{setBusy(false);onBusy(false)}};
  const pick=f=>f&&wrap(async()=>{setP(null);setM(null);setQ(null);const fd=new FormData();fd.append("file",f);if(f.name.toLowerCase().endsWith(".json")){await api("/bundles",{body:fd});setStage("upload");await done("Overview");return;}const r=await api("/datasets",{body:fd});setP(r);setM(r.mapping);setStage("map")});
  const check=()=>wrap(async()=>{setQ(await api("/datasets/check",{json:m}));setStage("check")});
  const run=()=>wrap(async()=>{await api("/datasets/process",{json:m});setStage("upload");await done("Overview")});
  const clear=()=>wrap(async()=>{await api("/dataset",{method:"DELETE"});await done("Dataset")});
  const Err=()=>err?<div className="err" role="alert">{err}</div>:null;
  const Steps=({n})=><div className="steps">{["1 Upload","2 Match columns","3 Check data"].map((s,i)=><span key={s} className={i===n?"on":""}>{s}</span>)}</div>;

  if(stage==="map"&&p){const set=(k,v)=>setM({...m,[k]:v===""?null:v});
    return <><h1>Match columns</h1><p className="lead">{p.name} · {p.rows} rows. Correct anything that looks wrong.</p><Steps n={1}/><Err/>
    <div className="card"><div className="row">{[["timestamp","Timestamp",0],["id","Equipment ID",0],["failure","Failure flag (optional)",1]].map(([k,l,o])=><div key={k}><label htmlFor={"m"+k}>{l}</label><select id={"m"+k} value={m[k]||""} onChange={e=>set(k,e.target.value)}>{o||!m[k]?<option value="">None</option>:null}{p.columns.map(c=><option key={c}>{c}</option>)}</select></div>)}</div>
    <label>Sensor columns</label><div>{p.columns.map(c=><label key={c} className="chk"><input type="checkbox" checked={m.sensors.includes(c)} onChange={e=>setM({...m,sensors:e.target.checked?[...m.sensors,c]:m.sensors.filter(x=>x!==c)})}/>{c}</label>)}</div>
    <h2>Preview (first 5 rows)</h2><div className="scroll"><table><thead><tr>{p.columns.map(c=><th key={c}>{c}</th>)}</tr></thead><tbody>{p.preview.map((r,i)=><tr key={i}>{p.columns.map(c=><td key={c}>{String(r[c]??"")}</td>)}</tr>)}</tbody></table></div>
    <p><button className="btn pri" disabled={busy} onClick={check}>{busy?"Checking…":"Check data"}</button> <button className="btn" disabled={busy} onClick={()=>setStage("upload")}>Cancel</button></p></div></>}
  if(stage==="check"&&q)return <><h1>Check data</h1><p className="lead">Review before anything is processed</p><Steps n={2}/><Err/>
    <div className="grid g5"><Kpi l="Rows" v={q.rows} s="Total data rows"/><Kpi l="Missing values" v={q.missing_pct+"%"} s={q.missing+" empty cells. Skipped, not invented"}/><Kpi l="Duplicate rows" v={q.duplicates} s="Removed before analysis"/><Kpi l="Invalid timestamps" v={q.bad_timestamps} s="Excluded from analysis"/><Kpi l="Extreme outliers" v={q.outliers} s="Over 4σ from the column mean. Kept"/></div>
    <div className="notice"><strong>{q.usable_rows} usable rows after cleaning</strong><p>{q.excluded_rows} rows excluded. {q.invalid_sensor_values} non-numeric or non-finite sensor values excluded from calculations. Missing sensor values are skipped; no sensor readings are invented.</p></div>
    <p><button className="btn pri" disabled={busy} onClick={run}>{busy?"Processing…":"Process and unlock"}</button> <button className="btn" disabled={busy} onClick={()=>setStage("map")}>Back</button></p></>;
  if(state.unlocked){const d=state.dataset;return <><h1>Dataset</h1><p className="lead">The active dataset drives every page</p><Err/><div className="card"><h2>{d.name}</h2>
    <p>{d.quality.rows} rows · {d.machines} machines · {d.mapping.sensors.length} sensors · failure column: {d.mapping.failure||"none"}</p>
    <p className="mute">{d.quality.usable_rows} usable rows; {d.quality.excluded_rows} excluded during cleaning. {d.quality.invalid_sensor_values} invalid sensor values excluded. All times are normalized to UTC.</p>
    <div className="notice">A replacement becomes active only after successful processing. Replacing or clearing a dataset resets its work orders, alert decisions and trained model.</div>
    <UploadControl onPick={pick} busy={busy} label={busy?"Reading…":"Replace dataset"}/> <button className="btn" disabled={busy} onClick={clear}>Clear dataset</button></div></>}
  return <><h1>Upload your equipment data</h1><p className="lead">Everything stays locked until your file passes validation.</p><Steps n={0}/><Err/>
    <div className="drop"><div className="upload-symbol" aria-hidden="true"><svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6"/></svg></div><b>Connect your equipment history</b><p className="mute">Upload a CSV or Excel file with one row per reading. Match your columns, review data quality, then unlock your workspace.</p><UploadControl onPick={pick} busy={busy} label={busy?"Reading…":"Choose file"} pri/><p className="file-note">CSV, XLSX, XLS or complete JSON bundle · Up to 50 MB by default</p></div>
    <div className="grid g2 upload-guide"><section className="card"><h2>What your file needs</h2><dl><dt>Timestamp</dt><dd>A readable date or ISO timestamp for each reading.</dd><dt>Equipment ID</dt><dd>A consistent asset identifier, such as your plant's equipment tag.</dd><dt>Sensor readings</dt><dd>At least one numeric measurement column. Put units in column names.</dd><dt>Failure flag (optional)</dt><dd>Complete 0/1 or true/false labels. Leave unmapped if unavailable.</dd></dl></section><section className="card"><h2>From readings to maintenance</h2><p>At least 20 usable unique rows are required. Each equipment sensor needs 10 readings to calculate a condition baseline.</p><p>After processing, review equipment condition, inspect sensor trends, manage alerts and create maintenance work orders.</p><p className="mute">No sample results are loaded. Failure dates, cost savings and model accuracy appear only when supported by the data and method.</p></section></div></>}

function Overview(){const [o,e]=useLoad("/overview"),[eq,e2]=useLoad("/equipment"),[q,setQ]=useState(""),[so,setSo]=useState("risk"),[status,setStatus]=useState("");
  return <Wait d={o&&eq} e={e||e2}>{o&&eq&&(()=>{const k=o.kpis,h=k.health;let L=eq.filter(a=>a.id.toLowerCase().includes(q.toLowerCase())&&(!status||a.status===status));if(so==="id")L=[...L].sort((a,b)=>a.id.localeCompare(b.id));
    return <><h1>Control tower</h1><p className="lead">{o.dataset}</p><div className="grid g5">
    <Kpi l="Equipment monitored" v={k.equipment.value} s={k.equipment.definition}/>
    <Kpi l="Health (critical / watch / healthy)" v={<><span style={{color:COL.critical}}>{h.critical}</span> / <span style={{color:COL.watch}}>{h.watch}</span> / <span style={{color:COL.healthy}}>{h.healthy}</span></>} s={h.definition}/>
    <Kpi l="Observed failures" v={k.failures.available?k.failures.value:"Insufficient data"} s={k.failures.available?`${k.failures.rate_pct}% of records. ${k.failures.definition}`:k.failures.reason} na={!k.failures.available}/>
    <Kpi l="Open work orders" v={k.open_work_orders.value} s={k.open_work_orders.definition}/>
    <Kpi l="Remaining useful life" v="Insufficient data" s={k.remaining_useful_life.reason} na/></div>
    <section className="card"><h2>Fleet condition</h2><div className="distribution" aria-label="Equipment counts by condition">{Object.keys(LAB).map(s=><div key={s} style={{flex:h[s]||0}} title={`${LAB[s]}: ${h[s]}`}><span style={{background:COL[s]}}/></div>)}</div><div className="legend">{Object.keys(LAB).map(s=><span key={s}><Pill s={s}/> {h[s]}</span>)}</div><p className="mute">Condition index = 100 minus a capped baseline shift score. It is a statistical indicator, not a failure probability. Assets with insufficient readings remain unscored.</p></section>
    <div className="card scroll"><h2>Equipment</h2><div className="row"><div><label htmlFor="q">Search equipment</label><input id="q" type="search" value={q} onChange={e=>setQ(e.target.value)}/></div><div><label htmlFor="equipment-status">Equipment status</label><select id="equipment-status" value={status} onChange={e=>setStatus(e.target.value)}><option value="">All conditions</option>{Object.keys(LAB).map(s=><option key={s} value={s}>{LAB[s]}</option>)}</select></div><div><label htmlFor="so">Sort by</label><select id="so" value={so} onChange={e=>setSo(e.target.value)}><option value="risk">Largest baseline shift</option><option value="id">Name</option></select></div></div>
    <p className="mute">Showing {L.length} of {eq.length} assets</p><table><thead><tr><th>Equipment</th><th>Condition index</th><th>Status</th><th>Main driver</th><th>Records</th></tr></thead><tbody>{L.length?L.map(a=><tr key={a.id}><td><strong>{a.id}</strong></td><td>{a.health==null?"Not scored":<><span>{a.health} / 100</span><div className="bar"><i style={{width:a.health+"%",background:COL[a.status]}}/></div></>}</td><td><Pill s={a.status}/></td><td>{a.status==="unscored"?"Needs at least 10 readings per sensor":a.worst&&a.max_z>=1.5?`${a.worst} (${a.sensors[a.worst].z>0?"+":""}${f2(a.sensors[a.worst].z)} σ)`:"Within baseline range"}</td><td>{a.records}</td></tr>):<tr><td colSpan="5" className="mute">No equipment matches “{q}”.</td></tr>}</tbody></table></div></>})()}</Wait>}

function Equipment({initialId}){const [list,e]=useLoad("/equipment"),[id,setId]=useState(initialId||null),[sn,setSn]=useState(null);
  const sel=id||list?.[0]?.id,[a,e2]=useLoad(sel?"/equipment/"+encodeURIComponent(sel):"/state");
  return <Wait d={list} e={e}>{list&&<><h1>Condition &amp; diagnostics</h1><p className="lead">Pick a machine to see the evidence behind its status</p>
    <div className="row"><div style={{maxWidth:260}}><label htmlFor="as">Equipment</label><select id="as" value={sel} onChange={e=>{setId(e.target.value);setSn(null)}}>{list.map(x=><option key={x.id}>{x.id}</option>)}</select></div></div>
    <Wait d={a&&a.sensors?a:null} e={e2}>{a&&a.sensors&&(()=>{const ns=Object.keys(a.sensors),n=ns.includes(sn)?sn:a.worst||ns[0];
    return !ns.length?<div className="card">Not enough readings to score this machine (at least 10 per sensor are needed).</div>:<><div className="asset-summary"><strong>{a.id}</strong><Pill s={a.status}/><span>Condition index {a.health} / 100</span><span>{a.records} records</span><span>Last reading {a.last}</span></div><div className="grid g2"><div className="card"><h2>{n}</h2><p className="sensor-switch">{ns.map(k=><button key={k} aria-pressed={k===n} className={"btn sm "+(k===n?"pri":"")} onClick={()=>setSn(k)}>{k}</button>)}</p><Chart key={sel+n} s={a.sensors[n]}/></div>
    <div className="card scroll"><h2>Evidence</h2><table><thead><tr><th>Sensor</th><th>Recent</th><th>Baseline</th><th>Shift</th></tr></thead><tbody>{ns.map(k=>{const x=a.sensors[k];return <tr key={k}><td>{k}</td><td>{f2(x.recent)}</td><td>{f2(x.baseline)}</td><td><Pill s={x.status} t={(x.z>0?"+":"")+f2(x.z)+" σ"}/></td></tr>})}</tbody></table>
    <p className="mute">Recent = mean of the last 3 readings. Baseline = mean of the first 60% of this machine's history. This is a statistical rule, not a trained model, and it does not predict a failure date.</p></div></div></>})()}</Wait></>}</Wait>}

function Alerts(){const [f,setF]=useState(""),[L,e,reload]=useLoad("/alerts"+(f?"?status="+f:"")),[err,setErr]=useState(null);
  const set=async(key,status)=>{try{await api("/alerts/status",{method:"PATCH",json:{key,status}});reload()}catch(x){setErr(x.message)}};
  return <><h1>Alert triage</h1><p className="lead">Raised by comparing the latest readings in the file with each machine's baseline. These are historical records, not live events.</p>
  <div className="row"><div style={{maxWidth:200}}><label htmlFor="af">Status</label><select id="af" value={f} onChange={x=>setF(x.target.value)}><option value="">All</option>{["Open","Acknowledged","Resolved"].map(o=><option key={o}>{o}</option>)}</select></div></div>
  {err&&<div className="err" role="alert">{err}</div>}<Wait d={L} e={e}>{L&&<div className="card scroll">{L.length?<table><thead><tr><th>Severity</th><th>Equipment</th><th>Why it triggered</th><th>Recommended action</th><th>Data time</th><th>Status</th><th></th></tr></thead><tbody>{L.map(a=><tr key={a.key}><td><Pill s={a.severity}/></td><td>{a.asset}</td><td>{a.why}</td><td>{a.action}</td><td>{a.data_timestamp}</td><td>{a.status}</td><td>{a.status==="Open"&&<button className="btn sm" onClick={()=>set(a.key,"Acknowledged")}>Acknowledge</button>} {a.status!=="Resolved"&&<button className="btn sm" onClick={()=>set(a.key,"Resolved")}>Resolve</button>}</td></tr>)}</tbody></table>:<p className="mute">No alerts match this filter.</p>}</div>}</Wait></>}

function Maintenance(){const [R,e]=useLoad("/maintenance/recommendations"),[W,e2,reload]=useLoad("/workorders"),[err,setErr]=useState(null);
  const [busy,setBusy]=useState(false);
  const call=async(path,opt)=>{setBusy(true);setErr(null);try{await api(path,opt);await reload()}catch(x){setErr(x.message)}finally{setBusy(false)}};
  return <><h1>Maintenance planning</h1><p className="lead">Generated recommendations are suggestions. Work orders are records created here.</p>{err&&<div className="err" role="alert">{err}</div>}
  <Wait d={R} e={e}>{R&&<div className="card scroll"><h2>Recommended inspections (generated, ranked by risk)</h2>{R.length?<table><thead><tr><th>Priority</th><th>Equipment</th><th>Action</th><th>Evidence</th><th></th></tr></thead><tbody>{R.map(r=><tr key={r.asset}><td>{r.priority}</td><td>{r.asset} <Pill s={r.status}/></td><td>{r.action}</td><td>{r.evidence}</td><td><button className="btn sm" disabled={busy} onClick={()=>call("/workorders",{json:{title:`Inspect ${r.asset}: ${r.sensor}`,asset:r.asset}})}>Create work order</button></td></tr>)}</tbody></table>:<p className="mute">No inspections were generated. Unscored assets need more readings before assessment.</p>}</div>}</Wait>
  <Wait d={W} e={e2}>{W&&<div className="card scroll"><h2>Work orders (records)</h2>{W.length?<table><thead><tr><th>Job</th><th>Assigned to</th><th>Due</th><th>Status</th></tr></thead><tbody>{W.map(w=><tr key={w.id}><td>{w.title}</td><td><input type="text" aria-label="Assignee" defaultValue={w.assignee} onBlur={x=>x.target.value!==w.assignee&&call("/workorders/"+w.id,{method:"PATCH",json:{assignee:x.target.value}})}/></td><td><input type="date" aria-label="Due date" defaultValue={w.due} onChange={x=>call("/workorders/"+w.id,{method:"PATCH",json:{due:x.target.value}})}/></td><td><select aria-label="Status" value={w.status} onChange={x=>call("/workorders/"+w.id,{method:"PATCH",json:{status:x.target.value}})}>{["Open","In progress","Done"].map(o=><option key={o}>{o}</option>)}</select></td></tr>)}</tbody></table>:<p className="mute">No work orders yet.</p>}<p className="mute">Cost and downtime savings require a configured mapping of cost and production inputs.</p></div>}</Wait></>}

function Model(){const [m,e,reload]=useLoad("/model"),[err,setErr]=useState(null),[busy,setBusy]=useState(false);
  const train=async()=>{setBusy(true);setErr(null);try{await api("/model/train",{method:"POST"});reload()}catch(x){setErr(x.message)}finally{setBusy(false)}};
  return <><h1>ML &amp; data assurance</h1><p className="lead">Only models that have actually been trained appear here</p>{err&&<div className="err" role="alert">{err}</div>}<Wait d={m} e={e}>{m&&(m.trained?
    <><div className="grid g5"><Kpi l="Model" v={m.version} s={m.task}/><Kpi l="Trained" v={m.trained_at.slice(0,16).replace("T"," ")+" UTC"} s={`${m.train_rows} train rows, ${m.test_rows} later test rows`}/>
    {m.metrics?<><Kpi l="Precision" v={f2(m.metrics.precision)} s="On the later test period"/><Kpi l="Recall" v={f2(m.metrics.recall)} s="On the later test period"/><Kpi l="ROC-AUC" v={m.metrics.roc_auc==null?"n/a":f2(m.metrics.roc_auc)} s="n/a if the test period has one class"/></>:null}</div>
    {m.note&&<div className="card">{m.note}</div>}
    {m.metrics&&<div className="grid g2"><div className="card"><h2>Confusion matrix</h2><table><tbody><tr><td></td><th>Predicted normal</th><th>Predicted failure</th></tr><tr><th>Actually normal</th><td>{m.metrics.confusion_matrix.tn}</td><td>{m.metrics.confusion_matrix.fp}</td></tr><tr><th>Actually failure</th><td>{m.metrics.confusion_matrix.fn}</td><td>{m.metrics.confusion_matrix.tp}</td></tr></tbody></table></div>
    <div className="card"><h2>What the model uses</h2>{m.importances.map(([n,v])=><div key={n}>{n}<span className="mute"> {(v*100).toFixed(0)}%</span><div className="bar"><i style={{width:v*100+"%",background:"var(--acc)"}}/></div></div>)}</div></div>}
    <div className="card mute"><p>{m.validation}</p>Experiment tracking: {m.mlflow}. {m.drift}</div><button className="btn" disabled={busy} onClick={train}>{busy?"Training…":"Retrain model"}</button></>
    :<div className="card"><h2>No model trained yet</h2><p>Right now the app only uses a statistical rule (distance from each machine's baseline). That is not a machine-learning model, so no accuracy is shown.</p><p className="mute">Training uses a time-ordered split: it learns from roughly the earlier 70% of timestamps and is tested on later timestamps. Missing values use training-period medians. With a failure column it trains a classifier (needs enough failure events). Without one it trains an anomaly detector and reports no accuracy.</p><button className="btn pri" disabled={busy} onClick={train}>{busy?"Training…":"Train model"}</button></div>)}</Wait></>}

export {api, sid, Dataset, Overview, Equipment, Alerts, Maintenance, Model, Chart, Kpi};
