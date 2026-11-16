import { useState } from 'react';
import { api } from '../api.js';

export default function Login({ onSignedIn }) {
  const [mode, setMode] = useState('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      onSignedIn(await api.post(mode === 'login' ? '/auth/login' : '/auth/register', { email, password }));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login">
      <form className="card" onSubmit={submit}>
        <div className="brand" style={{ padding: 0 }}><span className="brand-mark" aria-hidden="true">A</span>Akedu</div>
        <h1 style={{ fontSize: 26 }}>{mode === 'login' ? 'Sign in' : 'Create an account'}</h1>
        <p className="muted" style={{ margin: 0 }}>Turn your course outlines into one semester plan.</p>
        {error && <div className="alert error" role="alert">{error}</div>}
        <div className="field">
          <label htmlFor="email">Email</label>
          <input id="email" className="input" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="password">Password</label>
          <input id="password" className="input" type="password" minLength={6} required autoComplete={mode === 'login' ? 'current-password' : 'new-password'} value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>
        <button className="btn primary" type="submit" disabled={busy}>{mode === 'login' ? 'Sign in' : 'Create account'}</button>
        <button type="button" className="link-btn" onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(''); }}>
          {mode === 'login' ? 'New here? Create an account' : 'Already have an account? Sign in'}
        </button>
        <p className="muted small" style={{ margin: 0 }}>Pilot demo account: demo@akedu.app / akedu-demo</p>
      </form>
    </div>
  );
}
