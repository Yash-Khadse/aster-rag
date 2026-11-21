'use client';
import {useEffect,useState} from 'react';
import {AlertCircle,ArrowUpRight,FileText,LoaderCircle} from 'lucide-react';
import {api,type Evidence} from '@/lib/api';
export function ErrorNotice({message}:{message:string}){return <div role="alert" className="notice error"><AlertCircle size={18}/>{message}</div>}
export function Empty({title,children}:{title:string;children:React.ReactNode}){return <div className="empty"><FileText size={30}/><h3>{title}</h3><p>{children}</p></div>}
export function Loading(){return <div role="status" className="loading"><LoaderCircle size={18} className="spin"/> Loading workspace data…</div>}
export function Badge({children}:{children:React.ReactNode}){return <span className="badge">{children}</span>}
export function useResource<T>(path:string) {
  const [revision,setRevision]=useState(0);
  const [result,setResult]=useState<{path:string;revision:number;data?:T;error:string}>();
  useEffect(()=>{
    const request = new AbortController();
    api<T>(path,{signal:request.signal}).then(data=>{
      if (!request.signal.aborted) setResult({path,revision,data,error:''});
    }).catch(error=>{
      if (!request.signal.aborted) {
        setResult({path,revision,error:error instanceof Error ? error.message : 'Unable to load workspace data.'});
      }
    });
    return ()=>request.abort();
  },[path,revision]);
  const current = result?.path === path ? result : undefined;
  const loading = current?.revision !== revision;
  return {data:current?.data,error:loading ? '' : current?.error ?? '',loading,reload:()=>setRevision(n=>n+1)};
}
export function DataFields({data}:{data:unknown}){if(data===null||data===undefined)return <span className="muted">Not recorded</span>;if(Array.isArray(data))return <div className="records">{data.length?data.map((v,i)=><div key={i} className="record"><DataFields data={v}/></div>):<p className="muted">No records yet.</p>}</div>;if(typeof data==='object')return <dl className="fields">{Object.entries(data).map(([k,v])=><div key={k}><dt>{k.replaceAll('_',' ')}</dt><dd>{typeof v==='object'?<DataFields data={v}/>:String(v)}</dd></div>)}</dl>;return <span>{String(data)}</span>}
export function EvidenceCard({item,index,onOpen}:{item:Evidence;index:number;onOpen:(id:string)=>void}){return <article className="evidence-card"><div className="row"><span className="citation-number">{index+1}</span><span className="small muted">{item.page?`Page ${item.page}`:'Source excerpt'}</span></div><h3>{item.title||'Source document'}</h3>{item.section&&<p className="small muted">{item.section}</p>}<blockquote>{item.text||item.excerpt||'Open the source to inspect this citation.'}</blockquote><button className="text-button" onClick={()=>onOpen(item.document_id)}>View source <ArrowUpRight size={14}/></button></article>}
