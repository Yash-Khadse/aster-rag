'use client';

import { useEffect, useRef, useState } from 'react';
import {
  BookOpen, ChartNoAxesCombined, ChevronRight, CircleHelp, LogOut, Menu, MessageSquare,
  Search, Settings as SettingsIcon, Shield, X,
} from 'lucide-react';
import { api, ApiError, isAdmin, logout as endSession, type User } from '@/lib/api';
import { Auth } from '@/components/auth';
import { Chat } from '@/components/chat';
import { Library } from '@/components/library';
import { SearchExplorer } from '@/components/search';
import { Admin, Settings } from '@/components/dashboards';
import { EvaluationStudio } from '@/components/evaluations';
import { ErrorNotice, Loading } from '@/components/ui';
import { SourceDialog } from '@/components/source-dialog';

const navigation = [
  { id: 'chat', name: 'Ask Atlas', icon: MessageSquare },
  { id: 'library', name: 'Knowledge library', icon: BookOpen },
  { id: 'search', name: 'Search explorer', icon: Search },
  { id: 'evaluations', name: 'Evaluation studio', icon: ChartNoAxesCombined },
  { id: 'admin', name: 'Administration', icon: Shield },
  { id: 'settings', name: 'Settings', icon: SettingsIcon },
];

export default function Home() {
  const [user, setUser] = useState<User>();
  const [ready, setReady] = useState(false);
  const [page, setPage] = useState('chat');
  const [source, setSource] = useState<string>();
  const [menuOpen, setMenuOpen] = useState(false);
  const [sessionError, setSessionError] = useState('');
  const [sessionAttempt, setSessionAttempt] = useState(0);
  const mobileMenu = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const request = new AbortController();
    // The session is an HttpOnly cookie: ask the API who we are (also recovers the CSRF token).
    api<User>('/auth/me', { signal: request.signal }).then(currentUser => {
      if (!request.signal.aborted) setUser(currentUser);
    }).catch(error => {
      if (request.signal.aborted) return;
      if (!(error instanceof ApiError && (error.status === 401 || error.status === 403))) {
        setSessionError(error instanceof Error ? error.message : 'Could not verify your session.');
      }
    }).finally(() => {
      if (!request.signal.aborted) setReady(true);
    });
    return () => request.abort();
  }, [sessionAttempt]);

  useEffect(() => {
    function syncLocation() {
      const target = window.location.hash.slice(1);
      if (!target || navigation.some(item => item.id === target)) setPage(target || 'chat');
    }
    syncLocation();
    window.addEventListener('hashchange', syncLocation);
    return () => window.removeEventListener('hashchange', syncLocation);
  }, []);

  if (!ready) return <main className="boot"><Loading /></main>;
  if (sessionError) return <main className="boot"><section className="panel">
    <h1>Workspace connection interrupted</h1>
    <ErrorNotice message={sessionError} />
    <div className="row">
      <button className="primary" onClick={() => { setReady(false); setSessionError(''); setSessionAttempt(n => n + 1); }}>Retry connection</button>
      <button className="secondary" onClick={() => setSessionError('')}>Return to sign in</button>
    </div>
  </section></main>;
  if (!user) return <Auth onLogin={setUser} />;

  const links = navigation.filter(item => item.id !== 'admin' || isAdmin(user));
  const active = links.find(item => item.id === page) ?? links[0];

  function closeMenu() {
    mobileMenu.current?.close();
    setMenuOpen(false);
  }

  function navigate(target: string) {
    setPage(target);
    setSource(undefined);
    closeMenu();
  }

  function logout() {
    void endSession();
    setUser(undefined);
    setSource(undefined);
    setPage('chat');
    window.history.replaceState(null, '', window.location.pathname + window.location.search);
    closeMenu();
  }

  function sidebar(mobile: boolean) {
    return <>
      <div className="sidebar-top">
        <a href="#chat" className="brand" onClick={() => navigate('chat')} aria-label="Atlas workspace">
          <span className="brand-symbol" aria-hidden="true">A</span><span>Atlas</span>
        </a>
        {mobile && <button className="icon-button" aria-label="Close navigation" onClick={closeMenu}><X size={20} /></button>}
      </div>
      <div className="workspace">
        <span className="workspace-icon"><BookOpen size={17} aria-hidden="true" /></span>
        <div><strong>{user?.role === 'demo' ? 'Demo workspace' : 'Your workspace'}</strong><small>Knowledge base</small></div>
      </div>
      <nav aria-label="Main navigation">
        {links.map(item => <a key={item.id} href={`#${item.id}`} aria-current={active.id === item.id ? 'page' : undefined} onClick={() => navigate(item.id)}>
          <item.icon size={18} aria-hidden="true" /><span>{item.name}</span>
        </a>)}
      </nav>
      <div className="sidebar-note"><CircleHelp size={17} aria-hidden="true" /><p>Open a citation to verify an answer against its source.</p></div>
      <div className="user-profile">
        <span className="avatar" aria-hidden="true">{(user?.name || user?.email || 'U').slice(0, 1).toUpperCase()}</span>
        <div><strong>{user?.name || user?.email}</strong><small>{user?.role.replaceAll('_', ' ')}</small></div>
        <button className="icon-button" aria-label="Sign out" onClick={logout}><LogOut size={17} /></button>
      </div>
    </>;
  }

  return <div className="app-shell">
    <a href="#main-content" className="skip-link">Skip to content</a>
    <aside className="sidebar desktop-sidebar">{sidebar(false)}</aside>
    <dialog ref={mobileMenu} id="workspace-navigation" aria-label="Workspace navigation" className="sidebar mobile-drawer" onClose={() => setMenuOpen(false)}>
      {sidebar(true)}
    </dialog>
    <div className="main-shell">
      <header className="topbar">
        <div className="row">
          <button className="mobile-only icon-button" aria-label="Open navigation" aria-controls="workspace-navigation" aria-expanded={menuOpen}
            onClick={() => { mobileMenu.current?.showModal(); setMenuOpen(true); }}><Menu size={21} /></button>
          <span className="breadcrumb">Workspace <ChevronRight size={13} aria-hidden="true" /></span>
          <h1>{active.name}</h1>
        </div>
        <span className="workspace-badge"><Shield size={15} aria-hidden="true" /> Workspace scoped</span>
      </header>
      <main id="main-content" tabIndex={-1}>
        {active.id === 'chat' ? <Chat onSource={setSource} /> :
          active.id === 'library' ? <Library user={user} onSource={setSource} /> :
          active.id === 'search' ? <SearchExplorer onSource={setSource} /> :
          active.id === 'evaluations' ? <EvaluationStudio user={user} /> :
          active.id === 'admin' ? <Admin /> : <Settings user={user} />}
      </main>
    </div>
    {source && <SourceDialog key={source} id={source} user={user} onClose={() => setSource(undefined)} />}
  </div>;
}
