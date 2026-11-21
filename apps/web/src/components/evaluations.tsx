'use client';
import {isAdmin,type User} from '@/lib/api';
import {DataFields,Empty,ErrorNotice,Loading,useResource} from './ui';
type Variant={strategy:string;status:string;metrics:Record<string,number|null>;latency_ms?:{p50:number;p95:number}};
type Run={id:string;created_at:number;status:string;result:{dataset_version?:string;semantic_benchmark?:boolean;judge?:{status:string};variants?:Variant[]}};
const percent=(value:number|null|undefined)=>value==null?'Not measured':`${(value*100).toFixed(1)}%`;
function Telemetry(){const data=useResource<Record<string,unknown>>('/analytics');return <section className="panel"><h3>Workspace telemetry</h3>{data.loading?<Loading/>:data.error?<ErrorNotice message={data.error}/>:<DataFields data={data.data}/>}</section>}
export function EvaluationStudio({user}:{user:User}){
 const runs=useResource<Run[]>('/evaluations');
 return <div className="page-content"><div className="section-intro"><div><h2>Retrieval evaluation results</h2><p>Measured retrieval on a versioned fictional corpus. Generation quality is evaluated separately.</p></div><button className="secondary" onClick={runs.reload}>Refresh results</button></div>
 {runs.loading?<Loading/>:runs.error?<ErrorNotice message={runs.error}/>:!runs.data?.length?<Empty title="No evaluation runs recorded">Run the evaluation CLI and import its report to inspect actual results here.</Empty>:runs.data.map(run=><section className="panel" key={run.id}><h3>Retrieval benchmark · {run.result.dataset_version||'Unversioned'}</h3><p className="small muted">{new Date(run.created_at*1000).toLocaleString()} · {run.status} · {run.result.semantic_benchmark?'Real embedding model':'Deterministic test embeddings'} · Judge: {run.result.judge?.status||'not_run'}</p><div className="table-wrap"><table><thead><tr><th>Method</th><th>Recall@K</th><th>Precision@K</th><th>MRR</th><th>nDCG</th><th>p50</th><th>p95</th><th>Run</th></tr></thead><tbody>{run.result.variants?.map(v=><tr key={v.strategy}><td>{v.strategy}</td><td>{percent(v.metrics.recall)}</td><td>{percent(v.metrics.precision)}</td><td>{v.metrics.mrr?.toFixed(3)??'—'}</td><td>{v.metrics.ndcg?.toFixed(3)??'—'}</td><td>{v.latency_ms?.p50?.toFixed(0)??'—'} ms</td><td>{v.latency_ms?.p95?.toFixed(0)??'—'} ms</td><td>{v.status}</td></tr>)}</tbody></table></div><details><summary>Inspect report and per-question results</summary><DataFields data={run.result}/></details></section>)}
 {isAdmin(user)&&<Telemetry/>}</div>;
}
