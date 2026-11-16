import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api.js';
import { PageHead, useSession } from '../App.jsx';
import { DOW, addDays, courseColors, fmtDay, iso, mondayOf, monthName, parseDay, pct } from '../util.js';

function CrunchCard({ p, byId, colors }) {
  return (
    <section className="crunch" aria-label={`Crunch period ${fmtDay(p.start)} to ${fmtDay(p.end)}`}>
      <div style={{ flex: '999 1 420px', display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div className="row" style={{ gap: 10 }}>
          <svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#A33A0B" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3l10 18H2z" /><path d="M12 10v5" /><path d="M12 18h.01" /></svg>
          <h2>Crunch period · {fmtDay(p.start)}{p.start !== p.end ? ` – ${fmtDay(p.end)}` : ''}</h2>
        </div>
        <p style={{ margin: 0 }}>{p.count} {p.count === 1 ? 'assessment' : 'assessments'} worth {+p.total_weight}% combined weight.</p>
        <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 6 }}>
          {p.assessment_ids.map((id) => {
            const a = byId[id];
            if (!a) return null;
            return <li key={id}><strong style={{ color: colors[a.course_code]?.fg }}>{a.course_code}</strong> {a.title} · {fmtDay(a.due_date)} · {pct(a.weight_percent)}</li>;
          })}
        </ul>
        <p className="small" style={{ margin: 0 }}>Why flagged: {p.reasons.join('; ')}.</p>
      </div>
      <Link className="btn primary" to="/plan">See how to prepare</Link>
    </section>
  );
}

