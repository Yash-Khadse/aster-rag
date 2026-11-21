import {afterEach,describe,expect,it,vi} from 'vitest';
import {api,ApiError,logout,parseEvent,streamChat,canManage,isAdmin,type User} from '../src/lib/api';
afterEach(()=>{vi.unstubAllGlobals();sessionStorage.clear();localStorage.clear()});

it('reports the HTTP status when the server returns a null error payload', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('null', {status: 503})));
  await expect(api('/auth/me')).rejects.toEqual(new ApiError(503, 'Request failed (503).'));
});

it('preserves the HTTP status and displays structured validation messages', async () => {
  const response = new Response(JSON.stringify({detail: [{msg: 'Enter a valid email address'}]}), {status: 422});
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));
  await expect(api('/auth/register')).rejects.toEqual(new ApiError(422, 'Enter a valid email address'));
});

it('delivers progress before the result when an SSE separator spans chunks', async () => {
  const encoder = new TextEncoder();
  let writer!: ReadableStreamDefaultController<Uint8Array>;
  const body = new ReadableStream<Uint8Array>({start(controller){writer = controller;}});
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body)));
  let showProgress!: (value: string) => void;
  const progress = new Promise<string>(resolve => { showProgress = resolve; });
  const result = streamChat({}, showProgress, new AbortController().signal);
  writer.enqueue(encoder.encode('event: status\r\ndata: "Searching"\r\n\r'));
  writer.enqueue(encoder.encode('\n'));
  expect(await progress).toBe('Searching');
  writer.enqueue(encoder.encode('event: result\r\ndata: {"answer":"Grounded"}\r\n\r\n'));
  writer.close();
  expect(await result).toEqual({answer:'Grounded'});
});
describe('API transport',()=>{it('parses SSE result data and CRLF',()=>{expect(parseEvent('event: result\r\ndata: {"answer":"Grounded"}\r\n')).toEqual({event:'result',data:{answer:'Grounded'}})});it('sends cookies and a CSRF token only on unsafe requests, never storing tokens',async()=>{const fetch=vi.fn().mockImplementation(()=>Promise.resolve(new Response('{"csrf_token":"csrf-9","access_token":"ignored"}')));vi.stubGlobal('fetch',fetch);await api('/auth/me');await api('/documents');await api('/documents',{method:'POST',body:new FormData()});await api('/chat/sessions/1',{method:'DELETE'});fetch.mockImplementation(()=>Promise.resolve(new Response(new ReadableStream({start(c){c.enqueue(new TextEncoder().encode('event: result\ndata: {"answer":"a"}\n\n'));c.close()}}))));await streamChat({},()=>{},new AbortController().signal);const calls=fetch.mock.calls.map(c=>c[1]);calls.forEach(c=>{expect(c.credentials).toBe('include');expect(c.headers.get('Authorization')).toBeNull()});expect(calls[0].headers.get('X-CSRF-Token')).toBeNull();expect(calls[1].headers.get('X-CSRF-Token')).toBeNull();expect(calls.slice(2).map(c=>c.headers.get('X-CSRF-Token'))).toEqual(['csrf-9','csrf-9','csrf-9']);expect(sessionStorage.length+localStorage.length).toBe(0)});it('forgets the CSRF token on logout and 401',async()=>{const fetch=vi.fn().mockImplementation(()=>Promise.resolve(new Response('{"csrf_token":"csrf-1"}')));vi.stubGlobal('fetch',fetch);await api('/auth/me');fetch.mockImplementationOnce(()=>Promise.resolve(new Response(null,{status:204})));await logout();await api('/documents',{method:'POST'});expect(fetch.mock.calls[1][1].headers.get('X-CSRF-Token')).toBe('csrf-1');expect(fetch.mock.calls[2][1].headers.get('X-CSRF-Token')).toBeNull();await api('/auth/me');fetch.mockImplementationOnce(()=>Promise.resolve(new Response('{}',{status:401})));await expect(api('/documents')).rejects.toBeInstanceOf(ApiError);await api('/documents',{method:'POST'});expect(fetch.mock.calls.at(-1)![1].headers.get('X-CSRF-Token')).toBeNull()});it('surfaces API authorization errors without content fallback',async()=>{vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('{"detail":"Access denied"}',{status:403})));await expect(api('/documents')).rejects.toThrow('Access denied')});it('does not grant demo visitors management access',()=>{const user={role:'demo'} as User;expect(canManage(user)).toBe(false);expect(isAdmin(user)).toBe(false)});});
