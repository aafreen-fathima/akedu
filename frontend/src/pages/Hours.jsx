import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api.js';
import { PageHead } from '../App.jsx';
import { DAY_NAMES, DOW, hhmm } from '../util.js';

const FULL_DAY_HOURS = 8;
const hoursOf = (s) => {
  const [h1, m1] = s.start_time.split(':').map(Number);
  const [h2, m2] = s.end_time.split(':').map(Number);
  return (h2 * 60 + m2 - h1 * 60 - m1) / 60;
};

export default function Hours() {
  const [slots, setSlots] = useState([]);
  const [form, setForm] = useState({ weekday: 0, start_time: '09:00', end_time: '17:00', label: '' });
  const [error, setError] = useState('');
  const [saved, setSaved] = useState('');

  useEffect(() => { api.get('/reserved-hours').then(setSlots).catch((e) => setError(e.message)); }, []);

  const save = async (next, msg) => {
    setError('');
    try {
      const body = next.map(({ weekday, start_time, end_time, label }) => ({ weekday, start_time: hhmm(start_time), end_time: hhmm(end_time), label }));
      setSlots(await api.put('/reserved-hours', body));
      setSaved(msg);
      return true;
    } catch (e) {
      setError(e.message);
      return false;
    }
  };

  const add = async (e) => {
    e.preventDefault();
    if (await save([...slots, { ...form, weekday: Number(form.weekday) }], 'Slot added.')) setForm({ ...form, label: '' });
  };

  const perDay = DOW.map((_, d) => slots.filter((s) => s.weekday === d));
  const totals = perDay.map((ss) => ss.reduce((t, s) => t + hoursOf(s), 0));
  const fullCount = totals.filter((h) => h >= FULL_DAY_HOURS).length;

  return (
    <>
      <PageHead step={1} title="Your fixed weekly hours">
        Add work shifts, TA hours and anything else you can't move. Akedu never places study on a day these fill ({FULL_DAY_HOURS} hours or more).
      </PageHead>
      {error && <div className="alert error" role="alert">{error}</div>}
      <div className="row" style={{ alignItems: 'flex-start', gap: 24 }}>
        <form className="card" style={{ flex: '1 1 280px' }} onSubmit={add}>
          <h2>Add a slot</h2>
          <div className="field">
            <label htmlFor="day">Day</label>
            <select id="day" className="input" value={form.weekday} onChange={(e) => setForm({ ...form, weekday: e.target.value })}>
              {DAY_NAMES.map((n, i) => <option key={n} value={i}>{n}</option>)}
            </select>
          </div>
          <div className="row">
            <div className="field"><label htmlFor="start">Start</label>
              <input id="start" className="input" type="time" required value={form.start_time} onChange={(e) => setForm({ ...form, start_time: e.target.value })} /></div>
            <div className="field"><label htmlFor="end">End</label>
              <input id="end" className="input" type="time" required value={form.end_time} onChange={(e) => setForm({ ...form, end_time: e.target.value })} /></div>
          </div>
          <div className="field"><label htmlFor="label">Label</label>
            <input id="label" className="input" placeholder="e.g. Co-op, TA marking" maxLength={64} value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} /></div>
          <button className="btn primary" type="submit">Add slot</button>
          <span className="muted small" role="status">{saved}</span>
        </form>
        <section className="card" style={{ flex: '999 1 460px', minWidth: 0 }} aria-labelledby="wk">
          <div className="row between"><h2 id="wk">Your week</h2>
            <span className="muted small">{fullCount} full {fullCount === 1 ? 'day' : 'days'} · {7 - fullCount} open for study</span></div>
          <div className="scroll-x">
            <div className="week">
              {perDay.map((ss, d) => {
                const full = totals[d] >= FULL_DAY_HOURS;
                return (
                  <div key={d} className={`day${full ? ' full' : ''}`}>
                    <strong>{DOW[d]}</strong>
                    <span className={`tag ${full ? 'grey' : 'ok'}`} style={{ alignSelf: 'flex-start' }}>{full ? 'Full day' : 'Open'}</span>
                    {ss.length === 0 && <span className="muted small">No slots</span>}
                    {ss.map((s) => <span key={s.id} className="slot-pill">{s.label || 'Busy'}<br />{hhmm(s.start_time)}–{hhmm(s.end_time)}</span>)}
                    <span className="muted small" style={{ marginTop: 'auto' }}>{+totals[d].toFixed(1)} h</span>
                  </div>
                );
              })}
            </div>
          </div>
        </section>
      </div>
      <section className="card" aria-labelledby="sl">
        <h2 id="sl">{slots.length} recurring {slots.length === 1 ? 'slot' : 'slots'}</h2>
        {slots.length > 0 && (
          <div className="scroll-x">
            <table className="t">
              <thead><tr><th>Day</th><th>Time</th><th>Label</th><th>Hours</th><th><span className="sr">Actions</span></th></tr></thead>
              <tbody>
                {slots.map((s) => (
                  <tr key={s.id}>
                    <td>{DAY_NAMES[s.weekday]}</td><td>{hhmm(s.start_time)}–{hhmm(s.end_time)}</td><td>{s.label}</td><td>{+hoursOf(s).toFixed(1)}</td>
                    <td style={{ textAlign: 'right' }}>
                      <button className="btn danger" type="button" aria-label={`Delete ${DAY_NAMES[s.weekday]} ${s.label}`}
                        onClick={() => save(slots.filter((x) => x.id !== s.id), 'Slot deleted.')}>Delete</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <div className="row" style={{ justifyContent: 'flex-end' }}><Link className="btn primary" to="/upload">Continue to upload</Link></div>
    </>
  );
}