export default function Calendar() {
  const { term } = useSession();
  const [items, setItems] = useState([]);
  const [crunch, setCrunch] = useState([]);
  const [plan, setPlan] = useState(null);
  const [month, setMonth] = useState(null);
  const [showBlocks, setShowBlocks] = useState(true);

  useEffect(() => {
    api.get('/assessments?status=confirmed').then(setItems);
    api.get('/crunch').then(setCrunch);
    api.get('/plans/latest').then(setPlan);
  }, []);
  useEffect(() => {
    if (term && !month) { const t = parseDay(term.today); setMonth(new Date(t.getFullYear(), t.getMonth(), 1)); }
  }, [term, month]);

  const colors = useMemo(() => courseColors(items.map((a) => a.course_code)), [items]);
  const byId = useMemo(() => Object.fromEntries(items.map((a) => [a.id, a])), [items]);
  const hotDays = useMemo(() => {
    const s = new Set();
    crunch.forEach((p) => { for (let d = parseDay(p.start); d <= parseDay(p.end); d = addDays(d, 1)) s.add(iso(d)); });
    return s;
  }, [crunch]);

  if (!term || !month) return null;

  // weekly load strip across the term
  const weeks = [];
  for (let w = mondayOf(parseDay(term.start_date)); w <= parseDay(term.end_date); w = addDays(w, 7)) {
    const end = addDays(w, 6);
    const inWeek = items.filter((a) => a.due_date && parseDay(a.due_date) >= w && parseDay(a.due_date) <= end);
    const hot = crunch.some((p) => parseDay(p.start) <= end && parseDay(p.end) >= w);
    weeks.push({ start: w, weight: inWeek.reduce((t, a) => t + (a.weight_percent || 0), 0), hot });
  }
  const maxW = Math.max(30, ...weeks.map((w) => w.weight));

  // month grid
  const first = mondayOf(month);
  const lastOfMonth = new Date(month.getFullYear(), month.getMonth() + 1, 0);
  const days = [];
  for (let d = first; d <= lastOfMonth || notMonday(d); d = addDays(d, 1)) days.push(d);
  const dueOn = (k) => items.filter((a) => a.due_date === k);
  const blocksOn = (k) => (showBlocks && plan ? plan.blocks.filter((b) => b.start_date <= k && b.end_date >= k) : []);
  const today = term.today;
  const upcoming = crunch.filter((p) => p.end >= today);
  const past = crunch.length - upcoming.length;

  return (
    <>
      <PageHead step={4} title="Your semester">
        All confirmed deadlines in one place. Crunch periods update the moment you edit a deadline.
      </PageHead>
      {upcoming.map((p) => <CrunchCard key={p.start} p={p} byId={byId} colors={colors} />)}
      {crunch.length === 0 && items.length > 0 && <div className="alert info">No crunch periods: no 7-day window holds 3 or more assessments or 30% or more combined weight.</div>}
      {past > 0 && <p className="muted small" style={{ margin: 0 }}>{past} earlier crunch {past === 1 ? 'period has' : 'periods have'} passed.</p>}
      {items.length === 0 && <div className="alert info">Nothing confirmed yet. <Link to="/review">Review your extracted items</Link> to fill the calendar.</div>}

      <section className="card" aria-labelledby="ld">
        <div className="row between"><h2 id="ld" style={{ fontSize: 16 }}>Weight due per week</h2><span className="muted small">Sum of assessment weights, all courses</span></div>
        <div className="scroll-x">
          <div className="load" style={{ gridTemplateColumns: `repeat(${weeks.length}, minmax(0, 1fr))` }}>
            {weeks.map((w) => (
              <div key={iso(w.start)} className="load-col">
                <span className="small" style={{ fontWeight: 600, color: w.hot ? 'var(--crunch-strong)' : 'var(--text-3)' }}>{+w.weight.toFixed(1)}%</span>
                <div style={{ height: 80, width: '100%', display: 'flex', alignItems: 'flex-end' }}>
                  <div className={`load-bar${w.hot ? ' hot' : ''}`} style={{ height: Math.max(3, Math.round((w.weight / maxW) * 80)) }} />
                </div>
                <span className="small muted">{fmtDay(iso(w.start), false)}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="card" aria-labelledby="mt">
        <div className="row between">
          <div className="row" style={{ gap: 4 }}>
            <button className="btn" type="button" aria-label="Previous month" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))}>‹</button>
            <h2 id="mt" style={{ margin: '0 12px', fontSize: 20 }}>{monthName(month)}</h2>
            <button className="btn" type="button" aria-label="Next month" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))}>›</button>
          </div>
          <div className="legend">
            {Object.entries(colors).map(([c, col]) => <span key={c}><i className="dot" style={{ background: col.dot }} />{c}</span>)}
            <span><i className="dot" style={{ width: 14, borderRadius: 2, background: 'var(--crunch-soft)', border: '1px solid var(--crunch-border)' }} />Crunch period</span>
            {plan && <label><input type="checkbox" checked={showBlocks} onChange={(e) => setShowBlocks(e.target.checked)} /> Study blocks</label>}
          </div>
        </div>
        <div className="scroll-x">
          <div className="month">
            {DOW.map((d) => <span key={d} className="dow">{d}</span>)}
            {days.map((d) => {
              const k = iso(d);
              const out = d.getMonth() !== month.getMonth();
              return (
                <div key={k} className={`cell${out ? ' out' : ''}${hotDays.has(k) ? ' hot' : ''}${k === today ? ' today' : ''}`}>
                  <span className="num">{d.getDate() === 1 || d === days[0] ? fmtDay(k, false) : d.getDate()}</span>
                  {dueOn(k).map((a) => (
                    <div key={a.id} className="chip" style={{ background: colors[a.course_code]?.bg, color: colors[a.course_code]?.fg }}>
                      <strong>{a.course_code}</strong><span>{a.title} · {pct(a.weight_percent)}</span>
                    </div>
                  ))}
                  {blocksOn(k).map((b) => {
                    const a = byId[b.assessment_id];
                    return <div key={b.id} className="chip block" style={{ color: colors[a?.course_code]?.fg || 'var(--text-3)' }}>Study: {a ? a.title : b.task_label}</div>;
                  })}
                </div>
              );
            })}
          </div>
        </div>
      </section>
    </>
  );
}

function notMonday(d) {
  return d.getDay() !== 1; // keep filling until the last row closes on Sunday
}
