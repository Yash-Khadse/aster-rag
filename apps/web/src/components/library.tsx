'use client';

import { useRef, useState, type FormEvent } from 'react';
import { FileText, RefreshCw, Trash2, Upload } from 'lucide-react';
import { api, canManage, isAdmin, type User } from '@/lib/api';
import { Badge, Empty, ErrorNotice, Loading, useResource } from './ui';

type Document = {
  id: string;
  title?: string;
  filename?: string;
  owner_id?: string;
  status: string;
  access_scope: string;
  created_at: number;
  chunk_count?: number;
  error?: string;
};

const pageSize = 25;

export function Library({ user, onSource }: { user: User; onSource: (id: string) => void }) {
  const [draft, setDraft] = useState('');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(0);
  const [failure, setFailure] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState<string>();
  const submitting = useRef(false);
  const params = new URLSearchParams({ q: query, offset: String(page * pageSize), limit: String(pageSize + 1) });
  const { data, error, loading, reload } = useResource<Document[]>(`/documents?${params}`);
  const docs = (data ?? []).slice(0, pageSize);

  async function action(path: string, success: string, method = 'POST', body?: FormData) {
    if (submitting.current) return false;
    submitting.current = true;
    setBusy(true);
    setFailure('');
    setNotice('');
    try {
      const result = await api<{ job_id?: string | null }>(path, { method, body });
      setNotice(path === '/ingestion-jobs/run' && !result.job_id ? 'No queued jobs are available.' : success);
      setConfirm(undefined);
      reload();
      return true;
    } catch (error) {
      setFailure(error instanceof Error ? error.message : 'The request failed.');
      return false;
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    if (await action('/documents', 'Document saved. Check its status in the library.', 'POST', new FormData(form))) {
      form.reset();
      setPage(0);
      setQuery('');
      setDraft('');
    }
  }

  function filter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPage(0);
    setQuery(draft.trim());
  }

  return (
    <div className="page-content">
      <div className="section-intro">
        <div>
          
          <h2>Workspace documents</h2>
          <p>Upload sources and check whether they’re ready to search.</p>
        </div>
        <button className="secondary" disabled={busy || loading} onClick={reload}><RefreshCw size={16} /> Refresh</button>
      </div>
      {canManage(user) && <form className="upload-box" onSubmit={upload}>
        <Upload size={24} />
        <div>
          <strong>Add a document</strong>
          <p>PDF, DOCX, TXT, Markdown, HTML, or CSV.</p>
          <input aria-label="Document file" type="file" name="file" accept=".pdf,.docx,.txt,.md,.html,.csv" required />
        </div>
        <label>Visibility<select name="access_scope">
          <option value="workspace">Workspace</option><option value="private">Private</option>
        </select></label>
        <button className="primary" disabled={busy}>Upload document</button>
      </form>}
      {(error || failure) && <ErrorNotice message={failure || error} />}
      {notice && <p role="status">{notice}</p>}
      <div className="row library-filter">
        <form className="row" onSubmit={filter}>
          <input aria-label="Filter documents" placeholder="Find a document…" value={draft} maxLength={255} onChange={event => setDraft(event.target.value)} />
          <button className="secondary" disabled={busy}>Search</button>
          {query && <button type="button" className="text-button" onClick={() => { setDraft(''); setQuery(''); setPage(0); }}>Clear</button>}
        </form>
        {isAdmin(user) && <button className="text-button" disabled={busy} onClick={() => action('/ingestion-jobs/run', 'Job processed. Check the updated document status.')}>Process next job</button>}
      </div>
      {loading ? <Loading /> : docs.length ? (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Document</th><th>Status</th><th>Access</th><th>Chunks</th><th>Actions</th></tr></thead>
            <tbody>{docs.map(doc => {
              const title = doc.title || doc.filename || 'Untitled document';
              const editable = isAdmin(user) || (canManage(user) && doc.owner_id === user.id);
              return <tr key={doc.id}>
                <td>
                  <button className="document-name" onClick={() => onSource(doc.id)}>
                    <FileText size={19} /><span>{title}<small>{new Date(doc.created_at * 1000).toLocaleDateString()}</small></span>
                  </button>
                  {doc.error && <p className="error-text small">{doc.error}</p>}
                </td>
                <td><Badge>{doc.status}</Badge></td><td>{doc.access_scope}</td><td>{doc.chunk_count ?? '—'}</td>
                <td>{editable && <div className="row">
                  {confirm === doc.id ? <>
                    <span className="small">Delete source?</span>
                    <button className="danger" disabled={busy} onClick={() => action(`/documents/${doc.id}`, 'Deletion queued.', 'DELETE')}>Delete</button>
                    <button className="text-button" onClick={() => setConfirm(undefined)}>Cancel</button>
                  </> : <>
                    <button className="icon-button" disabled={busy || !['ready', 'failed'].includes(doc.status)} aria-label={`Reindex ${title}`} onClick={() => action(`/documents/${doc.id}/reindex`, 'Reindexing queued.')}><RefreshCw size={16} /></button>
                    <button className="icon-button" disabled={busy} aria-label={`Delete ${title}`} onClick={() => setConfirm(doc.id)}><Trash2 size={16} /></button>
                  </>}
                </div>}</td>
              </tr>;
            })}</tbody>
          </table>
        </div>
      ) : !error && <Empty title={query ? 'No matching documents' : 'No documents on this page'}>
        {query ? 'Try another document name.' : 'Upload a document or return to a previous page.'}
      </Empty>}
      {(page > 0 || (data?.length ?? 0) > pageSize) && <nav className="row library-pagination" aria-label="Document pages">
        <button className="secondary" disabled={loading || busy || page === 0} onClick={() => setPage(previous => previous - 1)}>Previous</button>
        <span>Page {page + 1}</span>
        <button className="secondary" disabled={loading || busy || (data?.length ?? 0) <= pageSize} onClick={() => setPage(previous => previous + 1)}>Next</button>
      </nav>}
    </div>
  );
}
