'use client';
import {useEffect,useRef,useState,type FormEvent} from 'react';
import {ArrowUp,ArrowUpRight,BookOpen,FileText,History,ListChecks,Plus,Shield,Square,ThumbsDown,ThumbsUp,Trash2,X} from 'lucide-react';
import {api,streamChat,type ChatMetrics,type ChatResult,type Evidence} from '@/lib/api';
import {ErrorNotice,EvidenceCard,useResource} from './ui';
type Message={id?:string;role:string;content:string;citations?:Evidence[];metrics?:ChatMetrics;feedback_rating?:number|null};
type Session={id:string;title:string};
export function Chat({onSource}:{onSource:(id:string)=>void}){const [messages,setMessages]=useState<Message[]>([]),[session,setSession]=useState<string>(),[question,setQuestion]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false),[status,setStatus]=useState(''),[evidence,setEvidence]=useState<Evidence[]>([]),[feedback,setFeedback]=useState<Record<string,string>>({});const [pendingVotes,setPendingVotes]=useState<string[]>([]);
const voteRequests=useRef(new Set<string>());
const [pendingDelete,setPendingDelete]=useState<string>();
const [selectedSource,setSelectedSource]=useState<number>();
const composerInput=useRef<HTMLTextAreaElement>(null);
const sourceDrawer=useRef<HTMLDialogElement>(null);

const [historyBusy,setHistoryBusy]=useState(false);const historyRequest=useRef<AbortController|null>(null);const controller=useRef<AbortController|null>(null),end=useRef<HTMLDivElement>(null);const history=useResource<Session[]>('/chat/sessions');useEffect(()=>()=>{controller.current?.abort();historyRequest.current?.abort()},[]);useEffect(()=>{if(messages.length||status)end.current?.scrollIntoView?.({block:'nearest'})},[messages,status]);async function withHistoryRequest(work:(signal:AbortSignal)=>Promise<void>) {
  if (controller.current || historyRequest.current) return;
  const request = new AbortController();
  historyRequest.current = request;
  setHistoryBusy(true);
  setError('');
  try {
    await work(request.signal);
  } catch (error) {
    if (!request.signal.aborted) setError(error instanceof Error ? error.message : 'Could not update conversation.');
  } finally {
    historyRequest.current = null;
    if (!request.signal.aborted) setHistoryBusy(false);
  }
}
async function openSession(id:string) {
  await withHistoryRequest(async signal=>{
    const data=await api<{messages:Message[]}>(`/chat/sessions/${encodeURIComponent(id)}`,{signal});
    if (signal.aborted) return;
    setSession(id);
    setMessages(data.messages);
    setSelectedSource(undefined);
    setFeedback(Object.fromEntries(data.messages.flatMap(message =>
      message.id && message.feedback_rating
        ? [[message.id, message.feedback_rating === 1 ? 'helpful' : 'unhelpful']]
        : []
    )));
    setEvidence(data.messages.filter(message=>message.role==='assistant').at(-1)?.citations ?? []);
  });
}
async function ask(e:FormEvent){e.preventDefault();if(!question.trim()||controller.current||historyRequest.current)return;const text=question.trim();setQuestion('');setBusy(true);setStatus('Finding relevant knowledge…');setError('');controller.current=new AbortController();try{const result:ChatResult=await streamChat({question:text,session_id:session,strategy:'hybrid',top_k:5,rerank:true},setStatus,controller.current.signal);setSession(result.session_id);setMessages(m=>[...m,{role:'user',content:text},{id:result.message_id,role:'assistant',content:result.answer,citations:result.citations,metrics:result.metrics}]);setEvidence(result.citations||[]);setSelectedSource(undefined);history.reload()}catch(e){setQuestion(draft=>draft || text);setError((e as Error).name==='AbortError'?'Generation stopped. You can ask another question.':(e as Error).message)}finally{controller.current=null;setBusy(false);setStatus('')}}async function rate(id:string,rating:string) {
  if (voteRequests.current.has(id)) return;
  voteRequests.current.add(id);
  setPendingVotes([...voteRequests.current]);
  setError('');
  try {
    await api('/feedback',{method:'POST',body:JSON.stringify({message_id:id,rating:rating==='helpful'?1:-1})});
    setFeedback(previous=>({...previous,[id]:rating}));
  } catch (error) {
    setError(error instanceof Error ? error.message : 'Could not save feedback.');
  } finally {
    voteRequests.current.delete(id);
    setPendingVotes([...voteRequests.current]);
  }
}
async function removeSession(id:string) {
  await withHistoryRequest(async signal=>{
    await api(`/chat/sessions/${encodeURIComponent(id)}`,{method:'DELETE',signal});
    if (signal.aborted) return;
    if (session===id) {
      setSession(undefined);
      setFeedback({});
      setMessages([]);
      setEvidence([]);
      setSelectedSource(undefined);
    }
    history.reload();
  });
}
function showSources(sources: Evidence[], index?: number) {
  setEvidence(sources);
  setSelectedSource(index);
  if (window.matchMedia('(max-width: 1050px)').matches) sourceDrawer.current?.showModal();
}

