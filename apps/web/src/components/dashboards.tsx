'use client';
import {useState,type FormEvent} from 'react';
import {api,type User} from '@/lib/api';
import {Badge,DataFields,Empty,ErrorNotice,Loading,useResource} from './ui';
export function Evaluations(){const runs=useResource<unknown[]>('/evaluations'),analytics=useResource<unknown>('/analytics');return <div className="page-content"><div className="section-intro"><div><h2>Retrieval evaluation results</h2><p>Recorded evaluation results and observed workspace usage.</p></div><button className="secondary" onClick={()=>{runs.reload();analytics.reload()}}>Refresh results</button></div><section className="panel"><h3>Evaluation runs</h3>{runs.loading?<Loading/>:runs.error?<ErrorNotice message={runs.error}/>:runs.data?.length?<DataFields data={runs.data}/>:<Empty title="No evaluation runs recorded">Run the evaluation pipeline and publish its results to inspect quality and baseline comparisons here.</Empty>}</section><section className="panel"><h3>Workspace telemetry</h3><p className="muted small">Actual API observations. Missing values mean they have not been recorded.</p>{analytics.loading?<Loading/>:analytics.error?<ErrorNotice message={analytics.error}/>:<DataFields data={analytics.data}/>}</section></div>}
type Job = {
  id: string;
  document_id: string;
  kind: string;
  status: string;
  attempts: number;
  created_at: number;
  error?: string;
};

export function Admin() {
  const resource = useResource<unknown>('/admin');
  const jobs = useResource<Job[]>('/ingestion-jobs');
  const collections = useResource<unknown[]>('/collections');
  const [error, setError] = useState('');
  const [jobError, setJobError] = useState('');
  const [jobNotice, setJobNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [jobAction, setJobAction] = useState<string>();

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setBusy(true);
    setError('');
    try {
      await api('/collections', {
        method: 'POST',
        body: JSON.stringify(Object.fromEntries(new FormData(form))),
      });
      collections.reload();
      form.reset();
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Could not create the collection.');
    } finally {
      setBusy(false);
    }
  }

  async function manageJob(id?: string) {
    if (jobAction) return;
    setJobAction(id ?? 'next');
    setJobNotice('');
    setJobError('');
    try {
      if (id) {
        await api(`/ingestion-jobs/${encodeURIComponent(id)}/retry`, { method: 'POST' });
        setJobNotice('Retry queued.');
      } else {
        const result = await api<{ job_id: string | null }>('/ingestion-jobs/run', { method: 'POST' });
        setJobNotice(result.job_id ? 'Job processed. Check the updated status below.' : 'No queued jobs are available.');
      }
      jobs.reload();
    } catch (error) {
      setJobError(error instanceof Error ? error.message : 'Could not update the job.');
    } finally {
      setJobAction(undefined);
    }
  }

  return (
    <div className="page-content">
      <div className="section-intro">
        <div><h2>Workspace administration</h2>
          <p>Review membership and audit events, organize collections, and recover failed jobs.</p></div>
        <button className="secondary" onClick={() => { resource.reload(); jobs.reload(); collections.reload(); }}>Refresh</button>
      </div>
      <section className="panel">
        <h3>System overview</h3>
        {resource.loading ? <Loading /> : resource.error ? <ErrorNotice message={resource.error} /> : <DataFields data={resource.data} />}
      </section>
      <section className="panel">
        <h3>Collections</h3>
        <form className="row" onSubmit={create}>
          <input aria-label="Collection name" name="name" placeholder="New collection name" required maxLength={100} />
          <button className="primary" disabled={busy}>Create collection</button>
        </form>
        {error && <ErrorNotice message={error} />}
        {collections.loading ? <Loading /> : collections.error ? <ErrorNotice message={collections.error} /> : <DataFields data={collections.data} />}
      </section>
      <section className="panel">
        <div className="section-intro"><h3>Ingestion jobs</h3>
          <button className="secondary" disabled={Boolean(jobAction)} onClick={() => manageJob()}>
            {jobAction === 'next' ? 'Processing…' : 'Process next job'}
          </button>
        </div>
        {jobNotice && <p role="status">{jobNotice}</p>}
        {jobError && <ErrorNotice message={jobError} />}
        {jobs.loading ? <Loading /> : jobs.error ? <ErrorNotice message={jobs.error} /> : jobs.data?.length ? (
          <div className="table-wrap"><table>
            <thead><tr><th>Job</th><th>Status</th><th>Attempts</th><th>Action</th></tr></thead>
            <tbody>{jobs.data.map(job => <tr key={job.id}>
              <td><strong>{job.kind}</strong><br /><small>{job.document_id}</small></td>
              <td><Badge>{job.status}</Badge>{job.error && <p className="error-text small">{job.error}</p>}</td>
              <td>{job.attempts}</td>
              <td>{job.status === 'failed' && <button className="text-button" disabled={Boolean(jobAction)} onClick={() => manageJob(job.id)}>
                {jobAction === job.id ? 'Queuing…' : 'Retry job'}
              </button>}</td>
            </tr>)}</tbody>
          </table></div>
        ) : <Empty title="No ingestion jobs">New uploads will appear here when they enter the queue.</Empty>}
      </section>
    </div>
  );
}

export function Settings({user}:{user:User}){const settings=useResource<unknown>('/settings');return <div className="page-content"><div className="section-intro"><div><h2>Workspace settings</h2><p>Active retrieval and provider configuration is managed on the server.</p></div></div><section className="panel"><h3>Account & security</h3><DataFields data={{name:user.name,email:user.email,role:user.role,workspace:user.workspace_id,session:'This tab only. Sign out to clear the access token.'}}/></section><section className="panel"><h3>Active configuration</h3>{settings.loading?<Loading/>:settings.error?<ErrorNotice message={settings.error}/>:<DataFields data={settings.data}/>}</section><section className="panel"><h3>Reading preference</h3><label className="row"><input type="checkbox" onChange={e=>document.documentElement.classList.toggle('comfortable',e.target.checked)}/> Larger reading text for this visit</label></section></div>}
