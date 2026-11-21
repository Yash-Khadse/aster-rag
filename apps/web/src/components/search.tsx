'use client';

import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Search as SearchIcon } from 'lucide-react';
import { api, type Evidence } from '@/lib/api';
import { DataFields, Empty, ErrorNotice, EvidenceCard } from './ui';

type Result = {
  evidence?: Evidence[];
  results?: Evidence[];
  timings?: Record<string, unknown>;
  reranker_status?: string;
};
type Outcome = Result | { error: string };

const strategies = [
  { key: 'dense', name: 'Semantic', description: 'Meaning and related concepts', rerank: false },
  { key: 'bm25', name: 'Keyword', description: 'Exact terms and identifiers', rerank: false },
  { key: 'hybrid', name: 'Hybrid', description: 'Reciprocal rank fusion', rerank: false },
  { key: 'hybrid', name: 'Reranked', description: 'Cross-encoder relevance', rerank: true },
];

export function SearchExplorer({ onSource }: { onSource: (id: string) => void }) {
  const [query, setQuery] = useState('');
  const [topK, setTopK] = useState(5);
  const [results, setResults] = useState<Outcome[]>([]);
  const [busy, setBusy] = useState(false);
  const [cancelled, setCancelled] = useState(false);
  const request = useRef<AbortController | null>(null);

  useEffect(() => () => request.current?.abort(), []);

  async function search(event: FormEvent) {
    event.preventDefault();
    const submittedQuery = query.trim();
    if (!submittedQuery || request.current) return;

    const controller = new AbortController();
    request.current = controller;
    setBusy(true);
    setCancelled(false);
    setResults([]);
    try {
      // Run serially so the comparison stays within the API's request limits.
      for (const strategy of strategies) {
        let outcome: Outcome;
        try {
          outcome = await api<Result>('/search', {
            method: 'POST',
            body: JSON.stringify({
              query: submittedQuery,
              strategy: strategy.key,
              rerank: strategy.rerank,
              top_k: topK,
            }),
            signal: controller.signal,
          });
        } catch (error) {
          outcome = { error: error instanceof Error ? error.message : 'Search failed.' };
        }
        if (controller.signal.aborted) break;
        setResults(previous => [...previous, outcome]);
      }
    } finally {
      request.current = null;
      setBusy(false);
    }
  }

  function cancel() {
    request.current?.abort();
    setCancelled(true);
  }

  return (
    <div className="page-content">
      <div className="section-intro">
        <div>
          
          <h2>Compare retrieval methods</h2>
          <p>See which source excerpts each method finds for the same question.</p>
        </div>
      </div>
      <form className="search-form" onSubmit={search}>
        <SearchIcon size={20} aria-hidden="true" />
        <input
          aria-label="Search query" required maxLength={4000} value={query}
          onChange={event => setQuery(event.target.value)} placeholder="Search your workspace knowledge…"
        />
        <label className="small">
          Results per method
          <select value={topK} onChange={event => setTopK(Number(event.target.value))}>
            {[3, 5, 10].map(count => <option key={count}>{count}</option>)}
          </select>
        </label>
        <button className="primary" disabled={busy || !query.trim()}>
          {busy ? 'Comparing…' : 'Compare retrieval'}
        </button>
        {busy && <button className="secondary" type="button" onClick={cancel}>Stop comparison</button>}
      </form>
      {(busy || cancelled) && <p role="status" className="small muted">
        {cancelled ? 'Comparison stopped.' : `${results.length} of ${strategies.length} methods finished.`}
      </p>}
      <div className="comparison">
        {strategies.map((strategy, index) => {
          const result = results[index];
          return (
            <section key={strategy.name} className="comparison-column">
              <header>
                
                <h3>{strategy.name}</h3>
                <p>{strategy.description}</p>
              </header>
              {result ? <ComparisonResult result={result} onSource={onSource} /> :
                <p className="comparison-placeholder">
                  {cancelled ? 'Comparison stopped.' : busy ? 'Waiting for results…' : 'Run a query to inspect ranked evidence.'}
                </p>}
            </section>
          );
        })}
      </div>
      <p className="small muted">Each method uses its own scoring scale.</p>
    </div>
  );
}

function ComparisonResult({ result, onSource }: { result: Outcome; onSource: (id: string) => void }) {
  if ('error' in result) return <ErrorNotice message={result.error} />;
  const evidence = result.evidence ?? result.results ?? [];
  return (
    <>
      {result.reranker_status && <p className="small muted">{result.reranker_status === "cross_encoder" ? "Cross-encoder applied" : result.reranker_status.replaceAll("_", " ")}</p>}
      <div className="timings"><DataFields data={result.timings} /></div>
      {evidence.map((item, index) => (
        <div key={item.id ?? index}>
          <EvidenceCard item={item} index={index} onOpen={onSource} />
          {item.score !== undefined && <p className="small muted">Score: {item.score.toFixed(5)}</p>}
        </div>
      ))}
      {!evidence.length && <Empty title="No matching evidence">
        Try different wording or inspect the document library.
      </Empty>}
    </>
  );
}
