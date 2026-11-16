import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api.js';
import { PageHead, useSession } from '../App.jsx';
import { DOW, addDays, courseColors, fmtDay, fmtRange, iso, mondayOf, parseDay } from '../util.js';

const ranges = (rs) => rs.map((r) => fmtRange(r.start, r.end)).join(' and ');

function Changes({ diff }) {
  if (!diff?.previous_version) return null;
  const rows = [
    ...diff.moved.map((m) => ['Moved', 'info', m.label, `was ${ranges(m.was)} · now ${ranges(m.now)}`]),
    ...diff.added.map((m) => ['Added', 'ok', m.label, ranges(m.now)]),
    ...diff.removed.map((m) => ['Removed', 'err', m.label, `was ${ranges(m.was)}`]),
  ];
  return (
    <section className="card" aria-labelledby="ch">
      <h2 id="ch" style={{ fontSize: 16 }}>What changed since version {diff.previous_version}</h2>
      {rows.length === 0 ? <p className="muted" style={{ margin: 0 }}>Nothing moved. {diff.unchanged.length} tasks kept their days.</p> : (
        <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 8 }}>
          {rows.map(([kind, tone, label, text]) => (
            <li key={kind + label} className="row" style={{ gap: '4px 10px' }}><span className={`tag ${tone}`}>{kind}</span><span><strong>{label}</strong> · {text}</span></li>
          ))}
          {diff.unchanged.length > 0 && <li className="muted small">{diff.unchanged.length} other tasks kept their days.</li>}
        </ul>
      )}
    </section>
  );
}

export default function Plan() {
  const { term } = useSession();
  const [plan, setPlan] = useState(null);
  const [diff, setDiff] = useState(null);
  const [items, setItems] = useState([]);
  const [start, setStart] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    const [p, d, a] = await Promise.all([api.get('/plans/latest'), api.get('/plans/latest/diff'), api.get('/assessments?status=confirmed')]);
    setPlan(p); setDiff(d); setItems(a);
  }, []);
  useEffect(() => { load().catch((e) => setError(e.message)); }, [load]);
  useEffect(() => { if (term && !start) setStart(mondayOf(parseDay(term.today))); }, [term, start]);

  const generate = async () => {
    setBusy(true); setError('');
    try { await api.post(`/plans?trigger=${plan ? 'regenerated' : 'first plan'}`); await load(); } catch (e) { setError(e.message); }
    setBusy(false);
  };

  const byId = useMemo(() => Object.fromEntries(items.map((a) => [a.id, a])), [items]);
  const colors = useMemo(() => courseColors(items.map((a) => a.course_code)), [items]);
  if (!term || !start) return null;

  const days = Array.from({ length: 14 }, (_, i) => addDays(start, i));
  const s0 = iso(days[0]), s1 = iso(days[13]);
  const full = new Set(plan?.full_weekdays || []);
  const blocks = plan?.blocks || [];
  const rowIds = [...new Set([
    ...blocks.filter((b) => b.end_date >= s0 && b.start_date <= s1).map((b) => b.assessment_id),
    ...items.filter((a) => a.due_date >= s0 && a.due_date <= s1).map((a) => a.id),
  ])].filter((id) => byId[id]).sort((x, y) => byId[x].due_date.localeCompare(byId[y].due_date));
  const upcoming = blocks.filter((b) => b.end_date >= term.today);

  return (
    <>
      <header className="row between" style={{ alignItems: 'flex-end' }}>
        <PageHead step={5} title="Your study plan" />
        <div className="row">
          <button className="btn" type="button" onClick={generate} disabled={busy || items.length === 0}>{plan ? 'Regenerate plan' : 'Generate plan'}</button>
          {plan && <a className="btn primary" href="/api/v1/export.ics" download>Export to calendar (.ics)</a>}
        </div>
      </header>
      {error && <div className="alert error" role="alert">{error}</div>}
      {items.length === 0 && <div className="alert info">Confirm some deadlines first. <Link to="/review">Go to Review</Link>.</div>}
      {items.length > 0 && !plan && <div className="alert info">No plan yet. Generate one to spread preparation across your free days.</div>}
      {plan && (
        <div className="row muted">
          <span>Version {plan.version} · {plan.trigger}</span>
          {plan.is_valid
            ? <span className="tag ok">All checks passed</span>
            : <span className="tag err">Some checks failed</span>}
        </div>
      )}
      {plan?.validation_errors?.length > 0 && (
        <div className={`alert ${plan.is_valid ? 'info' : 'error'}`} role="status">
          {plan.validation_errors.map((e) => <div key={e}>{e}</div>)}
        </div>
      )}
      <Changes diff={diff} />
      {plan && (
        <section className="card" aria-labelledby="tl">
          <div className="row between">
            <div className="row" style={{ gap: 4 }}>
              <button className="btn" type="button" aria-label="Previous two weeks" onClick={() => setStart(addDays(start, -14))}>‹</button>
              <h2 id="tl" style={{ fontSize: 16, margin: '0 10px' }}>{fmtDay(s0)} – {fmtDay(s1)}</h2>
              <button className="btn" type="button" aria-label="Next two weeks" onClick={() => setStart(addDays(start, 14))}>›</button>
            </div>
            <div className="legend">
              <span><i className="dot" style={{ width: 14, borderRadius: 2, background: 'var(--full)' }} />Full day, no study</span>
              <span><i className="dot" style={{ width: 14, borderRadius: 2, background: 'var(--crunch-soft)', border: '1.5px solid var(--crunch-strong)' }} />Due date</span>
            </div>
          </div>
          <div className="scroll-x">
            <div className="gantt">
              <div className="g-row">
                <span />
                {days.map((d) => <div key={iso(d)} className={`g-head${full.has((d.getDay() + 6) % 7) ? ' full' : ''}`}><span>{DOW[(d.getDay() + 6) % 7]}</span><strong>{d.getDate()}</strong></div>)}
              </div>
              {rowIds.length === 0 && <p className="muted" style={{ margin: 8 }}>Nothing planned or due in these two weeks.</p>}
              {rowIds.map((id) => {
                const a = byId[id];
                const col = colors[a.course_code];
                return (
                  <div key={id} className="g-row">
                    <div className="g-label"><span className="small" style={{ fontWeight: 600, color: col.fg }}>{a.course_code}</span><span>{a.title}</span></div>
                    {days.map((d) => {
                      const k = iso(d);
                      const study = blocks.some((b) => b.assessment_id === id && b.start_date <= k && b.end_date >= k);
                      if (study) return <div key={k} className="g-cell" style={{ background: col.bg, border: `1.5px solid ${col.dot}`, color: col.fg }}>Study</div>;
                      if (a.due_date === k) return <div key={k} className="g-cell due">Due</div>;
                      return <div key={k} className={`g-cell${full.has((d.getDay() + 6) % 7) ? ' full' : ''}`} />;
                    })}
                  </div>
                );
              })}
            </div>
          </div>
        </section>
      )}
      {plan && (
        <section className="card" aria-labelledby="dl">
          <h2 id="dl" style={{ fontSize: 16 }}>Day by day</h2>
          {upcoming.length === 0 ? <p className="muted" style={{ margin: 0 }}>No upcoming study blocks.</p> : (
            <ul className="daylist" style={{ margin: 0, padding: 0, listStyle: 'none' }}>
              {upcoming.map((b) => (
                <li key={b.id}><span>{fmtRange(b.start_date, b.end_date)}</span><span>{b.task_label}</span></li>
              ))}
            </ul>
          )}
        </section>
      )}
    </>
  );
}
