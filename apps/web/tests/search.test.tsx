import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { SearchExplorer } from '../src/components/search';

afterEach(() => vi.unstubAllGlobals());

it('shows completed methods and leaves unstarted methods alone after cancellation', async () => {
  const fetch = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ evidence: [{
      id: 'chunk-1', document_id: 'doc-1', title: 'Leave policy', text: 'Annual leave is 20 days.',
    }] })))
    .mockImplementationOnce((_url: string, options: RequestInit) => new Promise((_, reject) => {
      options.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
    }));
  vi.stubGlobal('fetch', fetch);
  render(<SearchExplorer onSource={() => {}} />);
  fireEvent.change(screen.getByRole('textbox', { name: 'Search query' }), { target: { value: 'annual leave' } });
  fireEvent.click(screen.getByRole('button', { name: 'Compare retrieval' }));

  expect(await screen.findByText('Annual leave is 20 days.')).toBeVisible();
  expect(screen.getByRole('status')).toHaveTextContent('1 of 4 methods finished.');
  fireEvent.click(screen.getByRole('button', { name: 'Stop comparison' }));

  expect(await screen.findByRole('button', { name: 'Compare retrieval' })).toBeEnabled();
  expect(screen.getByRole('status')).toHaveTextContent('Comparison stopped.');
  expect(screen.getByText('Annual leave is 20 days.')).toBeVisible();
  expect(fetch).toHaveBeenCalledTimes(2);
});
