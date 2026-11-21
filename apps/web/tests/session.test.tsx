import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import Home from '../src/app/page';

afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
  localStorage.clear();
  history.replaceState(null, '', '/');
});

it('recovers the session via /auth/me with the cookie; an outage keeps UI state and reconnects', async () => {
  history.replaceState(null, '', '/#library');
  const fetch = vi.fn()
    .mockResolvedValueOnce(new Response('{"detail":"API temporarily unavailable"}', { status: 503 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({
      id: 'member', name: 'Avery', email: 'avery@example.com', role: 'member',
      organization_id: 'organization', workspace_id: 'workspace', csrf_token: 'csrf-1',
    })))
    .mockImplementation(() => Promise.resolve(new Response('[]')));
  vi.stubGlobal('fetch', fetch);
  render(<Home />);
  const retry = await screen.findByRole('button', { name: 'Retry connection' });
  expect(location.hash).toBe('#library');
  fireEvent.click(retry);
  expect(await screen.findByRole('heading', { name: 'Knowledge library' })).toBeVisible();
  expect(fetch.mock.calls[1][0]).toMatch(/\/auth\/me$/);
  expect(fetch.mock.calls[1][1].credentials).toBe('include');
  expect(fetch.mock.calls[1][1].headers.get('Authorization')).toBeNull();
  expect(sessionStorage.length + localStorage.length).toBe(0);
});
