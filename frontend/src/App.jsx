import { createContext, useContext, useEffect, useState } from 'react';
import { Navigate, NavLink, Route, Routes } from 'react-router-dom';
import { api } from './api.js';
import Login from './pages/Login.jsx';
import Hours from './pages/Hours.jsx';
import Upload from './pages/Upload.jsx';
import Review from './pages/Review.jsx';
import Calendar from './pages/Calendar.jsx';
import Plan from './pages/Plan.jsx';

const SessionCtx = createContext(null);
export const useSession = () => useContext(SessionCtx);

const STEPS = [
  ['/hours', 'Reserved hours'],
  ['/upload', 'Upload outlines'],
  ['/review', 'Review'],
  ['/calendar', 'Calendar'],
  ['/plan', 'Study plan'],
];

function Layout({ children }) {
  const { user, term, signOut } = useSession();
  return (
    <div className="shell">
      <nav className="nav" aria-label="Main">
        <div className="brand"><span className="brand-mark" aria-hidden="true">A</span>Akedu</div>
        <div className="nav-links">
          {STEPS.map(([to, label], i) => (
            <NavLink key={to} to={to} className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
              <span className="num">{i + 1}</span>{label}
            </NavLink>
          ))}
        </div>
        <div className="nav-foot">
          {term ? `${term.name}` : ''}<br />
          {user.email}<br />
          <button type="button" className="link-btn" onClick={signOut}>Sign out</button>
        </div>
      </nav>
      <main className="main">{children}</main>
    </div>
  );
}

export default function App() {
  const [user, setUser] = useState(undefined);
  const [term, setTerm] = useState(null);

  useEffect(() => {
    api.get('/auth/me').then(setUser).catch(() => setUser(null));
  }, []);
  useEffect(() => {
    if (user) api.get('/term').then(setTerm).catch(() => {});
  }, [user]);

  const signOut = async () => {
    await api.post('/auth/logout');
    setUser(null);
  };

  if (user === undefined) return null;
  if (!user) return <Login onSignedIn={setUser} />;

  return (
    <SessionCtx.Provider value={{ user, term, signOut }}>
      <Layout>
        <Routes>
          <Route path="/hours" element={<Hours />} />
          <Route path="/upload" element={<Upload />} />
          <Route path="/review" element={<Review />} />
          <Route path="/calendar" element={<Calendar />} />
          <Route path="/plan" element={<Plan />} />
          <Route path="*" element={<Navigate to="/hours" replace />} />
        </Routes>
      </Layout>
    </SessionCtx.Provider>
  );
}

export function PageHead({ step, title, children }) {
  return (
    <header className="page-head">
      <span className="eyebrow">Step {step} of 5</span>
      <h1>{title}</h1>
      {children && <p className="lead">{children}</p>}
    </header>
  );
}
