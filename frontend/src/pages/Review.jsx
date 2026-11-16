import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api.js';
import { PageHead } from '../App.jsx';
import { fmtDay, pct } from '../util.js';

const TYPES = ['assignment', 'quiz', 'midterm', 'final', 'project', 'presentation', 'lab', 'other'];
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);

function Row({ a, onChange, onError }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({});
  const start = () => { setDraft({ title: a.title, type: a.type, due_date: a.due_date || '', weight_percent: a.weight_percent ?? '' }); setEditing(true); };

  const patch = async (body) => {
    try { onChange(await api.patch(`/assessments/${a.id}`, body)); return true; } catch (e) { onError(e.message); return false; }
  };
  const save = async () => {
    const body = { title: draft.title, type: draft.type, due_date: draft.due_date || null,
      weight_percent: draft.weight_percent === '' ? null : Number(draft.weight_percent) };
    if (await patch(body)) setEditing(false);
  };
  const confirmed = a.status === 'confirmed';

  return (
    <div className={`rv-grid rv-row${a.review_note && !confirmed ? ' flag' : ''}`}>
      <input type="checkbox" className="chk" checked={confirmed} aria-label={`Confirm ${a.title}`}
        onChange={() => patch({ status: confirmed ? 'extracted' : 'confirmed' })} />
      {editing ? (
        <>
          <input className="input sm" aria-label="Title" value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
          <select className="input sm" aria-label="Type" value={draft.type} onChange={(e) => setDraft({ ...draft, type: e.target.value })}>
            {TYPES.map((t) => <option key={t} value={t}>{cap(t)}</option>)}
          </select>
          <input className="input sm" type="date" aria-label="Due date" value={draft.due_date} onChange={(e) => setDraft({ ...draft, due_date: e.target.value })} />
          <input className="input sm" type="number" min="0" max="100" step="0.5" aria-label="Weight percent" value={draft.weight_percent} onChange={(e) => setDraft({ ...draft, weight_percent: e.target.value })} />
        </>
      ) : (
        <>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <strong style={{ lineHeight: 1.35 }}>{a.title}</strong>
            {a.review_note && !confirmed && <span className="note">{a.review_note}</span>}
          </div>
          <span>{cap(a.type)}</span>
          <span>{fmtDay(a.due_date)}</span>
          <span>{pct(a.weight_percent)}</span>
        </>
      )}
      <span className="excerpt">{a.source_excerpt ? `"${a.source_excerpt}"` : ''}{a.source_page ? ` · p. ${a.source_page}` : ''}</span>
      <div className="row" style={{ gap: 0, paddingTop: 0 }}>
        {editing ? (
          <><button className="btn ghost" type="button" onClick={save}>Save</button>
            <button className="btn ghost" type="button" onClick={() => setEditing(false)}>Cancel</button></>
        ) : (
          <><button className="btn ghost" type="button" onClick={start} aria-label={`Edit ${a.title}`}>Edit</button>
            <button className="btn danger" type="button" aria-label={`Delete ${a.title}`}
              onClick={async () => { await api.del(`/assessments/${a.id}`); onChange(null, a.id); }}>Delete</button></>
        )}
      </div>
    </div>
  );
}

function AddForm({ courses, onAdded, onError }) {
  const [open, setOpen] = useState(false);
  const blank = { course_code: courses[0] || '', title: '', type: 'assignment', due_date: '', weight_percent: '' };
  const [f, setF] = useState(blank);
  if (!open) return <button className="btn" type="button" style={{ alignSelf: 'flex-start' }} onClick={() => { setF(blank); setOpen(true); }}>Add an item manually</button>;
  const submit = async (e) => {
    e.preventDefault();
    try {
      onAdded(await api.post('/assessments', { ...f, weight_percent: f.weight_percent === '' ? null : Number(f.weight_percent) }));
      setOpen(false);
    } catch (err) { onError(err.message); }
  };
  return (
    <form onSubmit={submit} className="row" style={{ alignItems: 'flex-end', borderTop: '1px solid var(--border)', paddingTop: 16 }}>
      <div className="field"><label htmlFor="ac">Course code</label>
        <input id="ac" className="input" list="codes" required value={f.course_code} onChange={(e) => setF({ ...f, course_code: e.target.value })} placeholder="SOEN 6841" />
        <datalist id="codes">{courses.map((c) => <option key={c} value={c} />)}</datalist></div>
      <div className="field" style={{ flex: '2 1 200px' }}><label htmlFor="at">Title</label>
        <input id="at" className="input" required value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></div>
      <div className="field"><label htmlFor="aty">Type</label>
        <select id="aty" className="input" value={f.type} onChange={(e) => setF({ ...f, type: e.target.value })}>{TYPES.map((t) => <option key={t} value={t}>{cap(t)}</option>)}</select></div>
      <div className="field"><label htmlFor="ad">Due date</label>
        <input id="ad" className="input" type="date" required value={f.due_date} onChange={(e) => setF({ ...f, due_date: e.target.value })} /></div>
      <div className="field" style={{ flex: '0 1 110px' }}><label htmlFor="aw">Weight %</label>
        <input id="aw" className="input" type="number" min="0" max="100" step="0.5" value={f.weight_percent} onChange={(e) => setF({ ...f, weight_percent: e.target.value })} /></div>
      <button className="btn primary" type="submit">Add</button>
      <button className="btn" type="button" onClick={() => setOpen(false)}>Cancel</button>
    </form>
  );
}

