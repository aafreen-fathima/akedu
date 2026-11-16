import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api.js';
import { PageHead } from '../App.jsx';

const ACTIVE = ['queued', 'running'];

function Status({ doc }) {
  const job = doc.job;
  if (!job) return null;
  if (ACTIVE.includes(job.status)) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <span className="small">{job.status === 'queued' ? 'Queued' : 'Reading outline…'}</span>
        <div className="progress" role="progressbar" aria-label={`Reading ${doc.filename}`}><div /></div>
      </div>
    );
  }
  if (job.status === 'succeeded') return <span className="tag ok">{job.item_count} items found</span>;
  if (job.status === 'needs_manual') return <span className="tag warn">Couldn't read the deadlines</span>;
  return <span className="tag err">Failed</span>;
}

export default function Upload() {
  const [docs, setDocs] = useState([]);
  const [errors, setErrors] = useState([]);
  const [over, setOver] = useState(false);
  const input = useRef(null);

  const load = useCallback(() => api.get('/documents').then(setDocs).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!docs.some((d) => d.job && ACTIVE.includes(d.job.status))) return undefined;
    const t = setInterval(load, 2000); // poll job status (ADR-06)
    return () => clearInterval(t);
  }, [docs, load]);

  const send = async (files) => {
    const errs = [];
    for (const f of files) {
      try { await api.upload(f); } catch (e) { errs.push(`${f.name}: ${e.message}`); }
    }
    setErrors(errs);
    load();
  };

  const remove = async (id) => { await api.del(`/documents/${id}`); load(); };
  const ready = docs.filter((d) => d.job?.status === 'succeeded').length;

  return (
    <>
      <PageHead step={2} title="Upload your course outlines">
        Add 3 to 5 text-based PDF outlines, up to 10 MB each. Reading one outline can take up to 90 seconds; you can keep working while they process.
      </PageHead>
      <div className={`drop${over ? ' over' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); send([...e.dataTransfer.files]); }}>
        <svg aria-hidden="true" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#3346D3" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M12 16V4" /><path d="M7 9l5-5 5 5" /><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" /></svg>
        <strong style={{ fontSize: 18 }}>Drag PDF outlines here</strong>
        <span className="muted">or</span>
        <button className="btn" type="button" onClick={() => input.current.click()}>Choose files</button>
        <input ref={input} type="file" accept="application/pdf,.pdf" multiple hidden onChange={(e) => { send([...e.target.files]); e.target.value = ''; }} />
        <span className="muted small">PDF only · must contain selectable text · max 10 MB</span>
      </div>
      {errors.map((m) => <div key={m} className="alert error" role="alert">{m}</div>)}
      <div className="alert info">Outlines are read on Akedu's own server and deleted once extraction finishes. Only the extracted titles, dates and weights are kept, and only you can see them.</div>
      <section className="card" style={{ gap: 0, paddingTop: 16, paddingBottom: 8 }} aria-labelledby="files">
        <h2 id="files" style={{ marginBottom: 8 }}>{docs.length} {docs.length === 1 ? 'file' : 'files'}</h2>
        {docs.length === 0 && <p className="muted" style={{ margin: '0 0 16px' }}>No outlines yet.</p>}
        {docs.map((d) => (
          <div key={d.id} className="file-row">
            <div className="name">
              <strong>{d.filename}</strong>
              <span className="muted small">{d.course_code ? `${d.course_code} · ` : ''}{d.page_count} {d.page_count === 1 ? 'page' : 'pages'}</span>
              {d.job?.status === 'needs_manual' && <span className="small" style={{ color: 'var(--warn)' }}>The model's answer couldn't be used. Enter this course's deadlines manually on the Review page.</span>}
              {d.job?.status === 'failed' && <span className="small" style={{ color: 'var(--danger)' }}>{d.job.error}</span>}
            </div>
            <Status doc={d} />
            {d.job?.status === 'succeeded' && <Link className="btn ghost" to="/review">Review</Link>}
            <button className="btn danger" type="button" onClick={() => remove(d.id)} aria-label={`Remove ${d.filename}`}>Remove</button>
          </div>
        ))}
      </section>
      <div className="row between">
        <span className="muted">{ready} of {docs.length} outlines ready to review</span>
        <Link className="btn primary" to="/review">Review extracted items</Link>
      </div>
    </>
  );
}
