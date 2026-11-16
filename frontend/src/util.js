// Shared formatting and colour helpers.
const PALETTE = [
  { bg: '#EEF0FD', fg: '#2535A8', dot: '#3346D3' },
  { bg: '#E2F3F1', fg: '#0F5E58', dot: '#0F766E' },
  { bg: '#FDF1DE', fg: '#7A4300', dot: '#B45309' },
  { bg: '#F3E8FD', fg: '#5B1A9C', dot: '#7E22CE' },
  { bg: '#E6F1FB', fg: '#0C447C', dot: '#185FA5' },
  { bg: '#FBEAF0', fg: '#72243E', dot: '#993556' },
];

export function courseColors(codes) {
  const map = {};
  [...new Set(codes)].sort().forEach((c, i) => { map[c] = PALETTE[i % PALETTE.length]; });
  return map;
}

export const DOW = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
export const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

// Dates are handled as local calendar days built from 'YYYY-MM-DD' strings.
export function parseDay(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d);
}
export function iso(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
export function addDays(d, n) {
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  return x;
}
export function weekdayIdx(d) {
  return (d.getDay() + 6) % 7; // Monday = 0
}
export function mondayOf(d) {
  return addDays(d, -weekdayIdx(d));
}
export function fmtDay(isoStr, withDow = true) {
  if (!isoStr) return '—';
  const d = parseDay(isoStr);
  return `${withDow ? DOW[weekdayIdx(d)] + ' ' : ''}${MONTHS[d.getMonth()]} ${d.getDate()}`;
}
export function fmtRange(a, b) {
  if (a === b) return fmtDay(a);
  const da = parseDay(a), db = parseDay(b);
  const left = `${DOW[weekdayIdx(da)]}–${DOW[weekdayIdx(db)]}`;
  return da.getMonth() === db.getMonth()
    ? `${left} ${MONTHS[da.getMonth()]} ${da.getDate()}–${db.getDate()}`
    : `${left} ${MONTHS[da.getMonth()]} ${da.getDate()} – ${MONTHS[db.getMonth()]} ${db.getDate()}`;
}
export const monthName = (d) => d.toLocaleString('en-CA', { month: 'long', year: 'numeric' });
export const hhmm = (t) => (t ? t.slice(0, 5) : '');
export const pct = (w) => (w === null || w === undefined ? '—' : `${+w}%`);