export default function Review() {
  const [items, setItems] = useState([]);
  const [course, setCourse] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => { api.get('/assessments').then(setItems).catch((e) => setError(e.message)); }, []);

  const codes = useMemo(() => [...new Set(items.map((a) => a.course_code))].sort(), [items]);
  const active = course && codes.includes(course) ? course : codes[0];
  const shown = items.filter((a) => a.course_code === active);
  const flagged = shown.filter((a) => a.review_note && a.status !== 'confirmed').length;
  const confirmedCount = items.filter((a) => a.status === 'confirmed').length;

  const onChange = (updated, removedId) => {
    setError('');
    setItems((xs) => (updated ? xs.map((x) => (x.id === updated.id ? updated : x)) : xs.filter((x) => x.id !== removedId)));
  };
  const confirmCourse = async () => {
    const ids = shown.filter((a) => a.status !== 'confirmed' && a.due_date).map((a) => a.id);
    if (!ids.length) return;
    try {
      const done = await api.post('/assessments/confirm', { ids });
      setItems((xs) => xs.map((x) => done.find((d) => d.id === x.id) || x));
    } catch (e) { setError(e.message); }
  };

  return (
    <>
      <PageHead step={3} title="Check what we found">
        Confirm each item before it reaches your calendar. Nothing is flagged or planned from an unconfirmed item. Highlighted rows need a closer look.
      </PageHead>
      {error && <div className="alert error" role="alert">{error}</div>}
      {codes.length > 0 && (
        <div className="pills" role="group" aria-label="Courses">
          {codes.map((c) => {
            const n = items.filter((a) => a.course_code === c);
            return <button key={c} type="button" className="pill" aria-pressed={c === active} onClick={() => setCourse(c)}>
              {c} · {n.filter((a) => a.status === 'confirmed').length}/{n.length} confirmed</button>;
          })}
        </div>
      )}
      <section className="card" aria-labelledby="it">
        <div className="row between">
          <h2 id="it">{active || 'No items yet'}</h2>
          {flagged > 0 && <span className="tag warn">{flagged} need a closer look</span>}
        </div>
        {codes.length === 0 && <p className="muted" style={{ margin: 0 }}>Upload an outline, or add deadlines manually.</p>}
        {shown.length > 0 && (
          <div className="scroll-x">
            <div style={{ minWidth: 960 }}>
              <div className="rv-grid rv-head"><span>Confirm</span><span>Assessment</span><span>Type</span><span>Due</span><span>Weight</span><span>From the outline</span><span /></div>
              {shown.map((a) => <Row key={a.id} a={a} onChange={onChange} onError={setError} />)}
            </div>
          </div>
        )}
        <div className="row between">
          <AddForm courses={codes} onError={setError} onAdded={(a) => { setItems((xs) => [...xs, a]); setCourse(a.course_code); }} />
          {shown.some((a) => a.status !== 'confirmed') && <button className="btn" type="button" onClick={confirmCourse}>Confirm all dated items in {active}</button>}
        </div>
      </section>
      <div className="row between">
        <span className="muted">{confirmedCount} of {items.length} items confirmed</span>
        <Link className="btn primary" to="/calendar">View calendar</Link>
      </div>
    </>
  );
}