return <div className="chat-layout">
  <section className="chat-main" aria-label="Conversation">
    <div className="chat-toolbar">
      <button className="secondary" disabled={busy || historyBusy} onClick={() => {
        setSession(undefined); setMessages([]); setEvidence([]); setSelectedSource(undefined); setError('');
      }}><Plus size={16} /> <span className="new-conversation-label">New conversation</span><span className="mobile-only">New chat</span></button>
      <div className="row chat-tools">
        <details className="history">
          <summary><History size={16} aria-hidden="true" /> History</summary>
          <div className="history-list">
            {history.loading ? <p>Loading conversations…</p> : history.error ?
              <ErrorNotice message={history.error} /> : !history.data?.length ? <p>No conversations yet.</p> :
              history.data.map(item => <div key={item.id} className="row history-row">
                <button disabled={busy || historyBusy} className="text-button" aria-current={item.id === session ? 'true' : undefined}
                  onClick={event => { event.currentTarget.closest('details')?.removeAttribute('open'); void openSession(item.id); }}>
                  {item.title || 'Untitled conversation'}
                </button>
                {pendingDelete === item.id ? <div className="row">
                  <button className="danger" disabled={historyBusy} onClick={() => { setPendingDelete(undefined); void removeSession(item.id); }}>Delete</button>
                  <button className="text-button" onClick={() => setPendingDelete(undefined)}>Cancel</button>
                </div> : <button disabled={busy || historyBusy} className="icon-button" aria-label={`Delete ${item.title || 'conversation'}`}
                  onClick={() => setPendingDelete(item.id)}><Trash2 size={15} /></button>}
              </div>)}
          </div>
        </details>
        <button className="secondary evidence-mobile-trigger" onClick={() => sourceDrawer.current?.showModal()}>
          <BookOpen size={16} /> Sources {evidence.length > 0 && <span className="count">{evidence.length}</span>}
        </button>
      </div>
    </div>
    <div className="messages" aria-busy={busy || historyBusy} aria-live="polite">
      {messages.length === 0 ? <div className="chat-welcome">
        <h2>What would you like<br className="welcome-break" /> to find?</h2>
        <p>Ask a question about your workspace. Open the sources to read the evidence behind each answer.</p>
        <div className="suggestions" aria-label="Suggested questions">
          {([
            ['What is the organization’s leave policy?', FileText],
            ['Which steps follow a production outage?', ListChecks],
            ['Find the API authentication requirements.', Shield],
          ] as const).map(([prompt, Icon]) => <button key={prompt} onClick={() => { setQuestion(prompt); composerInput.current?.focus(); }}>
            <Icon size={17} aria-hidden="true" /><span>{prompt}</span><ArrowUpRight size={15} aria-hidden="true" />
          </button>)}
        </div>
      </div> : messages.map((message, index) => <article key={message.id || index} className={`message ${message.role}`}>
        <div className="message-label">{message.role === 'user' ? 'You' : 'Aster'}</div>
        <div className="message-body"><CitationText text={message.content} citations={message.citations ?? []}
          onSelect={source => showSources(message.citations ?? [], source)} /></div>
        {!!message.citations?.length && <button className="text-button" onClick={() => showSources(message.citations ?? [])}>
          <BookOpen size={15} /> {message.citations.length} supporting {message.citations.length === 1 ? 'source' : 'sources'} <ArrowUpRight size={14} /></button>}
        {message.id && message.role === 'assistant' && <div className="feedback">
          <button aria-label="Helpful answer" disabled={pendingVotes.includes(message.id)} aria-pressed={feedback[message.id] === 'helpful'} onClick={() => rate(message.id!, 'helpful')}><ThumbsUp size={16} /></button>
          <button aria-label="Unhelpful answer" disabled={pendingVotes.includes(message.id)} aria-pressed={feedback[message.id] === 'unhelpful'} onClick={() => rate(message.id!, 'unhelpful')}><ThumbsDown size={16} /></button>
          {feedback[message.id] && <span className="small muted">Feedback saved</span>}
        </div>}
        {message.metrics?.reranker_fallback && <p className="small muted" title={message.metrics.reranker_reason ?? undefined}>Reranker unavailable — showing un-reranked results</p>}
        {message.metrics && <details className="small muted"><summary>Response metrics</summary><pre>{JSON.stringify(message.metrics, null, 2)}</pre></details>}
      </article>)}
      {historyBusy && <p className="stream-status" role="status">Updating conversation…</p>}
      {busy && <p className="stream-status" role="status"><span className="pulse" />{status}</p>}
      <div ref={end} />
    </div>
    <div className="composer-area">
      {error && <ErrorNotice message={error} />}
      <form className="composer" onSubmit={ask}>
        <label className="sr-only" htmlFor="question">Ask a question</label>
        <textarea ref={composerInput} id="question" value={question} onChange={event => setQuestion(event.target.value)}
          maxLength={4000} placeholder="Ask about your workspace…" rows={2}
          onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault(); event.currentTarget.form?.requestSubmit();
          } }} />
        <div className="composer-bottom">
          <span><BookOpen size={15} aria-hidden="true" /> Workspace sources</span>
          <div className="row">
            <span className="composer-keyboard"><kbd>Enter</kbd> to send</span>
            {busy ? <button type="button" className="send" aria-label="Stop generation" onClick={() => controller.current?.abort()}><Square size={16} /></button>
              : <button className="send" disabled={historyBusy || !question.trim()} aria-label="Send question"><ArrowUp size={20} /></button>}
          </div>
        </div>
      </form>
      <p className="composer-note">Aster can miss context. Check the source before acting on an answer.</p>
    </div>
  </section>
  <aside className="evidence-panel evidence-desktop" aria-label="Answer sources">
    <EvidenceList evidence={evidence} selected={selectedSource} onSource={onSource} />
  </aside>
  <dialog className="evidence-panel evidence-drawer" ref={sourceDrawer} aria-label="Answer sources">
    <button className="icon-button evidence-close" aria-label="Close sources" onClick={() => sourceDrawer.current?.close()}><X size={20} /></button>
    <EvidenceList evidence={evidence} selected={selectedSource} onSource={id => { sourceDrawer.current?.close(); onSource(id); }} />
  </dialog>
