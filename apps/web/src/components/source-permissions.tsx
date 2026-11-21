'use client';

import { useState, type FormEvent } from 'react';
import { api } from '@/lib/api';
import { ErrorNotice, Loading, useResource } from './ui';

type Option = { id: string; name: string };
type Choices = { members: Option[]; groups: Option[]; collections: Option[] };

export function SourcePermissions({ id, document, onSaved }: {
  id: string;
  document: Record<string, unknown>;
  onSaved: () => void;
}) {
  const path = `/documents/${encodeURIComponent(id)}`;
  const options = useResource<Choices>(`${path}/permission-options`);
  const [scope, setScope] = useState(String(document.access_scope ?? 'workspace'));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const fields = new FormData(event.currentTarget);
    setBusy(true);
    setError('');
    try {
      await api(`${path}/permissions`, {
        method: 'PATCH',
        body: JSON.stringify({
          access_scope: scope,
          allowed_users: scope === 'restricted' ? fields.getAll('member') : [],
          allowed_groups: scope === 'restricted' ? fields.getAll('group') : [],
          collection_id: fields.get('collection') || null,
        }),
      });
      onSaved();
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Could not update access.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="source-permissions">
      <h3>Document access</h3>
      {options.loading ? <Loading /> : options.error ? <ErrorNotice message={options.error} /> : options.data && (
        <form onSubmit={save}>
          <fieldset disabled={busy}>
            <legend className="sr-only">Document permissions</legend>
            <label>Visibility
              <select value={scope} onChange={event => setScope(event.target.value)}>
                <option value="workspace">Everyone in the workspace</option>
                <option value="private">Owner and admins</option>
                <option value="restricted">Selected members and groups</option>
              </select>
            </label>
            {scope === 'restricted' && <>
              <p className="small muted">The document owner and workspace admins retain access.</p>
              <fieldset>
                <legend>Members</legend>
                <OptionList name="member" choices={options.data.members} selected={document.allowed_users} />
              </fieldset>
              <fieldset>
                <legend>Groups</legend>
                <OptionList name="group" choices={options.data.groups} selected={document.allowed_groups} />
              </fieldset>
            </>}
            <label>Collection
              <select name="collection" defaultValue={String(document.collection_id ?? '')}>
                <option value="">No collection</option>
                {options.data.collections.map(collection => <option key={collection.id} value={collection.id}>{collection.name}</option>)}
              </select>
            </label>
            <button className="primary" disabled={busy}>{busy ? 'Saving…' : 'Save access'}</button>
          </fieldset>
          {error && <ErrorNotice message={error} />}
        </form>
      )}
    </section>
  );
}

function OptionList({ name, choices, selected }: { name: string; choices: Option[]; selected: unknown }) {
  const checked = Array.isArray(selected) ? selected : [];
  if (!choices.length) return <p className="small muted">No {name}s available.</p>;
  return <div className="permission-options">
    {choices.map(option => <label className="row" key={option.id}>
      <input type="checkbox" name={name} value={option.id} defaultChecked={checked.includes(option.id)} />
      {option.name}
    </label>)}
  </div>;
}
