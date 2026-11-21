'use client';

import { useEffect, useRef, useState } from 'react';
import { ArrowUpRight, X } from 'lucide-react';
import { API_URL, canManage, isAdmin, type User } from '@/lib/api';
import { DataFields, ErrorNotice, Loading, useResource } from './ui';
import { SourcePermissions } from './source-permissions';

export function SourceDialog({ id, user, onClose }: { id: string; user: User; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const path = `/documents/${encodeURIComponent(id)}`;
  const { data, error, loading, reload } = useResource<Record<string, unknown>>(path);
  const [downloadError, setDownloadError] = useState('');
  const [downloading, setDownloading] = useState(false);
  const [saved, setSaved] = useState(false);
  useEffect(() => { dialog.current?.showModal(); }, []);

  async function download() {
    if (downloading) return;
    setDownloading(true);
    setDownloadError('');
    try {
      const response = await fetch(`${API_URL}${path}/source`, { credentials: 'include' });
      if (!response.ok) throw new Error(`Source unavailable (${response.status}).`);
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url;
      link.download = String(data?.title || 'source');
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      setDownloadError(error instanceof Error ? error.message : 'Could not download the source.');
    } finally {
      setDownloading(false);
    }
  }

  const editable = data && (isAdmin(user) || (canManage(user) && data.owner_id === user.id));
  return (
    <dialog ref={dialog} onCancel={onClose} className="source-dialog" aria-labelledby="source-title">
      <header>
        <div><h2 id="source-title">{String(data?.title || 'Source document')}</h2></div>
        <button className="icon-button" onClick={onClose} aria-label="Close source"><X /></button>
      </header>
      {saved && <p role="status">Document access saved.</p>}
      {loading ? <Loading /> : error ? <ErrorNotice message={error} /> : data && <>
        <p><strong>{String(data.status ?? 'Unknown')}</strong> · {String(data.access_scope ?? 'Unknown')} access</p>
        <button className="secondary" disabled={downloading} onClick={download}>
          {downloading ? 'Downloading…' : 'Download original source'} <ArrowUpRight size={16} />
        </button>
        {downloadError && <ErrorNotice message={downloadError} />}
        {editable && <SourcePermissions id={id} document={data} onSaved={() => { setSaved(true); reload(); }} />}
        <details className="source-content">
          <summary>Document details</summary>
          <DataFields data={data} />
        </details>
      </>}
    </dialog>
  );
}
