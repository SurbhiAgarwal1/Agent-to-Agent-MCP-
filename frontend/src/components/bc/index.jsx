import React from 'react';

export function PageHeader({ title, subtitle, children }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem', flexWrap: 'wrap' }}>
      <div>
        <h1 className="bc-h1">{title}</h1>
        {subtitle && <p className="bc-sub">{subtitle}</p>}
      </div>
      {children}
    </div>
  );
}

export function StatTile({ icon, value, label, tone = 'lav' }) {
  return (
    <div className={`bc-stat bc-t-${tone}`}>
      <div className="ico" aria-hidden="true">{icon}</div>
      <div><div className="v">{value}</div><div className="l">{label}</div></div>
    </div>
  );
}

export function Panel({ title, action, children, className = '' }) {
  return (
    <section className={`bc-panel ${className}`}>
      {title && <h2><span>{title}</span>{action}</h2>}
      {children}
    </section>
  );
}

const STATUS = {
  PENDING: ['Pending', 'gray'], PROCESSING: ['In Progress', 'amber'], PARTIALLY_FULFILLED: ['Partial', 'blue'],
  FULFILLED: ['Fulfilled', 'green'], CANCELLED: ['Cancelled', 'gray'],
};
export function StatusPill({ status }) {
  const [label, tone] = STATUS[status] || [status || '—', 'gray'];
  return <span className={`bc-pill bc-p-${tone}`}>{label}</span>;
}
export function UrgencyPill({ urgency }) {
  const u = (urgency || '').toUpperCase();
  const tone = u === 'CRITICAL' ? 'red' : u === 'HIGH' ? 'red' : u === 'MEDIUM' ? 'amber' : 'gray';
  const label = u === 'CRITICAL' ? 'Urgent' : u === 'HIGH' ? 'High' : u === 'MEDIUM' ? 'Medium' : u ? 'Normal' : '—';
  return <span className={`bc-pill bc-p-${tone}`}>{label}</span>;
}

export function fmtEta(min) {
  if (min == null) return '—';
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60), m = min % 60;
  return m ? `${h} hr ${m} min` : `${h} hr`;
}
export function fmtWhen(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

/** Horizontal bars: [{label, value}] */
export function Bars({ rows, unit = '' }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <div className="bc-bars">
      {rows.map((r) => (
        <div className="bc-bar" key={r.label}>
          <strong>{r.label}</strong>
          <div className="track"><div className="fill" style={{ width: `${(r.value / max) * 100}%` }} /></div>
          <span>{r.value}{unit}</span>
        </div>
      ))}
    </div>
  );
}

/** Vertical column chart: [{label, value}] */
export function Columns({ rows, height = 170 }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  const w = 36, gap = 14, left = 30;
  const width = left + rows.length * (w + gap);
  return (
    <svg viewBox={`0 0 ${width} ${height + 24}`} role="img" aria-label="Units by blood group" style={{ width: '100%', height: 'auto' }}>
      {[0, 0.5, 1].map((t) => (
        <g key={t}>
          <line x1={left - 4} x2={width} y1={height - t * (height - 10)} y2={height - t * (height - 10)} stroke="#eee" />
          <text x={left - 8} y={height - t * (height - 10) + 3} fontSize="8" textAnchor="end" fill="#9ca3af">{Math.round(max * t)}</text>
        </g>
      ))}
      {rows.map((r, i) => {
        const h = (r.value / max) * (height - 10);
        const x = left + i * (w + gap);
        return (
          <g key={r.label}>
            <rect x={x} y={height - h} width={w} height={h} rx="3" fill="#c0505d" opacity={0.55 + 0.45 * (r.value / max)}><title>{`${r.label}: ${r.value}`}</title></rect>
            <text x={x + w / 2} y={height + 14} fontSize="9" textAnchor="middle" fill="#4b5160">{r.label}</text>
          </g>
        );
      })}
    </svg>
  );
}

/** Donut: [{label, value, color}] with a centre label */
export function Donut({ segments, centre, caption }) {
  const total = segments.reduce((s, x) => s + x.value, 0);
  const r = 52, c = 2 * Math.PI * r;
  let offset = 0;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem', flexWrap: 'wrap' }}>
      <svg viewBox="0 0 140 140" width="150" height="150" role="img" aria-label={caption || 'Status split'}>
        <circle cx="70" cy="70" r={r} fill="none" stroke="#f1eef0" strokeWidth="18" />
        {total > 0 && segments.map((s) => {
          const len = (s.value / total) * c;
          const el = <circle key={s.label} cx="70" cy="70" r={r} fill="none" stroke={s.color} strokeWidth="18"
            strokeDasharray={`${len} ${c - len}`} strokeDashoffset={-offset} transform="rotate(-90 70 70)"><title>{`${s.label}: ${s.value}`}</title></circle>;
          offset += len;
          return el;
        })}
        <text x="70" y="68" textAnchor="middle" fontSize="22" fontWeight="800" fill="#1b1f3b">{centre ?? total}</text>
        <text x="70" y="84" textAnchor="middle" fontSize="9" fill="#6b7280">{caption}</text>
      </svg>
      <div className="bc-legend">
        {segments.map((s) => (
          <span key={s.label}><i style={{ background: s.color }} />{s.label} ({total ? Math.round((s.value / total) * 100) : 0}%)</span>
        ))}
      </div>
    </div>
  );
}

/** Line chart: [{label, value}] */
export function Line({ points, height = 150 }) {
  const max = Math.max(1, ...points.map((p) => p.value));
  const width = 420, left = 28, step = (width - left - 24) / Math.max(1, points.length - 1);
  const xy = points.map((p, i) => [left + i * step, height - 8 - (p.value / max) * (height - 22)]);
  const d = xy.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ');
  return (
    <svg viewBox={`0 0 ${width} ${height + 20}`} role="img" aria-label="Requests per day" style={{ width: '100%', height: 'auto' }}>
      {[0, 0.5, 1].map((t) => (
        <g key={t}>
          <line x1={left} x2={width} y1={height - 8 - t * (height - 22)} y2={height - 8 - t * (height - 22)} stroke="#eee" />
          <text x={left - 5} y={height - 5 - t * (height - 22)} fontSize="8" textAnchor="end" fill="#9ca3af">{Math.round(max * t)}</text>
        </g>
      ))}
      <path d={`${d} L${xy[xy.length - 1][0]},${height - 8} L${xy[0][0]},${height - 8} Z`} fill="#a61b2b" opacity="0.08" />
      <path d={d} fill="none" stroke="#c23a49" strokeWidth="2" />
      {xy.map((p, i) => <circle key={i} cx={p[0]} cy={p[1]} r="3" fill="#c23a49"><title>{`${points[i].label}: ${points[i].value}`}</title></circle>)}
      {points.map((p, i) => <text key={p.label} x={xy[i][0]} y={height + 12} fontSize="8" textAnchor="middle" fill="#6b7280">{p.label}</text>)}
    </svg>
  );
}
