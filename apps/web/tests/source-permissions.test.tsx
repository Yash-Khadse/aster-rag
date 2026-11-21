import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { SourcePermissions } from '../src/components/source-permissions';

afterEach(() => vi.unstubAllGlobals());

it('saves restricted access selections with the existing collection', async () => {
  const fetch = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({
      members: [{ id: 'member-1', name: 'Avery' }],
      groups: [{ id: 'group-1', name: 'Support' }],
      collections: [{ id: 'collection-1', name: 'Handbook' }],
    })))
    .mockResolvedValueOnce(new Response('{}'));
  vi.stubGlobal('fetch', fetch);
  const onSaved = vi.fn();
  render(<SourcePermissions id="doc-1" document={{
    access_scope: 'restricted', collection_id: 'collection-1', allowed_groups: ['group-1'],
  }} onSaved={onSaved} />);

  fireEvent.click(await screen.findByRole('checkbox', { name: 'Avery' }));
  expect(screen.getByRole('checkbox', { name: 'Support' })).toBeChecked();
  fireEvent.click(screen.getByRole('button', { name: 'Save access' }));
  await waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
  expect(fetch.mock.calls[1][0]).toMatch(/\/documents\/doc-1\/permissions$/);
  expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({
    access_scope: 'restricted', allowed_users: ['member-1'], allowed_groups: ['group-1'],
    collection_id: 'collection-1',
  });
});