</div>
}

function CitationText({text,citations,onSelect}:{text:string;citations:Evidence[];onSelect:(index:number)=>void}) {
  if (!citations.length) return text;
  const identifiers = new Map(citations.map((citation, index) => [citation.citation_id ?? citation.id, index]));
  return text.split(/(\[[^\]\r\n]+\])/).map((part, index) => {
    const citation = index % 2 === 1 ? identifiers.get(part.slice(1, -1)) : undefined;
    if (citation === undefined) return part;
    return <button key={index} className="inline-citation" aria-label={`Inspect source ${citation + 1}`}
      title={citations[citation].title} onClick={() => onSelect(citation)}>{citation + 1}</button>;
  });
}

function EvidenceList({ evidence, selected, onSource }: { evidence: Evidence[]; selected?: number; onSource: (id: string) => void }) {
  const selectedCard = useRef<HTMLDivElement>(null);
  useEffect(() => { selectedCard.current?.scrollIntoView?.({ block: 'nearest' }); }, [evidence, selected]);
  return <>
    <div className="evidence-heading">
      <div className="row"><BookOpen size={19} aria-hidden="true" /><h2>Sources</h2><span className="count">{evidence.length}</span></div>
      <p>Excerpts that support the selected answer.</p>
    </div>
    {evidence.length ? evidence.map((item, index) => (
      <div key={`${item.id ?? item.document_id}-${index}`} ref={selected === index ? selectedCard : undefined}
        className={selected === index ? 'evidence-selected' : undefined}>
        <EvidenceCard item={item} index={index} onOpen={onSource} />
      </div>
    )) : <div className="evidence-hint">
      <span className="citation-number" aria-hidden="true">1</span>
      <div><h3>No sources yet</h3><p>Select a numbered citation in an answer to read its excerpt here.</p></div>
    </div>}
    <div className="evidence-footer"><Shield size={15} aria-hidden="true" /> Sources follow workspace permissions</div>
  </>;
}
