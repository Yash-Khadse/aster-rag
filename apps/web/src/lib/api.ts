if (process.env.NODE_ENV === 'production' && !process.env.NEXT_PUBLIC_API_URL) throw new Error('NEXT_PUBLIC_API_URL must be set at build time for production builds.');
export const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';
export type User = {id:string;email:string;name:string;role:string;organization_id:string;workspace_id:string};
export type Evidence = {id?:string;citation_id?:string;document_id:string;title?:string;text?:string;excerpt?:string;page?:number;section?:string;score?:number;rerank_score?:number};
export type ChatMetrics = Record<string,unknown> & {reranker_status?:string|null;reranker_reason?:string|null;reranker_fallback?:boolean};
export type ChatResult = {answer:string;citations:Evidence[];session_id:string;message_id:string;status:string;metrics?:ChatMetrics};
export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

async function responseError(response: Response) {
  const body = await response.json().catch(() => ({}));
  const detail = body?.detail;
  if (typeof detail === 'string') return new ApiError(response.status, detail);
  if (Array.isArray(detail)) {
    const messages = detail.flatMap(item => typeof item?.msg === 'string' ? [item.msg] : []);
    if (messages.length) return new ApiError(response.status, messages.join('. '));
  }
  return new ApiError(response.status, `Request failed (${response.status}).`);
}
// The session itself is an HttpOnly cookie; only the CSRF token lives here, in memory (recovered via /auth/me on reload).
let csrf = '';
const safeMethods = ['GET', 'HEAD', 'OPTIONS'];
function csrfHeader(headers: Headers, method = 'GET') {
  if (csrf && !safeMethods.includes(method.toUpperCase())) headers.set('X-CSRF-Token', csrf);
}
export function logout() {
  const done = api('/auth/logout', { method: 'POST' }).catch(() => {});
  csrf = '';
  return done;
}
export async function api<T>(path:string,init:RequestInit={}):Promise<T>{
 const headers = new Headers(init.headers); csrfHeader(headers, init.method);
 if(init.body && !(init.body instanceof FormData))headers.set('Content-Type','application/json');
 let res:Response; try{res=await fetch(`${API_URL}${path}`,{...init,headers,credentials:'include',cache:'no-store'});}catch(error){if(init.signal?.aborted)throw error;throw new Error('The knowledge service is unavailable. Check the API connection and try again.')}
 if(res.status===401)csrf='';
 if(!res.ok)throw await responseError(res);
 if(res.status===204)return undefined as T;
 const data=await res.json();
 if(typeof data?.csrf_token==='string')csrf=data.csrf_token;
 return data;
}
export function parseEvent(frame:string){const lines=frame.replace(/\r/g,'').split('\n'); const event=lines.find(l=>l.startsWith('event:'))?.slice(6).trim()||'message';const data=lines.filter(l=>l.startsWith('data:')).map(l=>l.slice(5).trimStart()).join('\n');return {event,data:data?JSON.parse(data):null}}
export async function streamChat(body:Record<string,unknown>,onStatus:(s:string)=>void,signal:AbortSignal):Promise<ChatResult>{
 const headers = new Headers({'Content-Type':'application/json',Accept:'text/event-stream'});
 csrfHeader(headers,'POST');
 const res=await fetch(`${API_URL}/chat/stream`,{method:'POST',headers,body:JSON.stringify(body),signal,credentials:'include'});
 if(!res.ok)throw await responseError(res);
 if(!res.body)throw new Error('Streaming is unavailable.');
 const reader=res.body.getReader(),decoder=new TextDecoder();let buffer='',result:ChatResult|undefined;
 function consume(frame:string){const item=parseEvent(frame);if(item.event==='result')result=item.data;if(item.event==='status')onStatus(typeof item.data==='string'?item.data:item.data?.message||item.data?.status||'Retrieving evidence');if(item.event==='error')throw new Error(item.data?.detail||item.data?.message||'Answer generation failed.')}
 try {
   while (true) {
     const {done,value} = await reader.read();
     buffer += decoder.decode(value,{stream:!done});
     // Normalize whole frames so CRLF split across network chunks still works.
     let boundary = /(?:\r\n|\n)(?:\r\n|\n)/.exec(buffer);
     while (boundary) {
       consume(buffer.slice(0,boundary.index));
       buffer = buffer.slice(boundary.index + boundary[0].length);
       boundary = /(?:\r\n|\n)(?:\r\n|\n)/.exec(buffer);
     }
     if (done) break;
   }
   if (buffer.trim()) consume(buffer);
 } finally {
   void reader.cancel().catch(()=>{});
   reader.releaseLock();
 }
 if(!result)throw new Error('The connection ended before an answer was received.');return result;
}
export const canManage = (user:User) => ['owner','admin','knowledge_manager','editor'].includes(user.role);
export const isAdmin = (user:User) => ['owner','admin'].includes(user.role);
