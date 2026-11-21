'use client';

import { useEffect, useRef, useState, type FormEvent } from 'react';
import Link from 'next/link';
import { ArrowRight, ArrowUpRight, BookOpen, Eye, EyeOff, FileText, Shield } from 'lucide-react';
import { api, ApiError, type User } from '@/lib/api';
import { ErrorNotice } from './ui';

export function Auth({ onLogin }: { onLogin: (user: User) => void }) {
  const [register, setRegister] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [verify, setVerify] = useState<{ email: string } | null>(null);
  const [resent, setResent] = useState(false);
  const pending = useRef(false);
  const verifying = useRef(false);

  async function login(path: string, body?: Record<string, string>, fromLink = false) {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setError('');
    try {
      // The session cookie is HttpOnly; the access_token in the body is intentionally ignored.
      const result = await api<{ user?: User; verification_required?: boolean }>(path, {
        method: 'POST',
        body: body ? JSON.stringify(body) : undefined,
      });
      if (result.verification_required || !result.user) setVerify({ email: body?.email ?? '' });
      else onLogin(result.user);
    } catch (error) {
      if (fromLink) {
        setVerify({ email: '' });
        setError('This verification link is invalid or has expired. Enter your email to get a new one.');
      } else if (error instanceof ApiError && error.status === 403 && error.message === 'email_not_verified') {
        setVerify({ email: body?.email ?? '' });
      } else {
        setError(error instanceof Error ? error.message : 'Could not connect to Atlas.');
      }
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }

  useEffect(() => {
    const url = new URL(window.location.href);
    const token = url.searchParams.get('verify');
    if (!token || verifying.current) return;
    verifying.current = true;
    url.searchParams.delete('verify');
    window.history.replaceState(null, '', url.pathname + url.search + url.hash);
    void login('/auth/verify-email', { token }, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function resend(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      await api('/auth/resend-verification', { method: 'POST', body: JSON.stringify({ email: new FormData(event.currentTarget).get('email') }) });
      setResent(true);
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Could not connect to Atlas.');
    } finally {
      setBusy(false);
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void login(`/auth/${register ? 'register' : 'login'}`, Object.fromEntries(new FormData(event.currentTarget)) as Record<string, string>);
  }

  return (
    <main className="auth">
      <section className="auth-story" aria-label="About Atlas">
        <Link className="brand" href="/" aria-label="Atlas home"><span className="brand-symbol" aria-hidden="true">A</span><span>Atlas</span></Link>
        <div className="auth-story-body">
          <h1>Find the answer.<br />Follow the source.</h1>
          <p>Search your organization’s documents and read the evidence behind every answer.</p>
          <figure className="auth-example">
            <figcaption><BookOpen size={16} /> Example workspace</figcaption>
            <div className="auth-example-query">How do I request time off?</div>
            <div className="auth-example-answer">Start with the leave policy for the approval steps.<span className="citation-number">1</span></div>
            <div className="auth-example-source"><FileText size={18} /><span>Leave policy</span><span className="citation-number">1</span></div>
          </figure>
        </div>
        <p className="auth-story-note"><Shield size={16} /> Access follows your workspace permissions</p>
      </section>
      <section className="auth-form" aria-labelledby="sign-in-title">
        <div className="auth-form-inner">
          <h2 id="sign-in-title">{verify ? 'Check your email to verify your account' : register ? 'Create your workspace' : 'Sign in to Atlas'}</h2>
          <p>{verify ? 'We sent a verification link. Open it to finish signing in.' : register ? 'Set up a workspace for your organization.' : 'Continue to your organization’s knowledge base.'}</p>
          {error && <ErrorNotice message={error} />}
          {verify ? <>
            <form onSubmit={resend}>
              <fieldset disabled={busy}>
                <legend className="sr-only">Resend verification email</legend>
                <label>Email address<input name="email" type="email" required autoComplete="email" defaultValue={verify.email} /></label>
                <button className="secondary wide">Resend verification email</button>
              </fieldset>
            </form>
            {resent && <p role="status">If that address has an account awaiting verification, we sent a new link.</p>}
            <button className="text-button auth-switch" disabled={busy} onClick={() => { setVerify(null); setResent(false); setError(''); setRegister(false); }}>Back to sign in</button>
          </> : <>
          <form onSubmit={submit}>
            <fieldset disabled={busy}>
              <legend className="sr-only">{register ? 'Registration details' : 'Sign-in details'}</legend>
              {register && <>
                <label>Your name<input name="name" required autoComplete="name" /></label>
                <label>Organization<input name="organization_name" required autoComplete="organization" /></label>
              </>}
              <label>Email address<input name="email" type="email" required autoComplete="email" placeholder="you@company.com" /></label>
              <div className="password-control">
                <label>Password<input name="password" type={showPassword ? 'text' : 'password'} required minLength={register ? 12 : 1} autoComplete={register ? 'new-password' : 'current-password'} /></label>
                <button className="icon-button" type="button" aria-label={showPassword ? 'Hide password' : 'Show password'} aria-pressed={showPassword} onClick={() => setShowPassword(value => !value)}>
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
              {register && <p className="small">Use at least 12 characters.</p>}
              <button className="primary wide" disabled={busy}>{busy ? 'Connecting…' : register ? 'Create workspace' : 'Sign in'}<ArrowRight size={18} /></button>
            </fieldset>
          </form>
          <button className="text-button auth-switch" disabled={busy} onClick={() => { setRegister(!register); setError(''); }}>
            {register ? 'Already have an account? Sign in' : 'New here? Create a workspace'}
          </button>
          <div className="auth-demo">
            <div><strong>Take a look around</strong><p>Explore a workspace with fictional documents.</p></div>
            <button className="secondary" disabled={busy} onClick={() => login('/auth/demo')}>Explore demo workspace <ArrowUpRight size={17} /></button>
          </div>
          </>}
        </div>
      </section>
    </main>
  );
}
